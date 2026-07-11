from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sclite.artifacts import artifact_sha256
from sclite.integrity import ChainVerificationError

from .registry import validate_artifact

AUTOMATION_CHAIN_SCHEMA = "automation_chain.v0.1"
AUTOMATION_CHAIN_SCHEMA_REF = "schemas/automation_chain.v0.1.schema.json"
AUTOMATION_CHAIN_ARTIFACT_TYPE = "automation_chain"
AUTOMATION_CHAIN_NON_CLAIMS = (
    "Does not execute operations, schedule work, or authorize child operations.",
    "Does not replace GovEngine admission for automation transitions.",
    "Does not store raw evidence, connector payloads, secrets, or private topology.",
    "Does not make LLM proposals executable authority.",
    "Does not verify DAG shape, roots, connectivity, computed depth, transitions, "
    "recovery execution, checkpoints, or admission authenticity.",
)
CHILD_EDGE_TYPES = {"admitted_child", "spawned_child"}
REACTION_NODE_TYPES = {"reaction_plan"}
DIGEST_PREFIX = "sha256:"


def build_automation_chain(
    *,
    chain_id: str,
    created_at: str,
    profile_ref: Mapping[str, Any],
    source_operation_id: str,
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    controls: Mapping[str, Any] | None = None,
    recovery: Mapping[str, Any] | None = None,
    compatibility: Mapping[str, Any] | None = None,
    non_claims: Sequence[str] = AUTOMATION_CHAIN_NON_CLAIMS,
) -> dict[str, Any]:
    artifact = {
        "artifact_type": AUTOMATION_CHAIN_ARTIFACT_TYPE,
        "schema_version": "v0.1",
        "schema_ref": AUTOMATION_CHAIN_SCHEMA_REF,
        "chain_id": chain_id,
        "created_at": created_at,
        "profile_ref": _profile_ref(profile_ref),
        "source_operation_id": source_operation_id,
        "controls": _controls(controls),
        "recovery": _recovery(recovery),
        "compatibility": _compatibility(compatibility),
        "nodes": [dict(node) for node in nodes],
        "edges": [dict(edge) for edge in edges],
        "non_claims": list(non_claims),
    }
    validate_automation_chain(artifact)
    return artifact


def automation_chain_digest(value: Mapping[str, Any]) -> str:
    return artifact_sha256(dict(value))


def validate_automation_chain(
    value: Mapping[str, Any],
    *,
    strict_jsonschema: bool = False,
) -> None:
    artifact = dict(value)
    validate_artifact(
        artifact,
        AUTOMATION_CHAIN_SCHEMA,
        strict_jsonschema=strict_jsonschema,
    )
    _verify_invariants(artifact)


def verify_automation_chain(
    value: Mapping[str, Any],
    *,
    strict_jsonschema: bool = False,
) -> dict[str, Any]:
    artifact = dict(value)
    validate_automation_chain(artifact, strict_jsonschema=strict_jsonschema)
    nodes = _nodes(artifact)
    edges = _edges(artifact)
    reaction_count = sum(
        1 for node in nodes.values() if str(node.get("node_type") or "") in REACTION_NODE_TYPES
    )
    child_edge_count = sum(
        1 for edge in edges.values() if str(edge.get("edge_type") or "") in CHILD_EDGE_TYPES
    )
    checked = [
        "schema_shape",
        "unique_node_ids",
        "unique_edge_ids",
        "edge_endpoints_exist",
        "node_count_within_declared_budget",
        "declared_depth_values_within_declared_budget",
        "reaction_node_count_within_declared_budget",
        "source_operation_id_represented",
        "child_edge_idempotency_key_present",
        "child_admission_reference_shape",
        "llm_proposal_shape",
    ]
    not_checked = [
        "graph_acyclicity",
        "graph_roots",
        "graph_connectivity",
        "computed_depth",
        "transition_semantics",
        "recovery_semantics",
        "checkpoint_semantics",
        "global_idempotency",
        "admission_authenticity",
        "admission_decision_binding",
    ]
    host_asserted = [
        "node_depth",
        "edge_depth",
        "node_status",
        "controls",
        "recovery",
        "compatibility",
        "admission_status",
        "admission_owner_layer",
    ]
    return {
        "status": "passed",
        "schema_ref": AUTOMATION_CHAIN_SCHEMA_REF,
        "chain_id": str(artifact.get("chain_id") or ""),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "reaction_count": reaction_count,
        "child_edge_count": child_edge_count,
        "max_depth": _max_depth(nodes, edges),
        "max_depth_semantics": "host_asserted_not_computed",
        "root_chain_digest": automation_chain_digest(artifact),
        "verification_posture": "automation_bridge_partial_v0.1",
        "checked": checked,
        "not_checked": not_checked,
        "host_asserted": host_asserted,
        "requires_external_verification": {
            "graph_and_runtime_semantics": "rexecop",
            "recovery_and_checkpoint_semantics": "rexecop",
            "admission_authenticity_and_decision_binding": "govengine",
            "profile_transition_semantics": "profile",
        },
        "invariants": checked,
    }


