"""Compatibility policy for persisted runtime roots."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from rexecop.errors import RExecOpValidationError

RUNTIME_ROOT_COMPATIBILITY_SCHEMA = "rexecop.runtime_root_compatibility.v1"
RUNTIME_ROOT_UPGRADE_POLICY = "alpha_root_requires_new_v1_root"
SUPPORTED_RUNTIME_MANIFEST_SCHEMA = "rexecop.runtime_init.v0.1"

_VERSION_MAJOR = re.compile(r"^(\d+)(?:[.]|$)")


def _major(version: object) -> int | None:
    match = _VERSION_MAJOR.match(str(version or "").strip())
    return int(match.group(1)) if match else None


def runtime_root_compatibility(
    manifest: Mapping[str, Any],
    *,
    target_version: str,
) -> dict[str, Any]:
    stored_version = str(manifest.get("rexecop_version") or "").strip()
    manifest_schema = str(manifest.get("schema") or "").strip()
    stored_major = _major(stored_version)
    target_major = _major(target_version)

    reason_code = "runtime_root_compatible"
    status = "compatible"
    if manifest_schema != SUPPORTED_RUNTIME_MANIFEST_SCHEMA:
        status = "blocked"
        reason_code = "runtime_root_manifest_schema_unsupported"
    elif stored_major is None or target_major is None:
        status = "blocked"
        reason_code = "runtime_root_version_invalid"
    elif stored_major == 0 and target_major >= 1:
        status = "new_root_required"
        reason_code = "runtime_root_new_root_required"
    elif stored_major > target_major:
        status = "blocked"
        reason_code = "runtime_root_downgrade_unsupported"
    elif stored_major != target_major:
        status = "blocked"
        reason_code = "runtime_root_major_version_unsupported"

    return {
        "schema": RUNTIME_ROOT_COMPATIBILITY_SCHEMA,
        "status": status,
        "reason_code": reason_code,
        "policy": RUNTIME_ROOT_UPGRADE_POLICY,
        "manifest_schema": manifest_schema,
        "stored_version": stored_version,
        "target_version": target_version,
        "in_place_upgrade_supported": status == "compatible",
        "new_root_required": status == "new_root_required",
    }


def require_runtime_root_compatible(
    manifest: Mapping[str, Any],
    *,
    target_version: str,
) -> dict[str, Any]:
    decision = runtime_root_compatibility(manifest, target_version=target_version)
    if decision["status"] != "compatible":
        raise RExecOpValidationError(str(decision["reason_code"]))
    return decision


__all__ = [
    "RUNTIME_ROOT_COMPATIBILITY_SCHEMA",
    "RUNTIME_ROOT_UPGRADE_POLICY",
    "SUPPORTED_RUNTIME_MANIFEST_SCHEMA",
    "require_runtime_root_compatible",
    "runtime_root_compatibility",
]
