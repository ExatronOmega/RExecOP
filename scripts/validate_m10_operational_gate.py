#!/usr/bin/env python3
"""Validate the bounded, public-safe M10 operational qualification record."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "release-qualification" / "m10-operational.json"
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
PASS_FIELDS = (
    "clean_wheel_install",
    "pip_check",
    "stable_doctor",
    "target_identity_cross_check",
    "bounded_read_only_workflow",
    "operation_validation",
    "remote_temp_cleanup",
)
ZERO_DISCLOSURE_FIELDS = (
    "public_projection_private_address_matches",
    "public_projection_private_hostname_matches",
    "public_projection_identity_path_matches",
    "public_projection_known_hosts_path_matches",
    "public_projection_credential_ref_matches",
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def validate_record(record: Mapping[str, Any], *, source_version: str) -> list[str]:
    errors: list[str] = []
    if record.get("schema") != "rexecop.operational_qualification.v1":
        errors.append("operational_qualification_schema_invalid")

    scope = _mapping(record.get("scope"))
    qualified = _mapping(scope.get("qualified_source"))
    if source_version not in {qualified.get("version"), scope.get("target_release")}:
        errors.append("operational_qualification_version_drift")
    if not HEX_40.fullmatch(str(qualified.get("commit", ""))):
        errors.append("operational_qualification_source_commit_invalid")
    if scope.get("live_infrastructure_touched") is not True:
        errors.append("operational_qualification_live_journey_missing")
    if scope.get("live_mutations_performed") is not False:
        errors.append("operational_qualification_live_mutation_detected")

    stack = _mapping(record.get("stack"))
    for package in ("sclite-core", "govengine", "rexecop", "tecrax"):
        entry = _mapping(stack.get(package))
        if not entry.get("version"):
            errors.append(f"operational_qualification_stack_version_missing:{package}")
        if not HEX_40.fullmatch(str(entry.get("commit", ""))):
            errors.append(f"operational_qualification_stack_commit_invalid:{package}")

    artifacts = _mapping(record.get("artifacts"))
    for name in (
        "rexecop_wheel_sha256",
        "rexecop_sdist_sha256",
        "tecrax_wheel_sha256",
        "tecrax_sdist_sha256",
    ):
        if not HEX_64.fullmatch(str(artifacts.get(name, ""))):
            errors.append(f"operational_qualification_artifact_digest_invalid:{name}")

    checks = _mapping(record.get("checks"))
    for name in PASS_FIELDS:
        if checks.get(name) != "passed":
            errors.append(f"operational_qualification_check_failed:{name}")
    if checks.get("govengine_client_used") is not True:
        errors.append("operational_qualification_govengine_client_missing")
    if checks.get("static_govengine_adapter_used") is not False:
        errors.append("operational_qualification_static_adapter_used")

    recovery = _mapping(record.get("recovery"))
    crash = _mapping(recovery.get("post_io_crash"))
    expected_recovery = {
        "pre_io_failure_attempt_count": 0,
        "first_recovery_indeterminate_count": 1,
        "retry_block_reason": "outcome_indeterminate",
        "second_recovery_indeterminate_count": 0,
        "first_projection_reconciliation_count": 1,
        "second_projection_reconciliation_count": 0,
        "result": "passed",
    }
    for name, expected in expected_recovery.items():
        if recovery.get(name) != expected:
            errors.append(f"operational_qualification_recovery_invalid:{name}")
    if crash.get("durable_started_attempt") is not True:
        errors.append("operational_qualification_crash_attempt_missing")
    if crash.get("backend") != "local_shell_readonly":
        errors.append("operational_qualification_post_io_backend_invalid")
    if crash.get("backend_io_completed_before_crash") is not True:
        errors.append("operational_qualification_post_io_not_proven")
    if crash.get("raw_output_retained") is not False:
        errors.append("operational_qualification_post_io_raw_output_retained")
    if not HEX_64.fullmatch(str(crash.get("result_sha256", ""))):
        errors.append("operational_qualification_post_io_digest_invalid")
    if not HEX_64.fullmatch(str(recovery.get("recovery_result_sha256", ""))):
        errors.append("operational_qualification_recovery_digest_invalid")

    projections = _mapping(record.get("projections"))
    for name in ("receipt_show", "truth_path", "support_bundle"):
        entry = _mapping(projections.get(name))
        if not entry.get("schema"):
            errors.append(f"operational_qualification_projection_schema_missing:{name}")
        if not HEX_64.fullmatch(str(entry.get("sha256", ""))):
            errors.append(f"operational_qualification_projection_digest_invalid:{name}")

    disclosure = _mapping(record.get("disclosure"))
    for name in ZERO_DISCLOSURE_FIELDS:
        if disclosure.get(name) != 0:
            errors.append(f"operational_qualification_disclosure_detected:{name}")
    if disclosure.get("raw_runtime_contains_operator_topology") is not True:
        errors.append("operational_qualification_raw_runtime_scope_undeclared")
    if disclosure.get("raw_runtime_publication_prohibited") is not True:
        errors.append("operational_qualification_raw_runtime_publication_allowed")
    if disclosure.get("private_runtime_retained") is not False:
        errors.append("operational_qualification_private_runtime_retained")
    if disclosure.get("result") != "passed":
        errors.append("operational_qualification_disclosure_check_failed")

    review = _mapping(record.get("independent_review"))
    if review.get("included_in_this_record") is not False:
        errors.append("operational_qualification_review_scope_confused")
    return errors


def main() -> int:
    try:
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        print(f"m10_operational_gate_error:{exc}", file=sys.stderr)
        return 1
    if not isinstance(record, dict):
        print("m10_operational_gate_error:record_not_object", file=sys.stderr)
        return 1
    errors = validate_record(record, source_version=str(project["project"]["version"]))
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(
        "m10_operational_gate_ok:clean_install=OK:readonly=OK:recovery=OK:"
        "disclosure=OK:live_mutation=NONE:independent_review=SEPARATE"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
