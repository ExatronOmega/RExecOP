from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sclite._json import VerificationLimits
from sclite.artifacts import artifact_sha256
from sclite.integrity import (
    ChainVerificationError,
    artifact_descriptor,
    build_artifact_chain_manifest,
)
from sclite.integrity.chain import _verify_artifact_chain_manifest_with_snapshot

from .registry import LEGACY_REF_TO_FAMILY, ORCHESTRATION_SCHEMA_RESOLVER, validate_artifact

OBSERVATION_SCHEMA_REF = "schemas/observation_envelope.v0.1.schema.json"
FINDING_SCHEMA_REF = "schemas/finding.v0.1.schema.json"
REACTION_PLAN_SCHEMA_REF = "schemas/reaction_plan.v0.1.schema.json"
ESCALATION_PROPOSAL_SCHEMA_REF = "schemas/escalation_proposal.v0.1.schema.json"
REACTION_CHAIN_ROLES = ("observation", "finding", "reaction_plan")


def _profile_ref(value: Mapping[str, Any]) -> dict[str, str]:
    return {key: str(value[key]) for key in ("id", "version", "digest")}


def _link(value: Mapping[str, Any]) -> dict[str, Any]:
    return {"descriptor": artifact_descriptor(value)}


def _validated(value: dict[str, Any], schema_ref: str) -> dict[str, Any]:
    validate_artifact(value, schema_ref)
    return value


def build_observation_envelope(
    *,
    observation_id: str,
    observed_at: str,
    profile_ref: Mapping[str, Any],
    operation_id: str,
    intent_id: str,
    target_id: str,
    facts: Mapping[str, Any],
) -> dict[str, Any]:
    return _validated(
        {
            "artifact_type": "observation_envelope",
            "schema_version": "v0.1",
            "schema_ref": OBSERVATION_SCHEMA_REF,
            "observation_id": observation_id,
            "observed_at": observed_at,
            "profile_ref": _profile_ref(profile_ref),
            "source": {
                "operation_id": operation_id,
                "intent_id": intent_id,
                "target_id": target_id,
            },
            "facts": dict(facts),
        },
        OBSERVATION_SCHEMA_REF,
    )


