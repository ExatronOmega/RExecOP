from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from rexecop.errors import RExecOpValidationError
from rexecop.operation.controller import OperationController
from rexecop.runtime_ops.watchdog import WatchdogService
from rexecop.runtime_ops.worker import run_worker
from rexecop.storage.file_store import FileStore

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE = REPO_ROOT / "examples/profiles/runtime-fixture/profile.yaml"
ENVIRONMENT = REPO_ROOT / "examples/environments/runtime-fixture.example.yaml"
NOW = datetime(2026, 6, 28, 12, 0, 0, tzinfo=UTC)


def _controller(tmp_path: Path) -> OperationController:
    return OperationController(store=FileStore(tmp_path / ".rexecop"))


def _inbox_payload(*, secret: str = "never-write-this-token") -> dict[str, object]:
    return {
        "profile": str(PROFILE),
        "env": str(ENVIRONMENT),
        "intent": "inspect_fixture_state",
        "target": "fixture-target",
        "mode": "dry_run",
        "auto_start": True,
        "private_note": secret,
    }


def _watchdog_records(store: FileStore) -> list[dict[str, object]]:
    records = store.root / "watchdog" / "records"
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(records.glob("*.json"))]


def test_watchdog_records_worker_heartbeat(tmp_path: Path) -> None:
    store = FileStore(tmp_path / ".rexecop")
    service = WatchdogService(store)

    record = service.record_heartbeat(worker_id="worker-a", now=NOW)

    heartbeat = json.loads((store.root / "watchdog" / "heartbeat.json").read_text())
    assert heartbeat == record
    assert record["schema"] == "rexecop.watchdog_record.v0.1"
    assert record["observation"] == "worker_heartbeat"
    assert record["decision"] == "record_health"
    assert record["payload"]["worker_id"] == "worker-a"
    assert (store.root / "watchdog").stat().st_mode & 0o777 == 0o700
    assert (store.root / "watchdog" / "heartbeat.json").stat().st_mode & 0o777 == 0o600


def test_watchdog_moves_stale_inbox_to_dead_letter_without_payload_leak(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path)
    inbox = controller.store.root / "inbox"
    inbox.mkdir(parents=True)
    path = inbox / "job-1.json"
    path.write_text(json.dumps(_inbox_payload()), encoding="utf-8")
    stale = (NOW - timedelta(hours=2)).timestamp()
    os.utime(path, (stale, stale))

    records = WatchdogService(controller.store).move_stale_inbox_items(
        max_age_seconds=60,
        now=NOW,
    )

    assert len(records) == 1
    assert not path.exists()
    dead_letters = list((controller.store.root / "dead_letter").glob("*.json"))
    assert len(dead_letters) == 1
    assert dead_letters[0].read_text(encoding="utf-8").find("never-write-this-token") != -1
    record_text = json.dumps(records[0], sort_keys=True)
    assert "never-write-this-token" not in record_text
    assert records[0]["decision"] == "move_to_dead_letter"
    assert records[0]["payload"]["reason"] == "stale_inbox_item"


def test_worker_watchdog_moves_stale_inbox_before_processing(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    inbox = controller.store.root / "inbox"
    inbox.mkdir(parents=True)
    path = inbox / "job-1.json"
    path.write_text(json.dumps(_inbox_payload()), encoding="utf-8")
    stale = (datetime.now(UTC) - timedelta(hours=2)).timestamp()
    os.utime(path, (stale, stale))

    started = run_worker(
        controller,
        once=True,
        watch_inbox=True,
        watchdog=True,
        stale_inbox_seconds=60,
    )

    assert started == []
    assert controller.store.list_operations() == []
    assert not path.exists()
    assert list((controller.store.root / "dead_letter").glob("*.json"))
    records = _watchdog_records(controller.store)
    assert {record["observation"] for record in records} >= {
        "worker_heartbeat",
        "inbox_item",
        "queue_depth",
    }


def test_worker_watchdog_moves_failed_inbox_to_dead_letter_without_payload_leak(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path)
    inbox = controller.store.root / "inbox"
    inbox.mkdir(parents=True)
    path = inbox / "bad-job.json"
    path.write_text(
        json.dumps({"profile": str(PROFILE), "private_note": "never-write-this-token"}),
        encoding="utf-8",
    )

    started = run_worker(controller, once=True, watch_inbox=True, watchdog=True)

    assert started == []
    assert not path.exists()
    assert list((controller.store.root / "dead_letter").glob("*.json"))
    record_text = json.dumps(_watchdog_records(controller.store), sort_keys=True)
    assert "never-write-this-token" not in record_text
    assert "inbox_processing_failed" in record_text
    assert "RExecOpValidationError" in record_text


def test_watchdog_rejects_invalid_thresholds(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    service = WatchdogService(controller.store)

    with pytest.raises(RExecOpValidationError, match="max_age_seconds must be positive"):
        service.move_stale_inbox_items(max_age_seconds=0)

    with pytest.raises(RExecOpValidationError, match="stale_inbox_seconds must be positive"):
        run_worker(controller, once=True, watchdog=True, stale_inbox_seconds=0)
