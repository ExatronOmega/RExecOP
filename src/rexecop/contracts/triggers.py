from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sclite.artifacts import artifact_sha256
from sclite.integrity import artifact_descriptor

from .registry import validate_artifact

TRIGGER_DECISION_SCHEMA_REF = "schemas/trigger_decision.v0.1.schema.json"
TRIGGER_DECISION_SCHEMA = "trigger_decision.v0.1"

TRIGGER_DECISIONS = {
    "plan_operation",
    "ignore",
    "escalate",
    "drop_duplicate",
    "cooldown_blocked",
}


def _sha256_ref(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("sha256:"):
        return text
    return f"sha256:{text}"


def _event_ref(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(value.get("id") or ""),
        "source": str(value.get("source") or ""),
        "type": str(value.get("type") or ""),
        "subject": str(value.get("subject") or ""),
        "occurred_at": str(value.get("occurred_at") or ""),
        "digest": _sha256_ref(value.get("digest")),
        "payload_digest": _sha256_ref(value.get("payload_digest")),
        "dedupe_key": str(value.get("dedupe_key") or ""),
        "cooldown_key": (
            None if value.get("cooldown_key") is None else str(value.get("cooldown_key") or "")
        ),
    }


def _rule_set_ref(value: Mapping[str, Any]) -> dict[str, str]:
    return {
        "id": str(value.get("id") or ""),
        "version": str(value.get("version") or ""),
        "digest": _sha256_ref(value.get("digest")),
    }


def _rule_ref(value: Mapping[str, Any] | None) -> dict[str, str] | None:
    if value is None:
        return None
    return {
        "id": str(value.get("id") or ""),
        "digest": _sha256_ref(value.get("digest")),
    }


def _admission_ref(value: Mapping[str, Any]) -> dict[str, Any]:
    admission = value.get("admission")
    if not isinstance(admission, Mapping):
        admission = {}
    return {
        "request_digest": _sha256_ref(value.get("request_digest")),
        "admission_digest": _sha256_ref(value.get("admission_digest")),
        "allowed": bool(admission.get("allowed", False)),
        "outcome": str(admission.get("outcome") or ""),
    }


def build_trigger_decision(
    *,
    decision_id: str,
    decision: str,
    reason: str,
    decided_at: str,
    source: str,
    event: Mapping[str, Any],
    rule_set: Mapping[str, Any],
    admission: Mapping[str, Any],
    domain_authority: str,
    rule: Mapping[str, Any] | None = None,
    operation_id: str | None = None,
) -> dict[str, Any]:
    """Build a truth-layer projection of a runtime trigger decision.

    SCLite records the bounded evidence shape only. It does not match trigger
    rules, authorize a plan, create operations, or interpret profile semantics.
    """
    artifact = {
        "artifact_type": "trigger_decision",
        "schema_version": "v0.1",
        "schema_ref": TRIGGER_DECISION_SCHEMA_REF,
        "decision_id": decision_id,
        "decision": decision,
        "reason": reason,
        "decided_at": decided_at,
        "source": source,
        "event": _event_ref(event),
        "rule_set": _rule_set_ref(rule_set),
        "rule": _rule_ref(rule),
        "admission": _admission_ref(admission),
        "operation_ref": {"operation_id": operation_id} if operation_id else None,
        "authority": {
            "truth_layer": "sclite",
            "planner": "rexecop",
            "policy_authority": "govengine",
            "domain_authority": domain_authority,
            "execution_authority": "rexecop",
        },
    }
    _validate_trigger_decision_semantics(artifact)
    return validate_trigger_decision(artifact)


def validate_trigger_decision(value: Mapping[str, Any]) -> dict[str, Any]:
    artifact = dict(value)
    validate_artifact(artifact, TRIGGER_DECISION_SCHEMA)
    _validate_trigger_decision_semantics(artifact)
    return artifact


def trigger_decision_digest(value: Mapping[str, Any]) -> str:
    return f"sha256:{artifact_sha256(dict(value))}"


def trigger_decision_descriptor(value: Mapping[str, Any]) -> dict[str, Any]:
    return artifact_descriptor(dict(value))


def _validate_trigger_decision_semantics(value: Mapping[str, Any]) -> None:
    decision = str(value.get("decision") or "")
    if decision not in TRIGGER_DECISIONS:
        raise ValueError(f"unsupported trigger decision: {decision}")
    operation_ref = value.get("operation_ref")
    admission = value.get("admission")
    if not isinstance(admission, Mapping):
        raise ValueError("trigger decision requires admission object")
    if decision == "plan_operation":
        if not isinstance(operation_ref, Mapping) or not str(
            operation_ref.get("operation_id") or ""
        ):
            raise ValueError("plan_operation trigger decision requires operation_ref")
        if admission.get("allowed") is not True:
            raise ValueError("plan_operation trigger decision requires allowed admission")
    elif operation_ref is not None:
        raise ValueError(f"{decision} trigger decision cannot carry operation_ref")
