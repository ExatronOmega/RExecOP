from __future__ import annotations

from pathlib import Path
from typing import Any

from rexecop.catalog.digest import profile_snapshot_digest
from rexecop.catalog.service import compile_operation_descriptor
from rexecop.errors import RExecOpValidationError
from rexecop.profile.loader import load_profile
from rexecop.profile.resolver import resolve_profile_path

RUNBOOK_SHOW_SCHEMA = "rexecop.runbook_show.v0.1"
MAX_RUNBOOK_BYTES = 65536


def show_profile_runbook(
    profile_path: str | Path,
    intent: str,
) -> dict[str, Any]:
    """Return profile-owned runbook metadata and bounded content."""
    profile = load_profile(resolve_profile_path(profile_path))
    descriptor = compile_operation_descriptor(profile, intent)
    runbook_ref = descriptor.runbook_ref
    runbook_path = (profile.root / runbook_ref).resolve()
    root = profile.root.resolve()
    if root not in runbook_path.parents or not runbook_path.is_file():
        raise RExecOpValidationError(
            f"profile runbook reference invalid for intent {intent}: {runbook_ref}"
        )
    raw = runbook_path.read_bytes()
    if len(raw) > MAX_RUNBOOK_BYTES:
        raise RExecOpValidationError(
            f"runbook exceeds maximum size ({MAX_RUNBOOK_BYTES} bytes): {runbook_ref}"
        )
    content = raw.decode("utf-8")
    from rexecop.catalog.digest import text_digest

    return {
        "schema": RUNBOOK_SHOW_SCHEMA,
        "profile": profile.name,
        "profile_version": profile.version,
        "profile_digest": profile_snapshot_digest(profile.root),
        "intent": intent,
        "operation_id": descriptor.id,
        "runbook_ref": runbook_ref,
        "runbook_digest": text_digest(content),
        "content": content,
        "non_claims": [
            "Profile-owned operator guidance only.",
            "Does not execute work or override GovEngine admission.",
            "SCLite remains truth authority for emitted artifacts.",
        ],
    }


def render_runbook_show(payload: dict[str, Any], fmt: str) -> str:
    normalized = str(fmt or "json").strip().lower()
    if normalized == "json":
        import json

        return json.dumps(payload, indent=2, sort_keys=True)
    if normalized == "markdown":
        return _render_runbook_markdown(payload)
    if normalized == "table":
        return _render_runbook_table(payload)
    raise ValueError(f"unsupported runbook format: {fmt}")


def _render_runbook_table(payload: dict[str, Any]) -> str:
    rows = [
        ("profile", str(payload.get("profile") or "")),
        ("intent", str(payload.get("intent") or "")),
        ("runbook_ref", str(payload.get("runbook_ref") or "")),
        ("profile_digest", str(payload.get("profile_digest") or "")),
        ("runbook_digest", str(payload.get("runbook_digest") or "")),
    ]
    width = max(len(key) for key, _ in rows)
    lines = [f"{key.ljust(width)}  {value}" for key, value in rows]
    content = str(payload.get("content") or "").strip()
    if content:
        lines.extend(["", content])
    return "\n".join(lines) + "\n"


def _render_runbook_markdown(payload: dict[str, Any]) -> str:
    content = str(payload.get("content") or "").strip()
    return "\n".join(
        [
            f"# Runbook: {payload.get('intent', '')}",
            "",
            f"**Profile:** {payload.get('profile', '')}",
            f"**Runbook ref:** {payload.get('runbook_ref', '')}",
            f"**Profile digest:** {payload.get('profile_digest', '')}",
            f"**Runbook digest:** {payload.get('runbook_digest', '')}",
            "",
            content,
            "",
        ]
    )