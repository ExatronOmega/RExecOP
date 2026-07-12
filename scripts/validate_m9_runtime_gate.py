#!/usr/bin/env python3
"""Run the certified single-host M9 concurrency and crash-correctness gate."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-m", "m9_runtime"],
        cwd=ROOT,
        env={**os.environ, "REXECOP_SIGNOFF_INNER": "1"},
        check=False,
    )
    if result.returncode:
        return result.returncode
    print(
        "m9_runtime_gate_ok:single_executor=OK:queue_claim=OK:operation_cas=OK:"
        "durable_attempt=OK:outcome_indeterminate=OK:projection_reconcile=OK:"
        "filestore_stable_single_host=OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
