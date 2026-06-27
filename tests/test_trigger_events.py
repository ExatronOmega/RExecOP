from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from rexecop.errors import RExecOpValidationError
from rexecop.operation.controller import OperationController
from rexecop.operation.state import OperationState
from rexecop.runtime_ops.worker import run_worker
from rexecop.storage.file_store import FileStore
from rexecop.triggers.service import TriggerService

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PROFILE = ROOT / "examples/profiles/runtime-fixture"
POLICY_ENV = ROOT / "examples/environments/runtime-fixture.policy.example.yaml"
NOW = datetime(2026, 6, 28, 12, 0, 0, tzinfo=UTC)


def _profile(tmp_path: Path) -> Path:
    root = tmp_path / "runtime_fixture"
    shutil.copytree(SOURCE_PROFILE, root)
    triggers = root / "triggers"
    triggers.mkdir()
    (triggers / "trigger_rules.yaml").write_text(
        yaml.safe_dump(
            {
                "trigger_rules": {
                    "id": "fixture.triggers",
                    "version": "0.1",
                    "rules": [
                        {
                            "id": "fixture.degraded.inspect",
                            "priority": 10,
                            "event_type": "fixture.state_observed",
                            "when": [
                                {
                                    "path": "payload.status",
                                    "operator": "equals",
                                    "value": "degraded",
                                }
                            ],
                            "decision": "plan_operation",
                            "operation": {
                                "intent": "inspect_fixture_state",
                                "target": "fixture-target",
                                "mode": "dry_run",
                            },
                            "cooldown_seconds": 60,
                        },
                        {
                            "id": "fixture.noise.ignore",
                            "priority": 20,
                            "event_type": "fixture.state_observed",
                            "when": [
                                {
                                    "path": "payload.status",
                                    "operator": "equals",
                                    "value": "noise",
                                }
                            ],
                            "decision": "ignore",
                        },
                    ],
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return root


def _event(
    *,
    event_id: str = "evt-1",
    status: str = "degraded",
    subject: str = "fixture-target",
    occurred_at: datetime = NOW,
) -> dict:
    return {
        "id": event_id,
        "source": "fixture-source",
        "type": "fixture.state_observed",
        "subject": subject,
        "occurred_at": occurred_at.isoformat(),
        "payload": {"status": status},
        "rule_set": "fixture.triggers",
    }


def test_trigger_event_plans_operation_and_records_decision_evidence(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    store = FileStore(tmp_path / "runtime")
    controller = OperationController(store=store)

    decision = TriggerService(controller).process_event(
        profile_path=profile,
        environment_path=POLICY_ENV,
        event_payload=_event(),
        now=NOW,
        source="test",
    )

    assert decision["decision"] == "plan_operation"
    operation_id = decision["operation_id"]
    assert isinstance(operation_id, str)
    operation = store.load_operation(operation_id)
    assert operation.state == OperationState.PLANNED.value
    assert operation.intent == "inspect_fixture_state"
    assert operation.metadata["trigger_decision"]["decision_id"] == decision["decision_id"]
    assert operation.metadata["trigger_decision"]["payload_digest"] == (
        decision["event"]["payload_digest"]
    )
    events = store.list_evidence_events(operation_id)
    assert [event["event_type"] for event in events if event["event_type"] == "operation_triggered"]


def test_trigger_event_dedupes_by_event_identity_without_new_operation(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    store = FileStore(tmp_path / "runtime")
    controller = OperationController(store=store)
    service = TriggerService(controller)

    first = service.process_event(
        profile_path=profile,
        environment_path=POLICY_ENV,
        event_payload=_event(),
        now=NOW,
        source="test",
    )
    second = service.process_event(
        profile_path=profile,
        environment_path=POLICY_ENV,
        event_payload=_event(),
        now=NOW + timedelta(seconds=1),
        source="test",
    )

    assert first["decision"] == "plan_operation"
    assert second["decision"] == "drop_duplicate"
    assert [operation.id for operation in store.list_operations()] == [first["operation_id"]]


def test_trigger_event_cooldown_blocks_distinct_event_for_same_subject(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    store = FileStore(tmp_path / "runtime")
    controller = OperationController(store=store)
    service = TriggerService(controller)

    first = service.process_event(
        profile_path=profile,
        environment_path=POLICY_ENV,
        event_payload=_event(event_id="evt-1"),
        now=NOW,
        source="test",
    )
    second = service.process_event(
        profile_path=profile,
        environment_path=POLICY_ENV,
        event_payload=_event(event_id="evt-2"),
        now=NOW + timedelta(seconds=30),
        source="test",
    )

    assert first["decision"] == "plan_operation"
    assert second["decision"] == "cooldown_blocked"
    assert second["event"]["cooldown_key"] == "fixture.degraded.inspect:fixture-target"
    assert [operation.id for operation in store.list_operations()] == [first["operation_id"]]


def test_trigger_event_rejects_unsafe_timestamp_skew(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    service = TriggerService(OperationController(store=FileStore(tmp_path / "runtime")))

    with pytest.raises(RExecOpValidationError, match="too far in the future"):
        service.process_event(
            profile_path=profile,
            environment_path=POLICY_ENV,
            event_payload=_event(occurred_at=NOW + timedelta(minutes=10)),
            now=NOW,
            source="test",
        )


def test_worker_processes_trigger_event_inbox_without_autostart(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    store = FileStore(tmp_path / "runtime")
    controller = OperationController(store=store)
    inbox = store.root / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "event-1.json").write_text(
        json.dumps(
                {
                    "profile": str(profile),
                    "env": str(POLICY_ENV),
                    "trigger_event": _event(occurred_at=datetime.now(UTC)),
                }
            ),
        encoding="utf-8",
    )

    started = run_worker(controller, once=True, watch_inbox=True)

    assert started == []
    assert not list(inbox.glob("event-1.json"))
    operations = store.list_operations()
    assert len(operations) == 1
    assert operations[0].state == OperationState.PLANNED.value
