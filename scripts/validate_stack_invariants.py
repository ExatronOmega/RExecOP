#!/usr/bin/env python3
"""Run the stack invariant pytest suite for M8.5 property/invariant gates."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVARIANT_SCOPE = ROOT / "tests" / "invariant_scope.py"
INVARIANT_MODULE = ROOT / "tests" / "test_stack_invariants.py"


def collect_errors() -> list[str]:
    errors: list[str] = []
    if not INVARIANT_SCOPE.is_file():
        errors.append(f"missing_invariant_scope:{INVARIANT_SCOPE}")
    if not INVARIANT_MODULE.is_file():
        errors.append(f"missing_invariant_tests:{INVARIANT_MODULE}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run stack invariant pytest gate.")
    parser.add_argument(
        "--pytest-args",
        nargs=argparse.REMAINDER,
        help="Extra args forwarded to pytest after -m invariant.",
    )
    args = parser.parse_args(argv)

    errors = collect_errors()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    command = [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        "invariant",
        "-q",
        str(ROOT / "tests" / "test_stack_invariants.py"),
    ]
    if args.pytest_args:
        command.extend(args.pytest_args)

    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        return completed.returncode
    print("stack_invariants_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