def automation_owner_migration_contract() -> dict[str, Any]:
    """Return the frozen owner split for migration away from the bridge."""

    return {
        "schema": "sclite.automation_owner_migration.v0.1",
        "bridge_owner": "sclite",
        "bridge_checks": [
            "shape",
            "referential_endpoints",
            "declared_resource_budgets",
            "source_reference_presence",
            "llm_proposal_shape",
            "child_reference_shape",
        ],
        "external_owners": {
            "rexecop": [
                "dag_roots_connectivity",
                "computed_depth",
                "transition_semantics",
                "global_idempotency",
                "recovery_and_checkpoints",
            ],
            "govengine": ["admission_authenticity", "admission_decision_binding"],
            "profile": ["profile_transition_semantics"],
        },
        "migration_target": "owner adapters in 1.3.x; bridge removal no earlier than 2.0",
    }


def automation_node(
    *,
    node_id: str,
    node_type: str,
    depth: int,
    status: str,
    owner_layer: str,
    authority_level: str,
    operation_id: str = "",
    artifact_ref: Mapping[str, Any] | None = None,
    labels: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "node_type": node_type,
        "depth": depth,
        "status": status,
        "owner_layer": owner_layer,
        "authority_level": authority_level,
        "operation_id": operation_id,
        "artifact_ref": _artifact_ref(artifact_ref),
        "labels": list(labels),
    }


def automation_edge(
    *,
    edge_id: str,
    edge_type: str,
    from_node: str,
    to_node: str,
    depth: int,
    idempotency_key: str = "",
    admission: Mapping[str, Any] | None = None,
    labels: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "edge_id": edge_id,
        "edge_type": edge_type,
        "from_node": from_node,
        "to_node": to_node,
        "depth": depth,
        "idempotency_key": idempotency_key,
        "admission": _admission(admission),
        "labels": list(labels),
    }


def _profile_ref(value: Mapping[str, Any]) -> dict[str, str]:
    return {key: str(value[key]) for key in ("id", "version", "digest")}


def _controls(value: Mapping[str, Any] | None) -> dict[str, Any]:
    result = {
        "max_depth": 3,
        "max_nodes": 64,
        "max_reactions": 16,
        "requires_govengine_admission": True,
        "requires_profile_transition": True,
        "allowed_child_intent_classes": [],
        "llm_may_execute": False,
    }
    if value is not None:
        result.update(dict(value))
    return result


def _recovery(value: Mapping[str, Any] | None) -> dict[str, Any]:
    result = {
        "append_mode": "append_only",
        "idempotency_scope": "chain_edge",
        "duplicate_child_policy": "reuse_existing_child",
        "replay_policy": "verify_before_append",
        "checkpoint_required": True,
    }
    if value is not None:
        result.update(dict(value))
    return result


def _compatibility(value: Mapping[str, Any] | None) -> dict[str, bool]:
    result = {
        "reaction_chain_v0_1_subset": False,
        "single_step_reaction_compatible": True,
    }
    if value is not None:
        result.update({key: bool(item) for key, item in value.items()})
    return result


def _artifact_ref(value: Mapping[str, Any] | None) -> dict[str, str]:
    if value is None:
        return {"artifact_type": "", "schema_version": "", "schema_ref": "", "digest": ""}
    return {
        "artifact_type": str(value.get("artifact_type") or ""),
        "schema_version": str(value.get("schema_version") or ""),
        "schema_ref": str(value.get("schema_ref") or ""),
        "digest": str(value.get("digest") or ""),
    }


def _admission(value: Mapping[str, Any] | None) -> dict[str, str]:
    if value is None:
        return {
            "status": "not_applicable",
            "decision_id": "",
            "decision_digest": "",
            "owner_layer": "sclite",
        }
    return {
        "status": str(value.get("status") or "not_applicable"),
        "decision_id": str(value.get("decision_id") or ""),
        "decision_digest": str(value.get("decision_digest") or ""),
        "owner_layer": str(value.get("owner_layer") or "sclite"),
    }


