from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from rexecop.catalog.digest import canonical_digest, profile_snapshot_digest, yaml_document_digest
from rexecop.catalog.service import (
    CatalogService,
    compile_operation_descriptor,
    compile_profile_operations,
)
from rexecop.connectors.action_shape import validate_http_action_shape
from rexecop.environment.loader import load_environment
from rexecop.environment.model import Environment
from rexecop.environment.sanitize import validate_no_inline_secrets
from rexecop.errors import RExecOpValidationError
from rexecop.profile.loader import LoadedProfile, load_profile
from rexecop.profile.resolver import resolve_profile_path
from rexecop.secrets.doctor import collect_secret_ref_bindings
from rexecop.workflow.contract import validate_workflow_contract
from rexecop.workflow.loader import load_workflow

ACTION_LIST_SCHEMA = "rexecop.action_list.v0.1"
ACTION_SHOW_SCHEMA = "rexecop.action_show.v0.1"
ACTION_VALIDATE_SCHEMA = "rexecop.action_validate.v0.1"


class _ActionContext:
    def __init__(
        self,
        *,
        profile: LoadedProfile,
        environment: Environment | None,
        profile_path: Path,
        environment_path: Path | None,
        catalog_path: Path | None,
        target: str | None,
    ) -> None:
        self.profile = profile
        self.environment = environment
        self.profile_path = profile_path
        self.environment_path = environment_path
        self.catalog_path = catalog_path
        self.target = target