def build_finding(
    *,
    finding_id: str,
    created_at: str,
    profile_ref: Mapping[str, Any],
    kind: str,
    severity: str,
    summary: str,
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    return _validated(
        {
            "artifact_type": "finding",
            "schema_version": "v0.1",
            "schema_ref": FINDING_SCHEMA_REF,
            "finding_id": finding_id,
            "created_at": created_at,
            "profile_ref": _profile_ref(profile_ref),
            "taxonomy": {"kind": kind, "severity": severity},
            "summary": summary,
            "links": {"observation": _link(observation)},
        },
        FINDING_SCHEMA_REF,
    )


def build_reaction_plan(
    *,
    reaction_id: str,
    created_at: str,
    profile_ref: Mapping[str, Any],
    rule_id: str,
    rule_digest: str,
    outcome: str,
    intent_ref: str | None,
    child_operation_id: str | None,
    reason: str,
    depth: int,
    reaction_count: int,
    visited_rule_digests: Sequence[str],
    idempotency_key: str,
    admission_status: str,
    admission_decision: str | None,
    admission_decision_id: str | None,
    observation: Mapping[str, Any],
    finding: Mapping[str, Any],
) -> dict[str, Any]:
    return _validated(
        {
            "artifact_type": "reaction_plan",
            "schema_version": "v0.1",
            "schema_ref": REACTION_PLAN_SCHEMA_REF,
            "reaction_id": reaction_id,
            "created_at": created_at,
            "profile_ref": _profile_ref(profile_ref),
            "rule_ref": {"id": rule_id, "digest": rule_digest},
            "outcome": outcome,
            "intent_ref": intent_ref,
            "child_operation_id": child_operation_id,
            "reason": reason,
            "context": {
                "depth": depth,
                "reaction_count": reaction_count,
                "visited_rule_digests": list(visited_rule_digests),
                "idempotency_key": idempotency_key,
            },
            "admission": {
                "status": admission_status,
                "decision": admission_decision,
                "decision_id": admission_decision_id,
            },
            "links": {"observation": _link(observation), "finding": _link(finding)},
        },
        REACTION_PLAN_SCHEMA_REF,
    )


def validate_escalation_proposal(value: Mapping[str, Any]) -> None:
    validate_artifact(dict(value), ESCALATION_PROPOSAL_SCHEMA_REF)


def reaction_idempotency_key(
    *, profile_digest: str, observation: Mapping[str, Any], rule_digest: str, target_id: str
) -> str:
    return artifact_sha256(
        {
            "profile_digest": profile_digest,
            "observation_digest": artifact_descriptor(observation)["digest"],
            "rule_digest": rule_digest,
            "target_id": target_id,
        }
    )


def build_reaction_chain_manifest(
    *,
    reaction_id: str,
    created_at: str,
    observation: Mapping[str, Any],
    finding: Mapping[str, Any],
    reaction_plan: Mapping[str, Any],
    execution_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    artifacts = [
        {"role": "observation", "path": "01_observation.json", "value": observation},
        {"role": "finding", "path": "02_finding.json", "value": finding},
        {"role": "reaction_plan", "path": "03_reaction_plan.json", "value": reaction_plan},
    ]
    if execution_receipt is not None:
        artifacts.append(
            {
                "role": "execution_receipt",
                "path": "04_execution_receipt.json",
                "value": execution_receipt,
            }
        )
    return build_artifact_chain_manifest(
        artifacts,
        chain_id=f"reaction:{reaction_id}",
        created_at=created_at,
        profile="sclite-reaction-v0.1",
    )


def _bound_link(source: Mapping[str, Any], name: str, target: Mapping[str, Any]) -> bool:
    links = source.get("links")
    link = links.get(name) if isinstance(links, Mapping) else None
    descriptor = link.get("descriptor") if isinstance(link, Mapping) else None
    return descriptor == artifact_descriptor(target)


def verify_reaction_chain_manifest(
    manifest: Mapping[str, Any],
    *,
    root: Path,
    strict_jsonschema: bool = False,
    verification_limits: VerificationLimits | None = None,
) -> dict[str, Any]:
    result, snapshot = _verify_artifact_chain_manifest_with_snapshot(
        manifest,
        root=root,
        strict_jsonschema=strict_jsonschema,
        max_artifact_bytes=1_048_576,
        max_manifest_entries=4,
        verification_limits=verification_limits,
        schema_resolver=ORCHESTRATION_SCHEMA_RESOLVER,
        schema_resolver_refs=frozenset(LEGACY_REF_TO_FAMILY),
    )
    roles = tuple(result["checked_entries"])
    if roles not in {REACTION_CHAIN_ROLES, (*REACTION_CHAIN_ROLES, "execution_receipt")}:
        raise ChainVerificationError(f"reaction roles mismatch: {list(roles)}")
    try:
        observation = snapshot.artifacts_by_role["observation"].value
        finding = snapshot.artifacts_by_role["finding"].value
        plan = snapshot.artifacts_by_role["reaction_plan"].value
    except KeyError as exc:  # pragma: no cover - role validation above is the public failure path
        raise ChainVerificationError(f"reaction snapshot missing role: {exc.args[0]}") from exc
    if not _bound_link(finding, "observation", observation):
        raise ChainVerificationError("finding-observation digest mismatch")
    if not _bound_link(plan, "observation", observation):
        raise ChainVerificationError("reaction_plan-observation digest mismatch")
    if not _bound_link(plan, "finding", finding):
        raise ChainVerificationError("reaction_plan-finding digest mismatch")
    result["reaction_semantics"] = "passed"
    return result
