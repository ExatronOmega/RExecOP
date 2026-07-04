from __future__ import annotations

from pathlib import Path
from typing import Any

from govengine import explain_policy_evaluation

from rexecop.action.surface import (
    _connector_steps,
    _non_claims,
    _resolve_context,
    _source_contracts,
)
from rexecop.catalog.digest import canonical_digest
from rexecop.catalog.service import compile_operation_descriptor
from rexecop.environment.sanitize import validate_no_inline_secrets
from rexecop.environment.targets import validate_operation_target
from rexecop.errors import RExecOpValidationError
from rexecop.policy.operation import build_operation_policy_request
from rexecop.policy.pack import compile_environment_policy_pack
from rexecop.workflow.contract import validate_workflow_contract
from rexecop.workflow.loader import load_workflow

ACTION_POLICY_IMPACT_SCHEMA = "rexecop.action_policy_impact.v0.1"
SUPPORTED_POLICY_IMPACT_MODES = frozenset(
    {"observe", "dry_run", "apply", "emergency_readonly", "recovery"}
)


def preview_action_policy_impact(
    intent: str,
    *,
    profile: str | Path | None = None,
    env: Path | None = None,
    catalog: Path | None = None,
    target: str | None = None,
    mode: str = "dry_run",
) -> dict[str, Any]:
    """Simulate GovEngine policy impact for one action without admission authority."""
    if env is None and not (catalog is not None and target is not None):
        raise RExecOpValidationError(
            "action policy-preview requires --env or --catalog with --target"
        )
    if not target:
        raise RExecOpValidationError("action policy-preview requires --target")
    if mode not in SUPPORTED_POLICY_IMPACT_MODES:
        raise RExecOpValidationError(f"unsupported mode: {mode}")

    context = _resolve_context(profile=profile, env=env, catalog=catalog, target=target)
    if context.environment is None:
        raise RExecOpValidationError("environment is required for action policy-preview")

    validate_no_inline_secrets(context.environment.as_dict())
    workflow = load_workflow(context.profile.resolve_workflow_path(intent))
    intent_meta = context.profile.intent_metadata(intent)
    action_binding = _action_binding(context.profile, intent, workflow)
    intent_modes = intent_meta.get("modes")
    if intent_meta.get("enforce_declared_modes") is True and (
        not isinstance(intent_modes, list) or mode not in intent_modes
    ):
        raise RExecOpValidationError(f"mode {mode} not declared for intent: {intent}")

    validate_operation_target(context.environment, target)
    validate_workflow_contract(workflow, context.environment, context.profile)
    connector_steps = _connector_steps(context, workflow)
    descriptor_digest = str(action_binding.get("operation_descriptor_digest") or "")
    source_contracts = _source_contracts(context, descriptor_digest)
    policy_pack = compile_environment_policy_pack(context.environment.policy_pack)
    if policy_pack is None:
        return {
            "schema": ACTION_POLICY_IMPACT_SCHEMA,
            "status": "skipped",
            "action": action_binding,
            "workflow": {
                "id": workflow.id,
                "mode": workflow.mode,
                "risk": workflow.risk,
                "shape_digests": {
                    str(step["id"]): str(step.get("shape_digest") or "")
                    for step in connector_steps
                    if step.get("shape_digest")
                },
            },
            "source_contracts": source_contracts,
            "target": target,
            "mode": mode,
            "policy_simulation": {
                "available": False,
                "reason": "environment policy_pack is not configured",
            },
            "non_claims": _policy_impact_non_claims(),
        }

    risk = str(intent_meta.get("risk") or workflow.risk)
    request = build_operation_policy_request(
        operation_id=f"action-policy-impact:{intent}",
        profile=context.profile.name,
        environment=context.environment,
        intent=intent,
        target=target,
        mode=mode,
        risk=risk,
    )
    explanation = explain_policy_evaluation(request, policy_pack)
    explanation_dict = explanation.as_dict()
    return {
        "schema": ACTION_POLICY_IMPACT_SCHEMA,
        "status": "blocked" if explanation_dict["status"] == "blocked" else "simulated",
        "action": action_binding,
        "workflow": {
            "id": workflow.id,
            "mode": workflow.mode,
            "risk": workflow.risk,
            "shape_digests": {
                str(step["id"]): str(step.get("shape_digest") or "")
                for step in connector_steps
                if step.get("shape_digest")
            },
        },
        "source_contracts": {
            **source_contracts,
            "policy_request_digest": "sha256:" + canonical_digest(request),
        },
        "target": target,
        "mode": mode,
        "risk": risk,
        "policy_simulation": {
            "available": True,
            "policy_id": policy_pack.policy_id,
            "policy_version": policy_pack.version,
            "simulation_status": explanation_dict["status"],
            "decision": explanation_dict["decision"],
            "reason_code": explanation_dict["reason_code"],
            "evaluation_path": explanation_dict["evaluation_path"],
            "explanation": explanation_dict,
        },
        "non_claims": _policy_impact_non_claims(),
    }


def _action_binding(profile: Any, intent: str, workflow: Any) -> dict[str, str]:
    try:
        operation = compile_operation_descriptor(profile, intent)
        return {
            "id": operation.id,
            "operation_descriptor_digest": operation.digest,
            "side_effect_class": operation.side_effect_class,
        }
    except RExecOpValidationError:
        intent_meta = profile.intent_metadata(intent)
        intent_digest = "sha256:" + canonical_digest(
            {
                "schema": "rexecop.action_intent_projection.v0.1",
                "intent": intent,
                "workflow_id": workflow.id,
                "risk": str(intent_meta.get("risk") or workflow.risk),
                "modes": list(intent_meta.get("modes") or []),
            }
        )
        return {
            "id": intent,
            "operation_descriptor_digest": "",
            "intent_projection_digest": intent_digest,
            "side_effect_class": "unknown",
        }


def _policy_impact_non_claims() -> list[str]:
    return _non_claims() + [
        "Policy simulation uses GovEngine explain only; it is not runtime admission.",
        "Policy simulation does not approve operators or run approval workflow.",
        "Policy simulation does not verify SCLite artifacts or host enforcement.",
        "Policy simulation does not expose raw request payload values.",
    ]