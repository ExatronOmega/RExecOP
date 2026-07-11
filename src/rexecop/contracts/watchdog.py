from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sclite.artifacts import artifact_sha256
from sclite.integrity import artifact_descriptor

from .registry import validate_artifact

WATCHDOG_DECISION_SCHEMA_REF = "schemas/watchdog_decision.v0.1.schema.json"
WATCHDOG_DECISION_SCHEMA = "watchdog_decision.v0.1"

WATCHDOG_DECISIONS = {
    "record_health",
    "renew_lease",
    "mark_stale",
    "move_to_dead_letter",
    "retry_later",
    "escalate_operator",
    "block_autostart",
}


def _sha256_ref(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("sha256:"):
        return text
    return f"sha256:{text}"


def _observation_ref(value: Mapping[str, Any]) -> dict[str, str]:
    return {
        "record_id": str(value.get("record_id") or ""),
        "schema": str(value.get("schema") or ""),
        "observation": str(value.get("observation") or ""),
        "observed_at": str(value.get("observed_at") or ""),
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


def _affected_ref(value: Mapping[str, Any] | None) -> dict[str, str | None]:
    raw = value or {}
    return {
        "operation_id": _nullable_str(raw.get("operation_id")),
        "event_id": _nullable_str(raw.get("event_id")),
        "trigger_id": _nullable_str(raw.get("trigger_id")),
        "inbox_item_name": _nullable_str(raw.get("inbox_item_name")),
    }


def build_watchdog_decision(
    *,
    decision_id: str,
    decision: str,
    reason: str,
    decided_at: str,
    source: str,
    observation: Mapping[str, Any],
    admission: Mapping[str, Any],
    domain_authority: str,
    affected: Mapping[str, Any] | None = None,
    manual_recovery: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a bounded truth-layer projection of a runner watchdog decision.

    SCLite records the decision shape only. It does not supervise workers,
    retry operations, authorize recovery, inspect infrastructure health, or
    interpret profile/domain semantics.
    """
    artifact = {
        "artifact_type": "watchdog_decision",
        "schema_version": "v0.1",
        "schema_ref": WATCHDOG_DECISION_SCHEMA_REF,
        "decision_id": decision_id,
        "decision": decision,
        "reason": reason,
        "decided_at": decided_at,
        "source": source,
        "observation": _observation_ref(observation),
        "admission": _admission_ref(admission),
        "affected": _affected_ref(affected),
        "authority": {
            "truth_layer": "sclite",
            "supervisor": "rexecop",
            "policy_authority": "govengine",
            "domain_authority": domain_authority,
            "execution_authority": "rexecop",
        },
        "non_claims": [
            "sclite_does_not_supervise_runtime",
            "sclite_does_not_authorize_recovery",
            "sclite_does_not_interpret_domain_health",
        ],
    }
    if manual_recovery is not None:
        artifact["manual_recovery"] = _manual_recovery_ref(manual_recovery)
    _validate_watchdog_decision_semantics(artifact)
    return validate_watchdog_decision(artifact)


def validate_watchdog_decision(value: Mapping[str, Any]) -> dict[str, Any]:
    artifact = dict(value)
    validate_artifact(artifact, WATCHDOG_DECISION_SCHEMA)
    _validate_watchdog_decision_semantics(artifact)
    return artifact


def watchdog_decision_digest(value: Mapping[str, Any]) -> str:
    return f"sha256:{artifact_sha256(dict(value))}"


def watchdog_decision_descriptor(value: Mapping[str, Any]) -> dict[str, Any]:
    return artifact_descriptor(dict(value))


def _validate_watchdog_decision_semantics(value: Mapping[str, Any]) -> None:
    decision = str(value.get("decision") or "")
    if decision not in WATCHDOG_DECISIONS:
        raise ValueError(f"unsupported watchdog decision: {decision}")
    admission = value.get("admission")
    if not isinstance(admission, Mapping):
        raise ValueError("watchdog decision requires admission object")
    if decision in {"move_to_dead_letter", "retry_later", "block_autostart"}:
        if admission.get("allowed") is not True:
            raise ValueError(f"{decision} watchdog decision requires allowed admission")
    if decision in {"renew_lease", "mark_stale", "escalate_operator"}:
        if admission.get("allowed") is not True:
            raise ValueError(f"{decision} watchdog decision requires allowed admission")
        manual = value.get("manual_recovery")
        if not isinstance(manual, Mapping):
            raise ValueError(f"{decision} watchdog decision requires manual_recovery")
        if not str(manual.get("actor_ref") or ""):
            raise ValueError(f"{decision} watchdog decision requires actor_ref")
        if not str(manual.get("scope") or ""):
            raise ValueError(f"{decision} watchdog decision requires scope")
    affected = value.get("affected")
    if not isinstance(affected, Mapping):
        raise ValueError("watchdog decision requires affected object")
    if decision == "block_autostart" and not str(affected.get("operation_id") or ""):
        raise ValueError("block_autostart watchdog decision requires operation_id")
    if decision in {"move_to_dead_letter", "retry_later"} and not str(
        affected.get("inbox_item_name") or ""
    ):
        raise ValueError(f"{decision} watchdog decision requires inbox_item_name")


def _nullable_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _manual_recovery_ref(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "actor_ref": str(value.get("actor_ref") or ""),
        "scope": str(value.get("scope") or ""),
        "human_signoff": bool(value.get("human_signoff", False)),
        "reason": str(value.get("reason") or ""),
    }
