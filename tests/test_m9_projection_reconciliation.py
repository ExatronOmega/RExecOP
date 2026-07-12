from __future__ import annotations

from pathlib import Path

import pytest

from rexecop.operation.controller import OperationController
from rexecop.runtime_ops.projection import reconcile_pending_projections
from rexecop.storage.file_store import FileStore

pytestmark = pytest.mark.m9_runtime

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE = REPO_ROOT / "examples/profiles/runtime-fixture/profile.yaml"
ENVIRONMENT = REPO_ROOT / "examples/environments/runtime-fixture.example.yaml"


def test_transition_persists_projection_marker_in_same_revision(tmp_path: Path) -> None:
    controller = OperationController(FileStore(tmp_path / ".rexecop"))
    operation = controller.plan(
        profile_path=PROFILE,
        environment_path=ENVIRONMENT,
        intent="inspect_fixture_state",
        target="fixture-target",
        mode="dry_run",
    )

    marker = operation.metadata["sclite_projection"]
    assert marker["status"] == "pending"
    assert marker["state"] == "planned"
    assert marker["operation_revision"] == operation.operation_revision


def test_projection_reconciliation_is_idempotent(tmp_path: Path) -> None:
    controller = OperationController(FileStore(tmp_path / ".rexecop"))
    operation = controller.plan(
        profile_path=PROFILE,
        environment_path=ENVIRONMENT,
        intent="inspect_fixture_state",
        target="fixture-target",
        mode="dry_run",
    )
    completed = controller.start(operation.id)
    marker = dict(completed.metadata["sclite_projection"])
    marker["status"] = "pending"
    completed.metadata["sclite_projection"] = marker
    controller.store.save_operation(completed)

    first = reconcile_pending_projections(controller)
    event_count = len(controller.store.list_evidence_events(operation.id))
    second = reconcile_pending_projections(controller)

    projected = controller.get_operation(operation.id)
    assert first == {"projected": [operation.id], "deferred": []}
    assert second == {"projected": [], "deferred": []}
    assert projected.metadata["sclite_projection"]["status"] == "projected"
    assert len(controller.store.list_evidence_events(operation.id)) == event_count
