from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from rexecop.operation.model import Operation
from rexecop.runtime_ops.coordinator import ACTIVE_RUNTIME_STATES
from rexecop.runtime_ops.recovery import TERMINAL_RECEIPT_STATES
from rexecop.storage.port import RuntimeStore

RUNTIME_RECONSTRUCTION_SCHEMA = "rexecop.runtime_reconstruction.v0.1"


def collect_runtime_reconstruction_status(store: RuntimeStore) -> dict[str, Any]:
    """Project deterministic runtime-store reconstruction readiness without mutation."""
    operation_entries = _operation_entries(store.root)
    operations = [_operation_status(store, entry) for entry in operation_entries]
    blocked = [item for item in operations if item["status"] == "blocked"]
    needs_recovery = [item for item in operations if item["status"] == "needs_recovery"]
    partial = [item for item in operations if item["status"] == "partial"]
    return {
        "schema": RUNTIME_RECONSTRUCTION_SCHEMA,
        "runtime_root": str(store.root),
        "status": "blocked"
        if blocked
        else "needs_recovery"
        if needs_recovery
        else "partial"
        if partial
        else "reconstructable",
        "rules": _rules(),
        "summary": {
            "operation_count": len(operations),
            "reconstructable_count": sum(
                1 for item in operations if item["status"] == "reconstructable"
            ),
            "partial_count": len(partial),
            "needs_recovery_count": len(needs_recovery),
            "blocked_count": len(blocked),
        },
        "operations": operations,
        "safe_next_actions": _safe_next_actions(blocked=blocked, needs_recovery=needs_recovery),
        "non_claims": [
            "Does not execute recovery or connector IO.",
            "Does not repair receipts, leases, locks or operation state.",
            "Does not replace SCLite artifact truth.",
            "Does not recompute GovEngine admission or policy reasoning.",
        ],
    }


def _operation_entries(root: Path) -> list[dict[str, Any]]:
    operations_dir = root / "operations"
    if not operations_dir.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(operations_dir.glob("*.json")):
        operation_id = path.stem
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("operation record must be a mapping")
            operation = Operation.from_dict(payload)
            operation_id = operation.id
            entries.append(
                {
                    "operation_id": operation_id,
                    "path": path,
                    "operation": operation,
                    "load_error": "",
                }
            )
        except Exception as exc:
            entries.append(
                {
                    "operation_id": operation_id,
                    "path": path,
                    "operation": None,
                    "load_error": exc.__class__.__name__,
                }
            )
    return entries


def _operation_status(store: RuntimeStore, entry: Mapping[str, Any]) -> dict[str, Any]:
    operation_id = str(entry.get("operation_id") or "")
    operation = entry.get("operation")
    blockers: list[str] = []
    warnings: list[str] = []
    inputs = {
        "operation_record": {
            "path": _relative_to_root(store.root, entry.get("path")),
            "status": "present" if isinstance(operation, Operation) else "invalid",
        },
        "plan_record": _file_status(store.root, "plans", operation_id),
        "receipt_export": _file_status(store.root, "receipts", operation_id),
        "evidence_events": _evidence_status(store.root, operation_id),
        "sclite_bundle": _sclite_status(store.root, operation_id),
    }
    if not isinstance(operation, Operation):
        blockers.append(f"operation_record_invalid:{entry.get('load_error') or 'unknown'}")
        return _status_record(
            operation_id=operation_id,
            state="",
            status="blocked",
            inputs=inputs,
            blockers=blockers,
            warnings=warnings,
        )

    state = operation.state
    recovery_blocker = operation.metadata.get("recovery_blocker")
    auto_reaction = operation.metadata.get("auto_reaction")
    inputs["runtime_metadata"] = {
        "recovery_blocker": "present"
        if isinstance(recovery_blocker, Mapping)
        else "absent",
        "auto_reaction": "present" if isinstance(auto_reaction, Mapping) else "absent",
        "idempotency": "present"
        if isinstance(operation.metadata.get("idempotency"), Mapping)
        else "absent",
    }
    _validate_required_plan(inputs, blockers)
    _validate_active_state(state, blockers)
    _validate_terminal_receipt(state, inputs, recovery_blocker, blockers, warnings)
    _validate_sclite_refs(store.root, operation, warnings)
    _validate_auto_reaction(auto_reaction, warnings)

    status = "reconstructable"
    if blockers:
        status = "blocked"
    elif state in ACTIVE_RUNTIME_STATES:
        status = "needs_recovery"
    if status == "reconstructable" and warnings:
        status = "partial"
    return _status_record(
        operation_id=operation_id,
        state=state,
        status=status,
        inputs=inputs,
        blockers=blockers,
        warnings=warnings,
    )


def _validate_required_plan(inputs: Mapping[str, Any], blockers: list[str]) -> None:
    plan = inputs.get("plan_record")
    if not isinstance(plan, Mapping) or plan.get("status") != "present":
        blockers.append("plan_record_missing")


