from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rexecop.observability.failure_classes import FAILURE_CLASSES, normalize_failure_class
from rexecop.observability.structured_log import list_structured_logs

if TYPE_CHECKING:
    from rexecop.storage.port import RuntimeStore

RUNTIME_DIAGNOSTICS_SCHEMA = "rexecop.runtime_diagnostics.v0.1"


def _normalize_diagnostic_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items:
        failure_class = normalize_failure_class(str(item.get("failure_class") or ""))
        normalized.append({**item, "failure_class": failure_class})
    return normalized


def collect_runtime_diagnostics(store: RuntimeStore) -> dict[str, Any]:
    from rexecop.runtime_ops.triage import collect_ops_snapshot

    ops = collect_ops_snapshot(store)
    blockers = _normalize_diagnostic_items(list(ops.get("blockers") or []))
    action_required = _normalize_diagnostic_items(list(ops.get("action_required") or []))
    logs = list_structured_logs(store, limit=20)
    recent_kinds = [
        str(item.get("event_kind") or "")
        for item in logs.get("items") or []
        if item.get("event_kind")
    ]
    failure_class_counts: dict[str, int] = {}
    for item in blockers + action_required:
        failure_class = str(item.get("failure_class") or "runtime")
        failure_class_counts[failure_class] = failure_class_counts.get(failure_class, 0) + 1
    return {
        "schema": RUNTIME_DIAGNOSTICS_SCHEMA,
        "runtime_root": str(store.root),
        "failure_classes": sorted(FAILURE_CLASSES),
        "blockers": blockers,
        "action_required": action_required,
        "failure_class_counts": failure_class_counts,
        "structured_logs": {
            "count": int(logs.get("count") or 0),
            "recent_event_kinds": recent_kinds,
        },
        "safe_next_actions": list(ops.get("safe_next_actions") or []),
        "non_claims": [
            "Diagnostics use the same failure classes as explain-error.",
            "Output is bounded, redacted and does not expose secret values.",
            "Does not execute remediation or replace explain-error reasoning.",
        ],
    }