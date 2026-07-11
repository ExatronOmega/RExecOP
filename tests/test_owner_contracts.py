from __future__ import annotations

from rexecop.contracts.orchestration import (
    ORCHESTRATION_SCHEMA_RESOLVER,
    build_trigger_decision,
    verify_owner_artifact,
)


def _trigger() -> dict[str, object]:
    return {
        "decision_id": "trigger-1",
        "decision": "plan_operation",
        "reason": "matched:rule-1",
        "decided_at": "2026-07-11T00:00:00+00:00",
        "source": "test",
        "event": {
            "id": "event-1",
            "source": "tecrax",
            "type": "monitor.alert",
            "subject": "host:one",
            "occurred_at": "2026-07-11T00:00:00+00:00",
            "digest": "a" * 64,
            "payload_digest": "b" * 64,
            "dedupe_key": "event-1",
            "cooldown_key": "host:one",
        },
        "rule_set": {"id": "rules", "version": "1", "digest": "c" * 64},
        "rule": {"id": "rule-1", "digest": "d" * 64},
        "admission": {
            "request_digest": "sha256:" + "e" * 64,
            "admission_digest": "sha256:" + "f" * 64,
            "admission": {"allowed": True, "outcome": "allowed"},
        },
        "operation_id": "op-1",
        "domain_authority": "tecrax",
    }


def test_owner_contract_inventory_is_namespaced_and_stable() -> None:
    inventory = ORCHESTRATION_SCHEMA_RESOLVER.inventory()
    assert len(inventory) == 7
    assert all(item.schema_ref.startswith("rexecop.io/") for item in inventory)


def test_owner_bridge_preserves_canonical_v01_vector() -> None:
    kwargs = _trigger()
    current = build_trigger_decision(**kwargs)  # type: ignore[arg-type]
    assert current["artifact_type"] == "trigger_decision"
    assert current["schema_version"] == "v0.1"
    assert current["schema_ref"] == "schemas/trigger_decision.v0.1.schema.json"
    verify_owner_artifact(current, "trigger_decision")
