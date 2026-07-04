from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

IDEMPOTENCY_SCHEMA = "rexecop.idempotency.v0.1"


def canonical_idempotency_digest(payload: Mapping[str, Any]) -> str:
    rendered = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def plan_idempotency_key(
    *,
    profile: str,
    environment: str,
    intent: str,
    target: str,
    mode: str,
    catalog_binding: Mapping[str, Any] | None = None,
    auto_react: str | None = None,
) -> str:
    payload = {
        "kind": "plan",
        "profile": profile,
        "environment": environment,
        "intent": intent,
        "target": target,
        "mode": mode,
        "catalog_binding": dict(catalog_binding or {}),
        "auto_react": (auto_react or "").strip(),
    }
    return canonical_idempotency_digest(payload)


def start_idempotency_key(operation_id: str) -> str:
    return canonical_idempotency_digest({"kind": "start", "operation_id": operation_id})


def reaction_child_plan_key(*, reaction_id: str, child_operation_id: str) -> str:
    return canonical_idempotency_digest(
        {
            "kind": "reaction_child_plan",
            "reaction_id": reaction_id,
            "child_operation_id": child_operation_id,
        }
    )


def trigger_plan_key(*, dedupe_key: str, decision_id: str) -> str:
    return canonical_idempotency_digest(
        {
            "kind": "trigger_plan",
            "dedupe_key": dedupe_key,
            "decision_id": decision_id,
        }
    )


def attach_operation_idempotency(
    metadata: dict[str, Any],
    *,
    plan_key: str,
    start_key: str,
    extra: Mapping[str, str] | None = None,
) -> None:
    keys = {
        "schema": IDEMPOTENCY_SCHEMA,
        "plan_key": plan_key,
        "start_key": start_key,
    }
    if extra:
        keys.update(dict(extra))
    metadata["idempotency"] = keys