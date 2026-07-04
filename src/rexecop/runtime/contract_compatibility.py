from __future__ import annotations

from typing import Any

from rexecop import __version__
from rexecop.execution.model import (
    EXECUTION_RECEIPT_SCHEMA_VERSION,
    EXECUTION_REQUEST_SCHEMA_VERSION,
)
from rexecop.execution.typed_spec import TYPED_EXECUTION_SCHEMA_VERSION

STACK_CONTRACT_COMPATIBILITY_SCHEMA = "rexecop.stack_contract_compatibility.v0.1"

REXECOP_RUNTIME_PROJECTIONS: tuple[dict[str, Any], ...] = (
    {
        "surface_id": "step_execution_spec",
        "owner": "rexecop.execution.typed_spec",
        "schema": "rexecop.step_execution_spec.v0.1",
        "supported_versions": (TYPED_EXECUTION_SCHEMA_VERSION,),
    },
    {
        "surface_id": "command_execution_spec",
        "owner": "rexecop.execution.typed_spec",
        "schema": "rexecop.command_execution_spec.v0.1",
        "supported_versions": (TYPED_EXECUTION_SCHEMA_VERSION,),
    },
    {
        "surface_id": "http_action_execution_spec",
        "owner": "rexecop.execution.typed_spec",
        "schema": "rexecop.http_action_execution_spec.v0.1",
        "supported_versions": (TYPED_EXECUTION_SCHEMA_VERSION,),
    },
    {
        "surface_id": "execution_request",
        "owner": "rexecop.execution.model",
        "schema": "rexecop.execution_request.v0.2",
        "supported_versions": (EXECUTION_REQUEST_SCHEMA_VERSION,),
    },
    {
        "surface_id": "execution_receipt",
        "owner": "rexecop.execution.model",
        "schema": "rexecop.execution_receipt.v0.2",
        "supported_versions": (EXECUTION_RECEIPT_SCHEMA_VERSION,),
    },
    {
        "surface_id": "runtime_manifest",
        "owner": "rexecop.runtime.init",
        "schema": "rexecop.runtime_manifest.v0.1",
        "supported_versions": ("v0.1",),
    },
    {
        "surface_id": "doctor_report",
        "owner": "rexecop.runtime.doctor",
        "schema": "rexecop.doctor_report.v0.1",
        "supported_versions": ("v0.1",),
    },
)

REXECOP_EXPECTED_GOVENGINE_CONTRACTS: tuple[dict[str, str], ...] = (
    {"surface_id": "policy_request", "schema_version": "v0.1"},
    {"surface_id": "policy_verdict", "schema_version": "v0.1"},
    {"surface_id": "policy_enforcement_plan", "schema_version": "v0.1"},
    {"surface_id": "runtime_control_projection", "schema_version": "v0.1"},
    {"surface_id": "trigger_planning_request", "schema_version": "v0.1"},
    {"surface_id": "supervisor_action_request", "schema_version": "v0.1"},
    {"surface_id": "typed_execution_governance_request", "schema_version": "v0.1"},
    {"surface_id": "typed_execution_governance_projection", "schema_version": "v0.1"},
    {"surface_id": "typed_execution_stack_compatibility", "schema_version": "v0.1"},
    {"surface_id": "typed_execution_control_catalog", "schema_version": "v0.1"},
)


def rexecop_runtime_projection_matrix() -> dict[str, Any]:
    return {
        "schema": STACK_CONTRACT_COMPATIBILITY_SCHEMA,
        "rexecop_version": __version__,
        "projections": [dict(item) for item in REXECOP_RUNTIME_PROJECTIONS],
    }


def build_govengine_contract_compatibility_request(
    *,
    request_id: str = "rexecop-govengine-contracts",
) -> dict[str, Any]:
    return {
        "schema_version": "v0.1",
        "request_id": request_id,
        "consumer": "rexecop",
        "consumer_version": __version__,
        "declared_contracts": [dict(item) for item in REXECOP_EXPECTED_GOVENGINE_CONTRACTS],
    }


def evaluate_govengine_contract_compatibility(
    *,
    request_id: str = "rexecop-govengine-contracts",
) -> dict[str, Any]:
    from govengine import evaluate_contract_compatibility, supported_contract_report

    request = build_govengine_contract_compatibility_request(request_id=request_id)
    report = evaluate_contract_compatibility(request)
    catalog = supported_contract_report()
    payload = report.as_dict()
    return {
        "schema": STACK_CONTRACT_COMPATIBILITY_SCHEMA,
        "status": payload["status"],
        "request_id": payload["request_id"],
        "report_digest": payload["report_digest"],
        "govengine_version": payload["govengine_version"],
        "matched_contracts": payload["matched_contracts"],
        "unsupported_contracts": payload["unsupported_contracts"],
        "missing_contracts": payload["missing_contracts"],
        "blockers": payload["blockers"],
        "govengine_contract_catalog": catalog,
        "rexecop_runtime_projections": rexecop_runtime_projection_matrix(),
        "compatibility": payload,
        "non_claims": list(payload["non_claims"]),
    }