def _validate_active_state(state: str, blockers: list[str]) -> None:
    if state in ACTIVE_RUNTIME_STATES:
        blockers.append("active_state_requires_runtime_recover")


def _validate_terminal_receipt(
    state: str,
    inputs: Mapping[str, Any],
    recovery_blocker: Any,
    blockers: list[str],
    warnings: list[str],
) -> None:
    if state not in TERMINAL_RECEIPT_STATES:
        return
    receipt = inputs.get("receipt_export")
    if isinstance(receipt, Mapping) and receipt.get("status") == "present":
        return
    if isinstance(recovery_blocker, Mapping):
        warnings.append("terminal_receipt_blocked_by_recorded_recovery_blocker")
        return
    blockers.append("terminal_receipt_missing")


def _validate_sclite_refs(root: Path, operation: Operation, warnings: list[str]) -> None:
    for role, ref in sorted(operation.sclite_refs.items()):
        if not isinstance(ref, Mapping):
            warnings.append(f"sclite_ref_invalid:{role}")
            continue
        descriptor_path = str(ref.get("descriptor_path") or "").strip()
        if descriptor_path and not Path(descriptor_path).is_file():
            rel = _relative_to_root(root, descriptor_path)
            warnings.append(f"sclite_ref_descriptor_missing:{role}:{rel}")
        if not str(ref.get("digest") or "").strip():
            warnings.append(f"sclite_ref_digest_missing:{role}")


def _validate_auto_reaction(auto_reaction: Any, warnings: list[str]) -> None:
    if not isinstance(auto_reaction, Mapping):
        return
    status = str(auto_reaction.get("status") or "")
    if status != "planned":
        return
    if not str(auto_reaction.get("reaction_id") or "").strip():
        warnings.append("auto_reaction_reaction_id_missing")
    if not str(auto_reaction.get("automation_chain_digest") or "").strip():
        admission = auto_reaction.get("automation_admission")
        digest = (
            str(admission.get("automation_chain_digest") or "").strip()
            if isinstance(admission, Mapping)
            else ""
        )
        if not digest:
            warnings.append("auto_reaction_automation_chain_digest_missing")


def _status_record(
    *,
    operation_id: str,
    state: str,
    status: str,
    inputs: Mapping[str, Any],
    blockers: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "operation_id": operation_id,
        "state": state,
        "status": status,
        "inputs": dict(inputs),
        "blockers": blockers,
        "warnings": warnings,
    }


def _file_status(root: Path, directory: str, operation_id: str) -> dict[str, str]:
    path = root / directory / f"{operation_id}.json"
    return {
        "path": _relative_to_root(root, path),
        "status": "present" if path.is_file() else "missing",
    }


def _evidence_status(root: Path, operation_id: str) -> dict[str, Any]:
    path = root / "evidence" / operation_id
    count = len(list(path.glob("*.json"))) if path.is_dir() else 0
    return {
        "path": _relative_to_root(root, path),
        "status": "present" if count else "missing",
        "count": count,
    }


def _sclite_status(root: Path, operation_id: str) -> dict[str, Any]:
    path = root / "sclite" / operation_id
    count = len(list(path.glob("*.json"))) if path.is_dir() else 0
    return {
        "path": _relative_to_root(root, path),
        "status": "present" if count else "missing",
        "artifact_count": count,
    }


def _relative_to_root(root: Path, value: object) -> str:
    if not value:
        return ""
    path = Path(str(value))
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _safe_next_actions(
    *,
    blocked: list[dict[str, Any]],
    needs_recovery: list[dict[str, Any]],
) -> list[str]:
    if needs_recovery or any(
        "active_state_requires_runtime_recover" in item.get("blockers", [])
        for item in blocked
    ):
        return ["rexecop runtime recover --json", "rexecop runtime reconstruct-status --json"]
    if blocked:
        return [
            "Inspect operations with status=blocked.",
            "Restore missing runtime files from backup or recreate the operation plan.",
        ]
    return ["rexecop runtime status --json", "rexecop operation truth-path --operation <id>"]


def _rules() -> list[dict[str, str]]:
    return [
        {
            "id": "operation_record_required",
            "effect": "blocked_when_missing_or_invalid",
            "owner": "rexecop",
        },
        {
            "id": "plan_record_required",
            "effect": "blocked_when_missing",
            "owner": "rexecop",
        },
        {
            "id": "active_state_requires_recover",
            "effect": "needs_runtime_recover_before_reconstruction_claim",
            "owner": "rexecop",
        },
        {
            "id": "terminal_receipt_required_or_blocked",
            "effect": "blocked_when_terminal_receipt_missing_without_recovery_blocker",
            "owner": "rexecop",
        },
        {
            "id": "sclite_refs_are_external_truth_refs",
            "effect": "warn_when_descriptor_or_digest_missing",
            "owner": "sclite",
        },
        {
            "id": "govengine_refs_are_not_recomputed",
            "effect": "preserve_recorded_admission_and_policy_refs",
            "owner": "govengine",
        },
    ]
