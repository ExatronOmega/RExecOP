from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from rexecop.catalog.service import compile_operation_descriptor
from rexecop.errors import RExecOpValidationError
from rexecop.operation.explain import explain_operation
from rexecop.operation.model import Operation
from rexecop.operation.plan import OperationPlan
from rexecop.profile.loader import load_profile
from rexecop.profile.operator_metadata import intent_operator_metadata

OPERATION_REVIEW_SCHEMA = "rexecop.operation_review.v0.1"


def review_operation(operation: Operation, plan: OperationPlan) -> dict[str, Any]:
    """Build a stable operator decision screen for a stored plan."""
    explain = explain_operation(operation, plan)
    descriptor = _operation_descriptor(operation)
    operator = _operator_metadata(operation)
    backends = _connector_backends(operation, plan)
    blockers = _governance_blockers(explain["governance"])
    status = _review_status(operation, blockers)
    operator_label = (
        str(operator.get("label") or "")
        if operator is not None
        else (descriptor.title if descriptor is not None else "")
    )
    operator_hints = {}
    if operator is not None:
        operator_hints = {
            key: operator[key]
            for key in ("runbook_hint", "safe_next_options")
            if operator.get(key)
        }
    return {
        "schema": OPERATION_REVIEW_SCHEMA,
        "status": status,
        "decision_screen": {
            "operation_id": operation.id,
            "state": operation.state,
            "profile": operation.profile,
            "environment": operation.environment,
            "intent": operation.intent,
            "target": operation.target,
            "mode": operation.mode,
            "title": operator_label or (descriptor.title if descriptor is not None else ""),
            "risk": plan.risk,
            "backends": backends,
            "side_effect_class": (
                descriptor.side_effect_class if descriptor is not None else ""
            ),
            "digests": {
                "profile_digest": explain["bindings"]["profile_digest"],
                "environment_digest": explain["bindings"]["environment_digest"],
                "catalog_digest": explain["bindings"]["catalog_digests"].get(
                    "catalog_digest", ""
                ),
                "operation_descriptor_digest": explain["bindings"]["catalog_digests"].get(
                    "operation_descriptor_digest", ""
                ),
            },
            "runbook_ref": descriptor.runbook_ref if descriptor is not None else "",
            "operator_hints": operator_hints,
            "stop_conditions": _stop_conditions(operation, plan, blockers),
            "expected_evidence": list(plan.expected_evidence),
            "expected_sclite_artifacts": [
                item["role"] for item in explain["expected_sclite_artifacts"]
            ],
            "governance_blockers": blockers,
            "govengine_decision_summary": operation.govengine_decision_summary,
            "safe_next_actions": list(explain["safe_next_actions"]),
        },
        "workflow_summary": {
            "workflow_id": explain["workflow"]["workflow_id"],
            "step_count": explain["workflow"]["step_count"],
            "rollback_available": explain["workflow"]["rollback_available"],
            "pause_safe_points": explain["workflow"]["pause_safe_points"],
        },
        "non_claims": [
            "Does not execute work.",
            "Does not approve operators.",
            "Does not start, pause, cancel or retry operations.",
            "Safe next actions are suggestions only.",
        ],
    }


def _operation_descriptor(operation: Operation):
    profile_root_raw = str(operation.metadata.get("profile_root") or "").strip()
    if not profile_root_raw:
        return None
    profile_root = Path(profile_root_raw)
    if not profile_root.exists():
        return None
    try:
        profile = load_profile(profile_root)
        return compile_operation_descriptor(profile, operation.intent)
    except RExecOpValidationError:
        return None


def _operator_metadata(operation: Operation) -> dict[str, Any] | None:
    profile_root_raw = str(operation.metadata.get("profile_root") or "").strip()
    if not profile_root_raw:
        return None
    profile_root = Path(profile_root_raw)
    if not profile_root.exists():
        return None
    try:
        profile = load_profile(profile_root)
        return intent_operator_metadata(profile, operation.intent)
    except RExecOpValidationError:
        return None


def _connector_backends(
    operation: Operation,
    plan: OperationPlan,
) -> list[dict[str, str]]:
    connectors = operation.metadata.get("environment_connectors")
    if not isinstance(connectors, Mapping):
        return []
    backends: list[dict[str, str]] = []
    for connector_name in plan.required_connectors:
        config = connectors.get(connector_name)
        if not isinstance(config, Mapping):
            continue
        backend = str(config.get("backend") or config.get("mode") or "").strip()
        if not backend:
            continue
        backends.append({"connector": connector_name, "backend": backend})
    return backends


