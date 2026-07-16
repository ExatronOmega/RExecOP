#!/usr/bin/env python3
"""Run the GovEngine v1 release-candidate cross-stack behavior gate."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "tests/test_typed_execution_governance.py::"
    "test_workflow_runner_allows_readonly_fixture_with_matching_governance",
    "tests/test_typed_execution_governance.py::"
    "test_workflow_runner_enforces_typed_execution_governance_before_backend_io",
    "tests/test_typed_execution_governance.py::test_blocked_network_boundary_mismatch",
    "tests/test_http_api_connector.py::"
    "test_http_api_reads_fixture_state_against_staging_server",
    "tests/test_http_api_connector.py::test_http_api_blocks_mutating_without_governance",
    "tests/test_http_api_connector.py::test_stable_http_rejects_plaintext_before_io",
    "tests/test_http_api_connector.py::"
    "test_resolved_http_destination_must_match_declared_binding_before_io",
    "tests/test_g3_runtime_governance.py::"
    "test_signed_decision_is_bound_claimed_and_projected_to_runtime_permit",
    "tests/test_sclite_full_bundle.py::test_full_bundle_review_verdict_pass",
    "tests/test_sclite_full_bundle.py::"
    "test_review_bundle_matches_sclite_govengine_integration_shape",
)


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *TESTS],
        cwd=ROOT,
        env={**os.environ, "REXECOP_SIGNOFF_INNER": "1"},
        check=False,
    )
    if result.returncode:
        return result.returncode
    print(
        "g6_release_candidate_gate_ok:"
        "readonly_no_network_positive=OK:"
        "network_policy_negative=OK:"
        "governed_http_positive=OK:"
        "http_pre_io_negative=OK:"
        "signed_decision_receipt_binding=OK:"
        "sclite_review_bundle=OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
