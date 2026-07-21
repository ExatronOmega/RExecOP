#!/usr/bin/env python3
"""Prove the M10 stable-read-only mutation boundary."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "tests/test_mutation_posture.py",
    "tests/test_apply_gating.py::test_apply_allowed_is_still_blocked_by_stable_runtime_posture",
    "tests/test_cli_errors.py::test_start_reports_stable_mutation_posture_reason",
    "tests/test_m95_reason_codes.py::test_runtime_reason_codes_are_typed_and_stable",
    "tests/test_tecrax_profile_integration.py::test_stable_posture_blocks_tecrax_mutation_candidate",
)


def main() -> int:
    try:
        __import__("tecrax")
    except ImportError:
        print("m10_readonly_gate_error:tecrax_candidate_not_installed", file=sys.stderr)
        return 1
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *TESTS],
        cwd=ROOT,
        env={**os.environ, "REXECOP_SIGNOFF_INNER": "1"},
        check=False,
    )
    if result.returncode:
        return result.returncode
    print(
        "m10_readonly_gate_ok:default_stable_read_only=OK:positive_gov_blocked=OK:"
        "pre_backend_io=OK:lab_only_doctor_blocker=OK:stable_reason_code=OK:"
        "tecrax_candidate_blocked=OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