def _nodes(value: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for node in value.get("nodes") or []:
        if not isinstance(node, Mapping):
            raise ChainVerificationError("automation chain node is not an object")
        node_id = str(node.get("node_id") or "")
        if not node_id:
            raise ChainVerificationError("automation chain node missing node_id")
        if node_id in result:
            raise ChainVerificationError(f"duplicate automation node id: {node_id}")
        result[node_id] = node
    return result


def _edges(value: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for edge in value.get("edges") or []:
        if not isinstance(edge, Mapping):
            raise ChainVerificationError("automation chain edge is not an object")
        edge_id = str(edge.get("edge_id") or "")
        if not edge_id:
            raise ChainVerificationError("automation chain edge missing edge_id")
        if edge_id in result:
            raise ChainVerificationError(f"duplicate automation edge id: {edge_id}")
        result[edge_id] = edge
    return result


def _max_depth(
    nodes: Mapping[str, Mapping[str, Any]],
    edges: Mapping[str, Mapping[str, Any]],
) -> int:
    depths = [int(node.get("depth") or 0) for node in nodes.values()]
    depths.extend(int(edge.get("depth") or 0) for edge in edges.values())
    return max(depths or [0])


def _verify_invariants(value: Mapping[str, Any]) -> None:
    nodes = _nodes(value)
    edges = _edges(value)
    controls = value.get("controls")
    if not isinstance(controls, Mapping):
        raise ChainVerificationError("automation chain missing controls")
    max_nodes = int(controls.get("max_nodes") or 0)
    max_depth = int(controls.get("max_depth") or 0)
    max_reactions = int(controls.get("max_reactions") or 0)
    if len(nodes) > max_nodes:
        raise ChainVerificationError("automation chain node budget exceeded")
    if _max_depth(nodes, edges) > max_depth:
        raise ChainVerificationError("automation chain max_depth exceeded")
    reaction_count = sum(
        1 for node in nodes.values() if str(node.get("node_type") or "") in REACTION_NODE_TYPES
    )
    if reaction_count > max_reactions:
        raise ChainVerificationError("automation chain reaction budget exceeded")
    source_operation_id = str(value.get("source_operation_id") or "")
    if not any(
        str(node.get("operation_id") or "") == source_operation_id for node in nodes.values()
    ):
        raise ChainVerificationError("automation chain source_operation_id is not represented")
    for node in nodes.values():
        _verify_node(node)
    for edge in edges.values():
        _verify_edge(edge, nodes, controls)


def _verify_node(node: Mapping[str, Any]) -> None:
    owner_layer = str(node.get("owner_layer") or "")
    authority_level = str(node.get("authority_level") or "")
    node_type = str(node.get("node_type") or "")
    if owner_layer == "llm" and authority_level != "proposal":
        raise ChainVerificationError("llm automation nodes must be proposal-only")
    if owner_layer == "llm" and node_type != "escalation_proposal":
        raise ChainVerificationError("llm automation nodes must be escalation proposals")


def _verify_edge(
    edge: Mapping[str, Any],
    nodes: Mapping[str, Mapping[str, Any]],
    controls: Mapping[str, Any],
) -> None:
    from_node = str(edge.get("from_node") or "")
    to_node = str(edge.get("to_node") or "")
    edge_type = str(edge.get("edge_type") or "")
    if from_node not in nodes:
        raise ChainVerificationError(f"automation edge references unknown from_node: {from_node}")
    if to_node not in nodes:
        raise ChainVerificationError(f"automation edge references unknown to_node: {to_node}")
    if edge_type not in CHILD_EDGE_TYPES:
        return
    if not str(edge.get("idempotency_key") or ""):
        raise ChainVerificationError("automation child edge missing idempotency_key")
    admission = edge.get("admission")
    if not isinstance(admission, Mapping):
        raise ChainVerificationError("automation child edge missing admission")
    if bool(controls.get("requires_govengine_admission")):
        if not str(admission.get("decision_id") or ""):
            raise ChainVerificationError("automation child edge missing admission decision_id")
        if not _is_digest(str(admission.get("decision_digest") or "")):
            raise ChainVerificationError("automation child edge missing admission decision_digest")


def _is_digest(value: str) -> bool:
    raw = value[len(DIGEST_PREFIX) :] if value.startswith(DIGEST_PREFIX) else value
    return len(raw) == 64 and all(char in "0123456789abcdef" for char in raw.lower())
