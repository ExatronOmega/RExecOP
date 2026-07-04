from __future__ import annotations

from pathlib import Path
from typing import Any

from govengine import explain_profile_governance

from rexecop.profile.loader import load_profile
from rexecop.profile.resolver import resolve_profile_path

PROFILE_GOVERNANCE_BUNDLE_SCHEMA = "rexecop.profile_governance_bundle.v0.1"


def build_profile_governance_request(
    profile: str | Path,
    *,
    track: str = "readonly",
) -> dict[str, Any]:
    loaded = load_profile(resolve_profile_path(profile))
    operations_summary = _required_capabilities(profile)
    from rexecop.connectors.registry import list_connector_backend_descriptors
    from rexecop.profile import discoverability as profile_discoverability

    capabilities = profile_discoverability.list_capabilities_manifest()
    connectors = {
        "connector_backends": [
            item.as_dict() for item in list_connector_backend_descriptors()
        ]
    }
    tracks = _supported_tracks(track)
    return {
        "schema_version": "v0.1",
        "request_id": f"rexecop-profile-governance:{loaded.name}:{track}",
        "profile_name": loaded.name,
        "profile_version": loaded.version,
        "supported_tracks": tracks,
        "policy_hooks": [
            {
                "name": "runtime_admission_gate",
                "hook_type": "admission",
            }
        ],
        "evidence_expectations": [
            {
                "name": "receipt_bounded_execution",
                "receipt_bound_required": True,
                "claim_types": ["execution_truth"],
            }
        ],
        "runner_posture": {
            "name": "rexecop_default_dry_run",
            "mode": "dry_run",
            "live_enabled": False,
        },
        "required_capabilities": operations_summary,
        "profile_declared_capabilities": operations_summary,
        "available_capabilities": [
            item["capability"] for item in capabilities["capabilities"]
        ],
        "connector_backends": connectors["connector_backends"],
    }


def evaluate_profile_governance(
    profile: str | Path,
    *,
    track: str = "readonly",
) -> dict[str, Any]:
    request = build_profile_governance_request(profile, track=track)
    bundle = explain_profile_governance(request)
    payload = bundle.as_dict()
    return {
        "schema": PROFILE_GOVERNANCE_BUNDLE_SCHEMA,
        "status": payload["status"],
        "profile": payload["profile_name"],
        "track": track,
        "request_id": payload["request_id"],
        "bundle_digest": payload["bundle_digest"],
        "governance": payload["governance"],
        "compatibility": payload["compatibility"],
        "non_claims": list(payload["non_claims"]),
    }


def _required_capabilities(profile: str | Path) -> list[str]:
    from rexecop.catalog.service import compile_operation_descriptor
    from rexecop.errors import RExecOpValidationError

    loaded = load_profile(resolve_profile_path(profile))
    capabilities: set[str] = set()
    intents_dir = loaded.root / "intents"
    if not intents_dir.is_dir():
        return []
    for path in sorted(intents_dir.glob("*.yaml")):
        try:
            operation = compile_operation_descriptor(loaded, path.stem)
        except RExecOpValidationError:
            continue
        capabilities.update(operation.required_capabilities)
    return sorted(capabilities)


def _supported_tracks(track: str) -> list[str]:
    if track == "readonly":
        return ["readonly"]
    if track == "mutation":
        return ["readonly", "mutation"]
    return ["readonly", "mutation", "all"]