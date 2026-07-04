from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rexecop.cli import app
from rexecop.errors import RExecOpValidationError
from rexecop.operation.controller import OperationController
from rexecop.operation.model import Operation
from rexecop.operation.plan import OperationPlan
from rexecop.operation.state import OperationState
from rexecop.runtime_ops.backup import create_runtime_backup, restore_runtime_backup
from rexecop.runtime_ops.idempotency import start_idempotency_key
from rexecop.runtime_ops.lease import WorkerLeaseManager
from rexecop.runtime_ops.recovery import run_startup_recovery, start_is_idempotent
from rexecop.runtime_ops.target_lock import TargetLockManager
from rexecop.runtime_ops.worker import run_worker
from rexecop.storage.file_store import FileStore

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE = REPO_ROOT / "examples/profiles/runtime-fixture/profile.yaml"
ENVIRONMENT = REPO_ROOT / "examples/environments/runtime-fixture.example.yaml"
NOW = datetime(2026, 7, 4, 12, 0, 0, tzinfo=UTC)
runner = CliRunner()


def _controller(tmp_path: Path) -> OperationController:
    return OperationController(store=FileStore(tmp_path / ".rexecop"))


def _minimal_plan(operation_id: str) -> OperationPlan:
    return OperationPlan(
        operation_id=operation_id,
        profile="runtime-fixture",
        environment="runtime-fixture",
        intent="inspect_fixture_state",
        target="fixture-target",
        mode="dry_run",
        workflow={"id": "fixture-workflow", "steps": []},
        planned_steps=[],
        required_connectors=[],
        risk="low",
        govengine_request_preview={},
        expected_evidence=[],
        pause_safe_points=[],
        retry_policy_summary={"max_attempts": 0},
        rollback_available=False,
    )


