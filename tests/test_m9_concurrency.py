from __future__ import annotations

import multiprocessing
from pathlib import Path
from typing import Any

import pytest

from rexecop.errors import RExecOpConcurrencyConflict
from rexecop.operation.model import Operation
from rexecop.runtime_ops.queue import RunNowQueue
from rexecop.storage.file_store import FileStore
from rexecop.storage.sqlite_store import SqliteStore


def _operation(operation_id: str = "op-cas") -> Operation:
    return Operation(
        id=operation_id,
        profile="fixture",
        environment="fixture",
        intent="inspect",
        target="target",
        mode="dry_run",
        requested_by="test",
        state="planned",
        created_at="2026-07-12T00:00:00+00:00",
        updated_at="2026-07-12T00:00:00+00:00",
    )


@pytest.mark.parametrize("backend", ["file", "sqlite"])
def test_stale_operation_revision_fails_with_stable_conflict(tmp_path: Path, backend: str) -> None:
    store = (
        FileStore(tmp_path / ".rexecop")
        if backend == "file"
        else SqliteStore(tmp_path / ".rexecop")
    )
    operation = _operation()
    store.save_operation(operation)
    first = store.load_operation(operation.id)
    stale = store.load_operation(operation.id)
    first.metadata["writer"] = "first"
    store.save_operation(first)
    stale.metadata["writer"] = "stale"

    with pytest.raises(RExecOpConcurrencyConflict) as caught:
        store.save_operation(stale)

    assert caught.value.code == "concurrency_conflict"
    assert store.load_operation(operation.id).metadata["writer"] == "first"


def _claim_queue(root: str, result: Any) -> None:
    claim = RunNowQueue(FileStore(Path(root))).claim(
        owner_token=multiprocessing.current_process().name,
        lease_epoch=1,
        process_instance_id=multiprocessing.current_process().name,
    )
    result.put(None if claim is None else claim["operation_id"])


def test_queue_claim_is_atomic_across_processes(tmp_path: Path) -> None:
    root = tmp_path / ".rexecop"
    queue = RunNowQueue(FileStore(root))
    queue.enqueue("op-first")
    context = multiprocessing.get_context("spawn")
    result = context.Queue()
    processes = [context.Process(target=_claim_queue, args=(str(root), result)) for _ in range(2)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0

    assert sorted((result.get(timeout=2) for _ in processes), key=str) == [None, "op-first"]
    payload = queue._load_unlocked()
    claim = payload["claims"]["op-first"]
    assert claim["status"] == "claimed"
    assert claim["attempt"] == 1
    assert claim["owner_token"]
    assert claim["expires_at"]
