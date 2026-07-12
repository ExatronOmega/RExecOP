#!/usr/bin/env python3
"""Run the bounded M8.6 connector/disclosure security regression gate."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    command = [sys.executable, "-m", "pytest", "-q", "-m", "security_regression"]
    result = subprocess.run(
        command,
        cwd=ROOT,
        env={**os.environ, "REXECOP_SIGNOFF_INNER": "1"},
        check=False,
    )
    if result.returncode:
        return result.returncode
    print(
        "m86_security_gate_ok:"
        "http_origin_redirect_pagination=OK:"
        "dns_egress_posture=OK:ssh_fail_closed=OK:"
        "audience_negative_data=OK:admission_receipt_binding=OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