def list_actions(
    *,
    profile: str | Path | None = None,
    env: Path | None = None,
    catalog: Path | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    """List profile-owned actions without backend IO or admission."""
    context = _resolve_context(profile=profile, env=env, catalog=catalog, target=target)
    return {
        "schema": ACTION_LIST_SCHEMA,
        "profile": _profile_summary(context.profile),
        "environment": _environment_summary(context.environment, context.environment_path),
        "catalog": _catalog_summary(context),
        "actions": [
            _action_summary(context, operation_id)
            for operation_id in _operation_ids(context.profile)
        ],
        "non_claims": _non_claims(),
    }


def show_action(
    intent: str,
    *,
    profile: str | Path | None = None,
    env: Path | None = None,
    catalog: Path | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    """Describe one profile-owned action and its redacted operator requirements."""
    context = _resolve_context(profile=profile, env=env, catalog=catalog, target=target)
    operation = compile_operation_descriptor(context.profile, intent)
    workflow = load_workflow(context.profile.resolve_workflow_path(intent))
    connector_steps = _connector_steps(context, workflow)
    return {
        "schema": ACTION_SHOW_SCHEMA,
        "action": operation.as_dict(),
        "workflow": {
            "id": workflow.id,
            "mode": workflow.mode,
            "risk": workflow.risk,
            "connector_step_count": len(connector_steps),
            "connector_steps": connector_steps,
        },
        "source_contracts": _source_contracts(context, operation.digest),
        "required_refs": _required_refs(context, workflow),
        "template_provenance": {
            "available": False,
            "reason": "M5 list/show/validate does not use action templates.",
        },
        "backend_constraints": _backend_constraints(connector_steps),
        "applicability": _applicability(context, operation.id),
        "non_claims": _non_claims(),
    }


def validate_actions(
    *,
    profile: str | Path | None = None,
    env: Path | None = None,
    catalog: Path | None = None,
    target: str | None = None,
    intent: str | None = None,
) -> dict[str, Any]:
    """Validate action metadata and env bindings without backend IO."""
    if env is None and not (catalog is not None and target is not None):
        raise RExecOpValidationError("action validate requires --env or --catalog with --target")
    context = _resolve_context(profile=profile, env=env, catalog=catalog, target=target)
    operation_ids = [intent] if intent else _operation_ids(context.profile)
    checks = [_validate_one(context, operation_id) for operation_id in operation_ids]
    blockers = [
        f"{check['action']}:{item['id']}"
        for check in checks
        for item in check["checks"]
        if item["status"] == "failed"
    ]
    return {
        "schema": ACTION_VALIDATE_SCHEMA,
        "status": "failed" if blockers else "passed",
        "profile": _profile_summary(context.profile),
        "environment": _environment_summary(context.environment, context.environment_path),
        "catalog": _catalog_summary(context),
        "actions_checked": operation_ids,
        "checks": checks,
        "blockers": blockers,
        "non_claims": _non_claims(),
    }


def _resolve_context(
    *,
    profile: str | Path | None,
    env: Path | None,
    catalog: Path | None,
    target: str | None,
) -> _ActionContext:
    profile_path: Path | None = None
    environment_path = env
    if catalog is not None and target is not None:
        target_descriptor = CatalogService(catalog).get_target(target)
        profile_path = target_descriptor.profile_path
        environment_path = environment_path or target_descriptor.environment_path
    if profile is not None:
        profile_path = resolve_profile_path(profile)
    if profile_path is None:
        raise RExecOpValidationError(
            "--profile is required unless --catalog and --target resolve it"
        )
    loaded = load_profile(profile_path)
    environment = load_environment(environment_path) if environment_path is not None else None
    if environment is not None and environment.profile and environment.profile != loaded.name:
        raise RExecOpValidationError(
            f"environment profile mismatch: expected {loaded.name}, got {environment.profile}"
        )
    return _ActionContext(
        profile=loaded,
        environment=environment,
        profile_path=profile_path,
        environment_path=environment_path,
        catalog_path=catalog,
        target=target,
    )


def _operation_ids(profile: LoadedProfile) -> list[str]:
    return [item.id for item in compile_profile_operations(profile)]


def _action_summary(context: _ActionContext, operation_id: str) -> dict[str, Any]:
    operation = compile_operation_descriptor(context.profile, operation_id)
    workflow = load_workflow(context.profile.resolve_workflow_path(operation_id))
    connector_steps = _connector_steps(context, workflow)
    return {
        "id": operation.id,
        "title": operation.title,
        "modes": list(operation.modes),
        "backend_classes": sorted(
            {
                str(step.get("backend_class") or "")
                for step in connector_steps
                if step.get("backend_class")
            }
        ),
        "side_effect_class": operation.side_effect_class,
        "operation_descriptor_digest": operation.digest,
        "shape_digests": {
            str(step["id"]): step["shape_digest"]
            for step in connector_steps
            if step.get("shape_digest")
        },
        "applicability": _applicability(context, operation.id),
    }


def _connector_steps(context: _ActionContext, workflow: Any) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for step in workflow.steps:
        if step.type != "connector":
            continue
        contract = context.profile.connector_contract(step.connector) or {}
        config = _connector_config(context, step.connector)
        backend = _backend_class(contract, config)
        steps.append(
            {
                "id": step.id,
                "connector": step.connector,
                "action": step.action,
                "backend_class": backend,
                "enabled": _connector_enabled(config),
                "shape_digest": _shape_digest(
                    connector_name=step.connector,
                    action=step.action,
                    backend=backend,
                    contract=contract,
                    config=config,
                ),
                "contract_declared": bool(contract),
                "environment_configured": bool(config),
            }
        )
    return steps


def _connector_config(context: _ActionContext, connector: str) -> dict[str, Any]:
    if context.environment is None:
        return {}
    config = context.environment.connectors.get(connector)
    return dict(config) if isinstance(config, Mapping) else {}


def _backend_class(contract: Mapping[str, Any], config: Mapping[str, Any]) -> str:
    return str(config.get("backend") or config.get("mode") or contract.get("backend") or "").strip()


def _connector_enabled(config: Mapping[str, Any]) -> bool | None:
    if not config:
        return None
    return bool(config.get("enabled", True))


def _shape_digest(
    *,
    connector_name: str,
    action: str,
    backend: str,
    contract: Mapping[str, Any],
    config: Mapping[str, Any],
) -> str:
    if not contract:
        return ""
    if backend == "http_api" and config:
        digest = validate_http_action_shape(
            connector_name=connector_name,
            action=action,
            connector_contract=dict(contract),
            connector_config=dict(config),
        )
        return digest or ""
    command_shapes = contract.get("command_shapes")
    if isinstance(command_shapes, Mapping):
        shape = command_shapes.get(action)
        if isinstance(shape, Mapping):
            return "sha256:" + canonical_digest(
                {
                    "schema": "rexecop.command_shape_projection.v0.1",
                    "connector": connector_name,
                    "action": action,
                    "shape": dict(shape),
                }
            )
    return ""


def _source_contracts(context: _ActionContext, operation_digest: str) -> dict[str, str]:
    result = {
        "profile_digest": profile_snapshot_digest(context.profile.root),
        "operation_descriptor_digest": operation_digest,
    }
    if context.environment_path is not None:
        result["environment_digest"] = yaml_document_digest(context.environment_path)
    if context.catalog_path is not None:
        result["catalog_digest"] = yaml_document_digest(context.catalog_path)
    return result


def _required_refs(context: _ActionContext, workflow: Any) -> list[dict[str, str]]:
    if context.environment is None:
        return []
    connectors = {step.connector for step in workflow.steps if step.type == "connector"}
    selected = {
        name: config
        for name, config in context.environment.connectors.items()
        if name in connectors and isinstance(config, Mapping)
    }
    return [
        {"path": binding["path"], "ref": binding["ref"]}
        for binding in collect_secret_ref_bindings({"connectors": selected})
    ]


def _backend_constraints(connector_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "connector": str(step.get("connector") or ""),
            "action": str(step.get("action") or ""),
            "backend_class": str(step.get("backend_class") or ""),
            "read_only_backend": str(step.get("backend_class") or "").endswith("_readonly"),
            "shape_digest_available": bool(step.get("shape_digest")),
        }
        for step in connector_steps
    ]


def _applicability(context: _ActionContext, operation_id: str) -> dict[str, Any] | None:
    if context.catalog_path is None or context.target is None:
        return None
    try:
        return CatalogService(context.catalog_path).resolve_operation(
            context.target,
            operation_id,
        ).applicability.as_dict()
    except RExecOpValidationError as exc:
        return {
            "target_id": context.target,
            "operation_id": operation_id,
            "applicable": False,
            "status": "catalog_resolution_failed",
            "reason_codes": [str(exc)],
        }


def _validate_one(context: _ActionContext, operation_id: str) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    try:
        operation = compile_operation_descriptor(context.profile, operation_id)
        checks.append(_check("operation_descriptor", "passed", operation.digest))
    except RExecOpValidationError as exc:
        return {
            "action": operation_id,
            "status": "failed",
            "checks": [_check("operation_descriptor", "failed", str(exc))],
        }

    if context.environment is None:
        checks.append(_check("environment_binding", "failed", "environment is required"))
    else:
        try:
            validate_no_inline_secrets(context.environment.as_dict())
            checks.append(_check("secret_hygiene", "passed", "no inline secrets"))
        except RExecOpValidationError as exc:
            checks.append(_check("secret_hygiene", "failed", str(exc)))
        try:
            workflow = load_workflow(context.profile.resolve_workflow_path(operation_id))
            validate_workflow_contract(workflow, context.environment, context.profile)
            checks.append(_check("workflow_contract", "passed", workflow.id))
        except RExecOpValidationError as exc:
            checks.append(_check("workflow_contract", "failed", str(exc)))

    applicability = _applicability(context, operation_id)
    if applicability is not None:
        checks.append(
            _check(
                "catalog_applicability",
                "passed" if applicability.get("applicable") else "failed",
                str(applicability.get("status") or ""),
            )
        )
    status = "failed" if any(check["status"] == "failed" for check in checks) else "passed"
    return {"action": operation_id, "status": status, "checks": checks}


def _check(check_id: str, status: str, summary: str) -> dict[str, str]:
    return {"id": check_id, "status": status, "summary": summary}


def _profile_summary(profile: LoadedProfile) -> dict[str, str]:
    return {
        "name": profile.name,
        "version": profile.version,
        "digest": profile_snapshot_digest(profile.root),
    }


def _environment_summary(
    environment: Environment | None,
    path: Path | None,
) -> dict[str, Any] | None:
    if environment is None:
        return None
    return {
        "id": environment.id,
        "profile": environment.profile,
        "digest": yaml_document_digest(path) if path is not None else "",
    }


def _catalog_summary(context: _ActionContext) -> dict[str, str] | None:
    if context.catalog_path is None:
        return None
    return {
        "digest": yaml_document_digest(context.catalog_path),
        "target": context.target or "",
    }


def _non_claims() -> list[str]:
    return [
        "Does not execute backend IO.",
        "Does not create an execution request.",
        "Does not request or imply GovEngine admission.",
        "Does not emit SCLite truth artifacts.",
        "Does not print resolved secret values or connector configuration.",
    ]
