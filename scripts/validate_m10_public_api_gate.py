#!/usr/bin/env python3
"""Validate the frozen M10 Python, CLI and runtime-root compatibility surface."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "tests/test_m10_public_api.py",
    "tests/test_cli_contracts.py",
    "tests/test_package_import.py",
    "tests/test_contract_compatibility.py",
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
        "m10_public_api_gate_ok:python_import_matrix=OK:cli_classification=OK:"
        "schema_compatibility=OK:alpha_to_v1_new_root=OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
