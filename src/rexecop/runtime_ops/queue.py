from __future__ import annotations

import fcntl
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from rexecop.errors import RExecOpConcurrencyConflict
from rexecop.storage.atomic import atomic_write_text, secure_directory, secure_file
from rexecop.storage.port import RuntimeStore


class RunNowQueue:
    """Process-safe FIFO queue with durable, fenced claim records."""

    def __init__(self, store: RuntimeStore) -> None:
        self.store = store
        self.queue_dir = store.root / "queue"
        self.queue_file = self.queue_dir / "run_now.json"
        self.lock_file = self.queue_dir / "run_now.lock"

    @contextmanager
    def _locked(self) -> Iterator[None]:
        secure_directory(self.queue_dir)
        with self.lock_file.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.queue_file.is_file():
            return {"pending": [], "claims": {}}
        secure_file(self.queue_file)
        data = json.loads(self.queue_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"pending": [], "claims": {}}
        pending = data.get("pending")
        claims = data.get("claims")
        return {
            "pending": [str(item) for item in pending] if isinstance(pending, list) else [],
            "claims": dict(claims) if isinstance(claims, dict) else {},
        }

    def _save_unlocked(self, data: dict[str, Any]) -> None:
        data["updated_at"] = datetime.now(UTC).replace(microsecond=0).isoformat()
        atomic_write_text(self.queue_file, json.dumps(data, indent=2, sort_keys=True) + "\n")

    def list_pending(self) -> list[str]:
        with self._locked():
            return list(self._load_unlocked()["pending"])

    def position(self, operation_id: str) -> int | None:
        pending = self.list_pending()
        return pending.index(operation_id) if operation_id in pending else None

    def enqueue(self, operation_id: str) -> int:
        with self._locked():
            data = self._load_unlocked()
            pending = data["pending"]
            if operation_id not in pending:
                pending.append(operation_id)
            data["pending"] = pending
            self._save_unlocked(data)
            return pending.index(operation_id)

    def remove(self, operation_id: str) -> None:
        with self._locked():
            data = self._load_unlocked()
            data["pending"] = [item for item in data["pending"] if item != operation_id]
            data["claims"].pop(operation_id, None)
            self._save_unlocked(data)

    def discard_pending(self, operation_id: str) -> None:
        with self._locked():
            data = self._load_unlocked()
            data["pending"] = [item for item in data["pending"] if item != operation_id]
            self._save_unlocked(data)

    def peek(self) -> str | None:
        pending = self.list_pending()
        return pending[0] if pending else None

    def claim(
        self,
        *,
        owner_token: str,
        lease_epoch: int,
        process_instance_id: str,
        ttl_seconds: float = 120.0,
    ) -> dict[str, Any] | None:
        now = datetime.now(UTC).replace(microsecond=0)
        with self._locked():
            data = self._load_unlocked()
            pending = data["pending"]
            if not pending:
                return None
            operation_id = pending.pop(0)
            previous = data["claims"].get(operation_id)
            attempt = int(previous.get("attempt") or 0) + 1 if isinstance(previous, dict) else 1
            claim = {
                "operation_id": operation_id,
                "status": "claimed",
                "owner_token": owner_token,
                "process_instance_id": process_instance_id,
                "lease_epoch": lease_epoch,
                "attempt": attempt,
                "claimed_at": now.isoformat(),
                "expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
            }
            data["pending"] = pending
            data["claims"][operation_id] = claim
            self._save_unlocked(data)
            return claim

    def complete_claim(self, operation_id: str, *, owner_token: str, lease_epoch: int) -> None:
        with self._locked():
            data = self._load_unlocked()
            claim = data["claims"].get(operation_id)
            if not isinstance(claim, dict) or (
                str(claim.get("owner_token") or "") != owner_token
                or int(claim.get("lease_epoch") or 0) != lease_epoch
            ):
                raise RExecOpConcurrencyConflict(
                    f"concurrency_conflict: queue claim ownership lost for {operation_id}"
                )
            claim["status"] = "completed"
            claim["completed_at"] = datetime.now(UTC).replace(microsecond=0).isoformat()
            data["claims"][operation_id] = claim
            self._save_unlocked(data)

    def dequeue(self) -> str | None:
        """Compatibility helper; execution paths must use fenced claim()."""
        with self._locked():
            data = self._load_unlocked()
            if not data["pending"]:
                return None
            operation_id = data["pending"].pop(0)
            self._save_unlocked(data)
            return operation_id
