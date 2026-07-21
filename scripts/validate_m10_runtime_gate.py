#!/usr/bin/env python3
"""Run the M10 stable runtime qualification gate."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "tests/test_m10_runtime_qualification.py",
    "tests/test_m9_storage_certification.py",
    "tests/test_m95_plugin_contract.py::test_stable_doctor_requires_explicit_plugin_allowlist",
    "tests/test_network_egress_doctor.py",
    "tests/test_mutation_posture.py::test_doctor_reports_stable_read_only_as_certified",
    "tests/test_mutation_posture.py::test_doctor_blocks_nonstable_mutation_posture",
)


def _run(command: list[str]) -> int:
    return subprocess.run(
        command,
        cwd=ROOT,
        env={**os.environ, "REXECOP_SIGNOFF_INNER": "1"},
        check=False,
    ).returncode


def main() -> int:
    m9_result = _run([sys.executable, "scripts/validate_m9_runtime_gate.py"])
    if m9_result:
        return m9_result
    test_result = _run([sys.executable, "-m", "pytest", "-q", *TESTS])
    if test_result:
        return test_result
    print(
        "m10_runtime_gate_ok:m9_runtime=OK:storage_tier=OK:single_executor=OK:"
        "mutation_posture=OK:plugin_inventory=OK:security_blockers=OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
