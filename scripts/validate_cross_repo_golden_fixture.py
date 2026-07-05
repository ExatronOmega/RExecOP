#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/test_cross_repo_golden_fixture.py",
    ]
    result = subprocess.run(cmd, cwd=repo, check=False)
    if result.returncode != 0:
        return result.returncode
    print(
        "cross_repo_golden_fixture_ok:"
        "tecrax_diagnosis=OK,reaction_explain=OK,chain_explain=OK,"
        "sclite_reaction_replay=OK,idempotent_recovery=OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
