#!/usr/bin/env python3
"""Run the bounded M9.5N execution-kernel stabilization gate."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "tests/test_m95_runtime_ports.py",
    "tests/test_m95_execution_permit.py",
    "tests/test_m95_reason_codes.py",
    "tests/test_m95_plugin_contract.py",
    "tests/test_package_import.py",
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
        "m95n_gate_ok:runtime_ports=OK:execution_permit=OK:reason_codes=OK:"
        "trusted_plugins=OK:fresh_subprocess_imports=OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
