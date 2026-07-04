from __future__ import annotations

import json
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rexecop.errors import RExecOpValidationError
from rexecop.storage.atomic import atomic_write_text, secure_directory, secure_file

WORKER_LEASE_SCHEMA = "rexecop.worker_lease.v0.1"
DEFAULT_LEASE_TTL_SECONDS = 120.0


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class WorkerLeaseManager:
    """Single-node worker lease with captured wall time and monotonic heartbeat."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.lease_path = root / "watchdog" / "worker_lease.json"

    def read(self) -> dict[str, Any] | None:
        if not self.lease_path.is_file():
            return None
        secure_file(self.lease_path)
        payload = json.loads(self.lease_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None

    def is_stale(
        self,
        lease: Mapping[str, Any] | None = None,
        *,
        now: datetime | None = None,
        max_age_seconds: float = DEFAULT_LEASE_TTL_SECONDS,
    ) -> bool:
        record = dict(lease) if lease is not None else self.read()
        if not record:
            return True
        if str(record.get("schema") or "") != WORKER_LEASE_SCHEMA:
            return True
        observed = _parse_time(str(record.get("heartbeat_at") or record.get("acquired_at") or ""))
        if observed is None:
            return True
        current = now or _utc_now()
        age = max(0.0, current.timestamp() - observed.timestamp())
        return age > max_age_seconds

    def clear_if_stale(
        self,
        *,
        now: datetime | None = None,
        max_age_seconds: float = DEFAULT_LEASE_TTL_SECONDS,
    ) -> bool:
        if not self.lease_path.is_file():
            return False
        if not self.is_stale(now=now, max_age_seconds=max_age_seconds):
            return False
        self.lease_path.unlink(missing_ok=True)
        return True

    def acquire(
        self,
        *,
        worker_id: str,
        now: datetime | None = None,
        max_age_seconds: float = DEFAULT_LEASE_TTL_SECONDS,
    ) -> dict[str, Any]:
        if not worker_id.strip():
            raise RExecOpValidationError("worker_id must not be empty")
        observed_at = now or _utc_now()
        existing = self.read()
        if existing and not self.is_stale(
            existing,
            now=observed_at,
            max_age_seconds=max_age_seconds,
        ):
            holder = str(existing.get("worker_id") or "")
            if holder != worker_id:
                raise RExecOpValidationError(
                    f"worker lease held by {holder!r}; stale lease recovery required"
                )
        return self._write(worker_id=worker_id, observed_at=observed_at, previous=existing)

    def renew(
        self,
        *,
        worker_id: str,
        now: datetime | None = None,
        monotonic_seconds: float | None = None,
        max_age_seconds: float = DEFAULT_LEASE_TTL_SECONDS,
    ) -> dict[str, Any]:
        observed_at = now or _utc_now()
        existing = self.read()
        if existing and not self.is_stale(
            existing,
            now=observed_at,
            max_age_seconds=max_age_seconds,
        ):
            holder = str(existing.get("worker_id") or "")
            if holder != worker_id:
                raise RExecOpValidationError(f"worker lease held by {holder!r}")
            monotonic = (
                monotonic_seconds if monotonic_seconds is not None else time.monotonic()
            )
            previous_monotonic = existing.get("monotonic_seconds")
            if isinstance(previous_monotonic, (int, float)) and monotonic < float(
                previous_monotonic
            ):
                raise RExecOpValidationError("worker lease monotonic clock moved backwards")
        else:
            return self.acquire(
                worker_id=worker_id,
                now=observed_at,
                max_age_seconds=max_age_seconds,
            )
        return self._write(
            worker_id=worker_id,
            observed_at=observed_at,
            previous=existing,
            monotonic_seconds=monotonic_seconds,
        )

    def _write(
        self,
        *,
        worker_id: str,
        observed_at: datetime,
        previous: dict[str, Any] | None,
        monotonic_seconds: float | None = None,
    ) -> dict[str, Any]:
        secure_directory(self.lease_path.parent)
        monotonic = (
            float(monotonic_seconds)
            if monotonic_seconds is not None
            else round(time.monotonic(), 6)
        )
        acquired_at = str((previous or {}).get("acquired_at") or observed_at.isoformat())
        record = {
            "schema": WORKER_LEASE_SCHEMA,
            "worker_id": worker_id,
            "acquired_at": acquired_at,
            "heartbeat_at": observed_at.isoformat(),
            "monotonic_seconds": monotonic,
            "captured_epoch_seconds": round(observed_at.timestamp(), 3),
        }
        atomic_write_text(
            self.lease_path,
            json.dumps(record, indent=2, sort_keys=True) + "\n",
        )
        return record


def _parse_time(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)