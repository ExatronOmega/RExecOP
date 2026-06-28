from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rexecop.errors import RExecOpValidationError
from rexecop.storage.atomic import atomic_write_text, secure_directory, secure_file
from rexecop.storage.port import RuntimeStore

WATCHDOG_SCHEMA = "rexecop.watchdog_record.v0.1"
DEFAULT_WORKER_ID = "local-worker"


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _timestamp(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%SZ")


class WatchdogService:
    """Domain-neutral supervisor for RExecOp's own runtime mechanics."""

    def __init__(self, store: RuntimeStore) -> None:
        self.store = store
        self.root = store.root
        self.watchdog_dir = self.root / "watchdog"
        self.records_dir = self.watchdog_dir / "records"
        self.dead_letter_dir = self.root / "dead_letter"

    def ensure_layout(self) -> None:
        self.store.ensure_layout()
        secure_directory(self.watchdog_dir)
        secure_directory(self.records_dir)
        secure_directory(self.dead_letter_dir)

    def record_heartbeat(
        self,
        *,
        worker_id: str = DEFAULT_WORKER_ID,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not worker_id.strip():
            raise RExecOpValidationError("worker_id must not be empty")
        observed_at = now or _utc_now()
        record = self._write_record(
            observation="worker_heartbeat",
            decision="record_health",
            observed_at=observed_at,
            payload={
                "worker_id": worker_id,
                "monotonic_seconds": round(time.monotonic(), 6),
            },
        )
        atomic_write_text(
            self.watchdog_dir / "heartbeat.json",
            json.dumps(record, indent=2, sort_keys=True) + "\n",
        )
        return record

    def record_queue_depth(
        self,
        *,
        depth: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if depth < 0:
            raise RExecOpValidationError("queue depth must not be negative")
        return self._write_record(
            observation="queue_depth",
            decision="record_health",
            observed_at=now or _utc_now(),
            payload={"depth": depth},
        )

    def move_stale_inbox_items(
        self,
        *,
        max_age_seconds: float,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        if max_age_seconds <= 0:
            raise RExecOpValidationError("max_age_seconds must be positive")
        self.ensure_layout()
        inbox = self.root / "inbox"
        if not inbox.is_dir():
            return []
        secure_directory(inbox)

        observed_at = now or _utc_now()
        now_seconds = observed_at.timestamp()
        records: list[dict[str, Any]] = []
        for path in sorted(inbox.glob("*.json")):
            age_seconds = max(0.0, now_seconds - path.stat().st_mtime)
            if age_seconds <= max_age_seconds:
                continue
            records.append(
                self.move_inbox_item_to_dead_letter(
                    path,
                    reason="stale_inbox_item",
                    observed_at=observed_at,
                    details={
                        "age_seconds": round(age_seconds, 3),
                        "max_age_seconds": max_age_seconds,
                    },
                )
            )
        return records

    def move_inbox_item_to_dead_letter(
        self,
        path: Path,
        *,
        reason: str,
        observed_at: datetime | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.ensure_layout()
        if not path.is_file():
            raise RExecOpValidationError(f"inbox item not found: {path.name}")
        secure_file(path)
        timestamp = _timestamp(observed_at or _utc_now())
        destination = self.dead_letter_dir / f"{timestamp}-{uuid.uuid4().hex[:8]}-{path.name}"
        path.replace(destination)
        secure_file(destination)
        record = self._write_record(
            observation="inbox_item",
            decision="move_to_dead_letter",
            observed_at=observed_at or _utc_now(),
            payload={
                "reason": reason,
                "source_name": path.name,
                "dead_letter_name": destination.name,
                "details": dict(details or {}),
            },
        )
        return record

    def _write_record(
        self,
        *,
        observation: str,
        decision: str,
        observed_at: datetime,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.ensure_layout()
        record_id = f"wd-{_timestamp(observed_at)}-{uuid.uuid4().hex[:12]}"
        record = {
            "schema": WATCHDOG_SCHEMA,
            "record_id": record_id,
            "observed_at": observed_at.isoformat(),
            "observation": observation,
            "decision": decision,
            "payload": payload,
        }
        atomic_write_text(
            self.records_dir / f"{record_id}.json",
            json.dumps(record, indent=2, sort_keys=True) + "\n",
        )
        return record
