from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from rexecop.action.templates import (
    ACTION_TEMPLATE_SCOPE,
    list_action_templates,
    template_provenance_for_step,
)
from rexecop.catalog.digest import canonical_digest, profile_snapshot_digest, yaml_document_digest
from rexecop.catalog.service import (
    CatalogService,
    compile_operation_descriptor,
    compile_profile_operations,
)
from rexecop.connectors.action_shape import (
    canonical_http_action_shape,
    validate_http_action_shape,
)
from rexecop.connectors.command_shape import normalize_allowlisted_argv
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
ACTION_PREVIEW_SCHEMA = "rexecop.action_preview.v0.1"


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
        "template_provenance": _template_provenance(context, workflow),
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


def preview_action(
    intent: str,
    *,
    profile: str | Path | None = None,
    env: Path | None = None,
    catalog: Path | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    """Preview bounded connector call shapes without backend IO or admission."""
    if env is None and not (catalog is not None and target is not None):
        raise RExecOpValidationError("action preview requires --env or --catalog with --target")
    context = _resolve_context(profile=profile, env=env, catalog=catalog, target=target)
    operation = compile_operation_descriptor(context.profile, intent)
    workflow = load_workflow(context.profile.resolve_workflow_path(intent))
    connector_steps = _connector_steps(context, workflow)
    previews = [
        _step_preview(context, workflow.mode, step)
        for step in workflow.steps
        if step.type == "connector"
    ]
    return {
        "schema": ACTION_PREVIEW_SCHEMA,
        "action": {
            "id": operation.id,
            "title": operation.title,
            "side_effect_class": operation.side_effect_class,
            "operation_descriptor_digest": operation.digest,
        },
        "workflow": {
            "id": workflow.id,
            "mode": workflow.mode,
            "risk": workflow.risk,
            "connector_step_count": len(connector_steps),
        },
        "source_contracts": _source_contracts(context, operation.digest),
        "previews": previews,
        "bounded_output": _bounded_output_summary(previews),
        "applicability": _applicability(context, operation.id),
        "non_claims": _non_claims()
        + [
            "Does not print base URLs, hosts, users, identity files, auth material "
            "or raw connector action data.",
            "Does not prove the backend will respond successfully.",
        ],
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
        actions = config.get("actions")
        actual_spec = actions.get(action) if isinstance(actions, Mapping) else None
        if not isinstance(actual_spec, Mapping):
            return ""
        try:
            digest = validate_http_action_shape(
                connector_name=connector_name,
                action=action,
                connector_contract=dict(contract),
                connector_config=dict(config),
            )
        except RExecOpValidationError:
            return ""
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


def _step_preview(context: _ActionContext, mode: str, step: Any) -> dict[str, Any]:
    contract = context.profile.connector_contract(step.connector) or {}
    config = _connector_config(context, step.connector)
    backend = _backend_class(contract, config)
    base: dict[str, Any] = {
        "step_id": step.id,
        "connector": step.connector,
        "action": step.action,
        "backend_class": backend,
        "enabled": _connector_enabled(config),
        "contract_declared": bool(contract),
        "environment_configured": bool(config),
        "shape_digest": _shape_digest(
            connector_name=step.connector,
            action=step.action,
            backend=backend,
            contract=contract,
            config=config,
        ),
    }
    if backend == "http_api":
        base["call_preview"] = _http_call_preview(context, step, contract, config)
    elif backend in {"local_shell_readonly", "ssh_readonly"}:
        base["call_preview"] = _command_call_preview(
            backend=backend,
            action=step.action,
            mode=mode,
            config=config,
        )
    elif backend == "static_fixture":
        base["call_preview"] = _static_fixture_preview(step.action, config)
    else:
        base["call_preview"] = {
            "kind": "unsupported_preview",
            "reason": "No redacted preview renderer for this backend class.",
        }
    return base


def _http_call_preview(
    context: _ActionContext,
    step: Any,
    contract: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    action_spec = _http_action_spec(step.connector, step.action, contract, config)
    shape = canonical_http_action_shape(dict(action_spec), dict(config))
    return {
        "kind": "http_api",
        "method": shape["method"],
        "path_template": shape["path"],
        "path_preview": _render_preview_template(str(shape["path"]), context),
        "query_keys": sorted(str(key) for key in shape["query"]),
        "body_shape": _payload_shape(shape["body"]),
        "unwrap": shape["unwrap"],
        "pagination": shape["pagination"],
        "mutating": shape["mutating"],
        "headers": {
            "accept": "application/json",
            "content_type": "application/json" if shape["body"] is not None else "",
            "auth_configured": _http_auth_configured(config),
            "auth_header": _http_auth_header(config),
        },
        "bounded_output": {
            "max_response_bytes": shape["max_response_bytes"],
            "json_only": True,
            "redacted_payload": True,
        },
        "redactions": [
            "base_url",
            "base_url_secret_ref",
            "auth.secret_ref",
            "auth.prefix",
            "resolved headers",
        ],
    }


def _http_action_spec(
    connector: str,
    action: str,
    contract: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    actions = config.get("actions")
    config_spec = actions.get(action) if isinstance(actions, Mapping) else None
    if isinstance(config_spec, Mapping):
        return dict(config_spec)
    action_shapes = contract.get("action_shapes")
    contract_spec = action_shapes.get(action) if isinstance(action_shapes, Mapping) else None
    if isinstance(contract_spec, Mapping):
        return dict(contract_spec)
    raise RExecOpValidationError(f"http action not configured: {connector}.{action}")


def _http_auth_configured(config: Mapping[str, Any]) -> bool:
    auth = config.get("auth")
    return isinstance(auth, Mapping) and bool(str(auth.get("secret_ref") or "").strip())


def _http_auth_header(config: Mapping[str, Any]) -> str:
    auth = config.get("auth")
    if not isinstance(auth, Mapping):
        return ""
    return str(auth.get("header") or "Authorization")


def _command_call_preview(
    *,
    backend: str,
    action: str,
    mode: str,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    allowlist = config.get("allowlist")
    if not isinstance(allowlist, list):
        raise RExecOpValidationError(f"{backend} preview requires allowlist")
    entry = _find_allowlist_entry(allowlist, action)
    if entry is None:
        raise RExecOpValidationError(f"{backend} action not allowlisted: {action}")
    allowed_tools = {
        str(item.get("command")).strip().lower()
        for item in allowlist
        if isinstance(item, Mapping) and str(item.get("command") or "").strip()
    }
    argv = normalize_allowlisted_argv(
        tool=str(entry.get("command") or "").strip(),
        args=entry.get("args") or [],
        allowed_tools=allowed_tools,
    )
    return {
        "kind": backend,
        "mode": mode,
        "readonly_only": True,
        "command": {
            "argv": argv,
            "argv_digest": "sha256:" + canonical_digest(argv),
        },
        "bounded_output": {
            "max_output_bytes": int(config.get("max_output_bytes") or 65536),
            "stdout_digest_expected": True,
            "stderr_digest_expected": True,
            "redacted_payload": True,
        },
        "timeout_seconds": float(
            config.get("timeout_seconds") or (15 if backend == "ssh_readonly" else 10)
        ),
        "redactions": _command_redactions(backend),
    }


def _find_allowlist_entry(allowlist: list[Any], action: str) -> Mapping[str, Any] | None:
    for item in allowlist:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("action") or item.get("command")) == action:
            return item
    return None


def _command_redactions(backend: str) -> list[str]:
    if backend == "ssh_readonly":
        return [
            "host",
            "user",
            "port",
            "known_hosts_file",
            "identity_file_secret_ref",
            "resolved identity file",
        ]
    return []


def _static_fixture_preview(action: str, config: Mapping[str, Any]) -> dict[str, Any]:
    actions = config.get("actions")
    spec = actions.get(action) if isinstance(actions, Mapping) else None
    if not isinstance(spec, Mapping):
        raise RExecOpValidationError(f"static_fixture action not configured: {action}")
    return {
        "kind": "static_fixture",
        "fixture_only": bool(config.get("fixture_only", False)),
        "mutating": bool(spec.get("mutating", False)),
        "data_digest": "sha256:" + canonical_digest(spec.get("data") or {}),
        "redactions": ["raw fixture data"],
        "bounded_output": {
            "redacted_payload": True,
            "raw_data_printed": False,
        },
    }


def _render_preview_template(template: str, context: _ActionContext) -> str:
    if context.target is None:
        return template
    return template.replace("{target}", context.target)


def _payload_shape(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _payload_shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_payload_shape(value[0])] if value else []
    if value is None:
        return None
    return f"<{type(value).__name__}>"


def _bounded_output_summary(previews: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "per_step": [
            {
                "step_id": preview["step_id"],
                "backend_class": preview["backend_class"],
                "bounded_output": preview.get("call_preview", {}).get("bounded_output", {}),
            }
            for preview in previews
        ],
        "raw_backend_output_printed": False,
    }


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
            checks.append(_check_duplicate_secret_refs(context, workflow))
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


def _check_duplicate_secret_refs(context: _ActionContext, workflow: Any) -> dict[str, str]:
    if context.environment is None:
        return _check("duplicate_refs", "passed", "environment is required for ref bindings")
    connectors = {step.connector for step in workflow.steps if step.type == "connector"}
    selected = {
        name: config
        for name, config in context.environment.connectors.items()
        if name in connectors and isinstance(config, Mapping)
    }
    by_ref: dict[str, list[str]] = defaultdict(list)
    for binding in collect_secret_ref_bindings({"connectors": selected}):
        ref = str(binding.get("ref") or "").strip()
        if not ref:
            continue
        by_ref[ref].append(str(binding.get("path") or ""))
    duplicates = {ref: sorted(paths) for ref, paths in by_ref.items() if len(paths) > 1}
    if duplicates:
        return _check(
            "duplicate_refs",
            "failed",
            "one or more secret_ref names are reused across multiple bindings",
        )
    return _check("duplicate_refs", "passed", "no duplicate secret_ref reuse detected")


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


def _template_provenance(context: _ActionContext, workflow: Any) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    for step in workflow.steps:
        if step.type != "connector":
            continue
        contract = context.profile.connector_contract(step.connector) or {}
        config = _connector_config(context, step.connector)
        backend = _backend_class(contract, config) or str(contract.get("backend") or "").strip()
        provenance = template_provenance_for_step(
            backend=backend,
            action=step.action,
            contract=contract,
        )
        steps.append(
            {
                "step_id": step.id,
                "connector": step.connector,
                "action": step.action,
                "backend_class": backend,
                **provenance,
            }
        )
    return {
        "available": any(item.get("available") for item in steps),
        "scope": ACTION_TEMPLATE_SCOPE,
        "library": [item["id"] for item in list_action_templates()["templates"]],
        "steps": steps,
    }


def _non_claims() -> list[str]:
    return [
        "Does not execute backend IO.",
        "Does not create an execution request.",
        "Does not request or imply GovEngine admission.",
        "Does not emit SCLite truth artifacts.",
        "Does not print resolved secret values or connector configuration.",
    ]