def _governance_blockers(governance: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    verdict = governance.get("policy_verdict")
    if isinstance(verdict, Mapping):
        blockers.extend(str(item) for item in verdict.get("blockers") or [] if str(item))
        decision = str(verdict.get("decision") or "")
        reason_code = str(verdict.get("reason_code") or "")
        if decision == "deny" and reason_code and reason_code not in blockers:
            blockers.append(reason_code)
    enforcement = governance.get("policy_enforcement")
    if isinstance(enforcement, Mapping):
        blockers.extend(
            str(item) for item in enforcement.get("plan_blockers") or [] if str(item)
        )
        plan_status = str(enforcement.get("plan_status") or "")
        plan_reason = str(enforcement.get("plan_reason_code") or "")
        if plan_status == "blocked" and plan_reason and plan_reason not in blockers:
            blockers.append(plan_reason)
    return sorted(dict.fromkeys(blockers))


def _stop_conditions(
    operation: Operation,
    plan: OperationPlan,
    blockers: list[str],
) -> list[str]:
    conditions = [f"pause_safe:{step_id}" for step_id in plan.pause_safe_points]
    if plan.rollback_available:
        conditions.append("rollback_available_on_failure")
    if operation.state == "waiting_for_approval":
        conditions.append("manual_approval_required")
    conditions.extend(f"policy_blocker:{item}" for item in blockers)
    return conditions


def _review_status(operation: Operation, blockers: list[str]) -> str:
    if blockers:
        return "blocked"
    if operation.state == "waiting_for_approval":
        return "approval_required"
    if operation.state in {"failed", "cancelled", "completed"}:
        return "closed"
    return "proceed"


def render_operation_review(payload: Mapping[str, Any], fmt: str) -> str:
    normalized = str(fmt or "json").strip().lower()
    if normalized == "json":
        import json

        return json.dumps(dict(payload), indent=2, sort_keys=True)
    if normalized == "table":
        return _render_review_table(payload)
    if normalized == "markdown":
        return _render_review_markdown(payload)
    raise ValueError(f"unsupported review format: {fmt}")


def _render_review_table(payload: Mapping[str, Any]) -> str:
    screen = payload.get("decision_screen")
    if not isinstance(screen, Mapping):
        return ""
    rows = [
        ("status", str(payload.get("status") or "")),
        ("operation_id", str(screen.get("operation_id") or "")),
        ("intent", str(screen.get("intent") or "")),
        ("target", str(screen.get("target") or "")),
        ("mode", str(screen.get("mode") or "")),
        ("state", str(screen.get("state") or "")),
        ("side_effect_class", str(screen.get("side_effect_class") or "")),
        ("profile_digest", str(screen.get("digests", {}).get("profile_digest", ""))),
        ("environment_digest", str(screen.get("digests", {}).get("environment_digest", ""))),
        ("catalog_digest", str(screen.get("digests", {}).get("catalog_digest", ""))),
        ("runbook_ref", str(screen.get("runbook_ref") or "")),
    ]
    backends = screen.get("backends")
    if isinstance(backends, list) and backends:
        backend_text = ", ".join(
            f"{item.get('connector', '')}:{item.get('backend', '')}"
            for item in backends
            if isinstance(item, Mapping)
        )
        rows.append(("backends", backend_text))
    width = max(len(key) for key, _ in rows)
    lines = [f"{key.ljust(width)}  {value}" for key, value in rows]
    blockers = screen.get("governance_blockers")
    if isinstance(blockers, list) and blockers:
        lines.append(f"{'blockers'.ljust(width)}  {', '.join(str(item) for item in blockers)}")
    actions = screen.get("safe_next_actions")
    if isinstance(actions, list) and actions:
        lines.append(f"{'next_actions'.ljust(width)}  {'; '.join(str(item) for item in actions)}")
    return "\n".join(lines) + "\n"


def _render_review_markdown(payload: Mapping[str, Any]) -> str:
    screen = payload.get("decision_screen")
    if not isinstance(screen, Mapping):
        return ""
    lines = [
        "# Operation review",
        "",
        f"**Status:** {payload.get('status', '')}",
        "",
        "## Operation",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| operation_id | {screen.get('operation_id', '')} |",
        f"| intent | {screen.get('intent', '')} |",
        f"| target | {screen.get('target', '')} |",
        f"| mode | {screen.get('mode', '')} |",
        f"| state | {screen.get('state', '')} |",
        f"| side_effect_class | {screen.get('side_effect_class', '')} |",
        f"| runbook_ref | {screen.get('runbook_ref', '')} |",
        "",
        "## Digests",
        "",
        "| Field | Value |",
        "| --- | --- |",
    ]
    digests = screen.get("digests")
    if isinstance(digests, Mapping):
        for key in ("profile_digest", "environment_digest", "catalog_digest"):
            lines.append(f"| {key} | {digests.get(key, '')} |")
    backends = screen.get("backends")
    if isinstance(backends, list) and backends:
        lines.extend(["", "## Backends", "", "| Connector | Backend |", "| --- | --- |"])
        for item in backends:
            if isinstance(item, Mapping):
                lines.append(
                    f"| {item.get('connector', '')} | {item.get('backend', '')} |"
                )
    blockers = screen.get("governance_blockers")
    if isinstance(blockers, list) and blockers:
        lines.extend(["", "## Governance blockers", ""])
        lines.extend(f"- {item}" for item in blockers)
    actions = screen.get("safe_next_actions")
    if isinstance(actions, list) and actions:
        lines.extend(["", "## Safe next actions", ""])
        lines.extend(f"- `{item}`" for item in actions)
    return "\n".join(lines) + "\n"