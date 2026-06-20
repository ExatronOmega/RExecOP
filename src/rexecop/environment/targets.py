from __future__ import annotations

from typing import Any, Literal

from rexecop.environment.model import Environment
from rexecop.errors import RExecOpValidationError

TargetKind = Literal["group", "host", "member"]


def validate_operation_target(environment: Environment, target: str) -> None:
    """Reject operation targets that are not declared in environment.targets."""
    name = str(target or "").strip()
    if not name:
        raise RExecOpValidationError("operation target is required")
    if describe_target(environment, name)["kind"] == "unknown":
        raise RExecOpValidationError(f"unknown environment target: {name}")


def describe_target(environment: Environment, target: str) -> dict[str, Any]:
    """Resolve target semantics for operators and SCLite target_host mapping."""
    name = str(target or "").strip()
    if not name:
        return {"name": "", "kind": "unknown", "members": []}

    spec = environment.targets.get(name)
    if isinstance(spec, dict):
        kind = str(spec.get("type") or "host").strip().lower()
        if kind == "group":
            members = [
                str(item).strip()
                for item in (spec.get("members") or [])
                if str(item).strip()
            ]
            return {
                "name": name,
                "kind": "group",
                "members": members,
                "declared_as": name,
            }
        return {
            "name": name,
            "kind": "host",
            "members": [name],
            "declared_as": name,
        }

    for group_name, group_spec in environment.targets.items():
        if not isinstance(group_spec, dict):
            continue
        if str(group_spec.get("type") or "").lower() != "group":
            continue
        members = group_spec.get("members") or []
        if not isinstance(members, list):
            continue
        if name in {str(item).strip() for item in members if str(item).strip()}:
            return {
                "name": name,
                "kind": "member",
                "members": [name],
                "declared_as": group_name,
                "group": group_name,
            }

    return {"name": name, "kind": "unknown", "members": []}


def list_declared_target_names(environment: Environment) -> list[str]:
    names = sorted(str(key) for key in environment.targets)
    for spec in environment.targets.values():
        if not isinstance(spec, dict):
            continue
        if str(spec.get("type") or "").lower() != "group":
            continue
        for member in spec.get("members") or []:
            text = str(member).strip()
            if text and text not in names:
                names.append(text)
    return sorted(names)