def test_plan_attaches_explicit_idempotency_keys(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    operation = controller.plan(
        profile_path=PROFILE,
        environment_path=ENVIRONMENT,
        intent="inspect_fixture_state",
        target="fixture-target",
        mode="dry_run",
    )
    keys = operation.metadata.get("idempotency")
    assert isinstance(keys, dict)
    assert keys["schema"] == "rexecop.idempotency.v0.1"
    assert len(str(keys["plan_key"])) == 64
    assert keys["start_key"] == start_idempotency_key(operation.id)
    assert keys["start_key"] != keys["plan_key"]


def test_start_is_idempotent_for_terminal_operation(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    operation = controller.plan(
        profile_path=PROFILE,
        environment_path=ENVIRONMENT,
        intent="inspect_fixture_state",
        target="fixture-target",
        mode="dry_run",
    )
    completed = controller.start(operation.id)
    assert completed.state == OperationState.COMPLETED.value
    again = controller.start(operation.id)
    assert again.state == OperationState.COMPLETED.value
    assert start_is_idempotent(again) is True


def test_startup_recovery_interrupts_running_operation(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    now = NOW.isoformat()
    operation = Operation(
        id="op-running-1",
        profile="runtime-fixture",
        environment="runtime-fixture",
        intent="inspect_fixture_state",
        target="fixture-target",
        mode="dry_run",
        requested_by="operator",
        state=OperationState.RUNNING.value,
        created_at=now,
        updated_at=now,
        correlation_id="corr-running-1",
        metadata={"execution_cursor": {"next_step_index": 1}},
    )
    controller.store.save_operation(operation)
    controller.store.save_plan(_minimal_plan(operation.id))

    report = run_startup_recovery(controller.store, controller=controller, now=NOW)

    updated = controller.get_operation(operation.id)
    assert updated.state == OperationState.FAILED.value
    assert updated.metadata["recovery"]["reason"] == "interrupted_by_restart"
    assert report["summary"]["interrupted_count"] == 1


def test_startup_recovery_releases_stale_lock(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    now = NOW.isoformat()
    completed = Operation(
        id="op-done-1",
        profile="runtime-fixture",
        environment="env-a",
        intent="inspect_fixture_state",
        target="target-a",
        mode="apply",
        requested_by="operator",
        state=OperationState.COMPLETED.value,
        created_at=now,
        updated_at=now,
        correlation_id="corr-done-1",
    )
    controller.store.save_operation(completed)
    TargetLockManager(controller.store).acquire(
        environment="env-a",
        target="target-a",
        operation_id="op-done-1",
    )

    report = run_startup_recovery(controller.store, controller=controller, now=NOW)

    assert list((controller.store.root / "locks").glob("*.lock")) == []
    assert report["actions"]["released_stale_locks"][0]["operation_id"] == "op-done-1"


def test_worker_lease_rejects_conflicting_holder(tmp_path: Path) -> None:
    store = FileStore(tmp_path / ".rexecop")
    lease = WorkerLeaseManager(store.root)
    lease.acquire(worker_id="worker-a", now=NOW)
    with pytest.raises(RExecOpValidationError, match="worker lease held"):
        lease.acquire(worker_id="worker-b", now=NOW + timedelta(seconds=5))


def test_worker_lease_clears_when_stale(tmp_path: Path) -> None:
    store = FileStore(tmp_path / ".rexecop")
    lease = WorkerLeaseManager(store.root)
    lease.acquire(worker_id="worker-a", now=NOW - timedelta(seconds=300))
    assert lease.clear_if_stale(now=NOW) is True
    renewed = lease.acquire(worker_id="worker-b", now=NOW)
    assert renewed["worker_id"] == "worker-b"


def test_backup_restore_round_trip(tmp_path: Path) -> None:
    source_root = tmp_path / "source" / ".rexecop"
    controller = OperationController(store=FileStore(source_root))
    operation = controller.plan(
        profile_path=PROFILE,
        environment_path=ENVIRONMENT,
        intent="inspect_fixture_state",
        target="fixture-target",
        mode="dry_run",
    )
    controller.start(operation.id)

    archive_dir = tmp_path / "backup"
    created = create_runtime_backup(source_root, output=archive_dir, now=NOW)
    archive = Path(created["archive"])
    assert archive.is_file()

    target_root = tmp_path / "restored" / ".rexecop"
    restored = restore_runtime_backup(archive=archive, target_root=target_root)
    assert restored["status"] == "restored"
    restored_store = FileStore(target_root)
    restored_ops = restored_store.list_operations()
    assert len(restored_ops) == 1
    assert restored_ops[0].id == operation.id


def test_recovery_replay_drill_worker_restart_does_not_duplicate_start(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path)
    operation = controller.plan(
        profile_path=PROFILE,
        environment_path=ENVIRONMENT,
        intent="inspect_fixture_state",
        target="fixture-target",
        mode="dry_run",
        requested_by="trigger:inbox:job.json",
    )
    operation.state = OperationState.RUNNING.value
    operation.metadata["execution_cursor"] = {"next_step_index": 0}
    controller.store.save_operation(operation)

    first = run_worker(controller, once=True, watchdog=True)
    assert first == []
    updated = controller.get_operation(operation.id)
    assert updated.state == OperationState.FAILED.value

    second = run_worker(controller, once=True, watchdog=True)
    assert second == []
    final = controller.get_operation(operation.id)
    assert final.state == OperationState.FAILED.value


def test_cli_runtime_recover_and_backup(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    init = runner.invoke(app, ["--root", str(root), "init"])
    assert init.exit_code == 0, init.output

    recover = runner.invoke(app, ["--root", str(root), "runtime", "recover", "--json"])
    assert recover.exit_code == 0, recover.output
    assert '"schema": "rexecop.runtime_recovery.v0.1"' in recover.output

    backup = runner.invoke(
        app,
        ["--root", str(root), "backup", "create", "--output", str(tmp_path / "bundle.tar")],
    )
    assert backup.exit_code == 0, backup.output
    assert '"status": "created"' in backup.output