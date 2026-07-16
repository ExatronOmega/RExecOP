#!/usr/bin/env python3
"""Run the wheel-shipped GovEngine v1 corpus through the RExecOp consumer."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from govengine.conformance import assert_conformance_outcome, iter_conformance_cases  # noqa: E402

from rexecop.conformance import run_rexecop_conformance_case  # noqa: E402


def main() -> int:
    cases = iter_conformance_cases()
    with tempfile.TemporaryDirectory(prefix="rexecop-conformance-") as temporary:
        root = Path(temporary)
        for case in cases:
            outcome = run_rexecop_conformance_case(
                case,
                store_root=root / str(case["case_id"]),
            )
            assert_conformance_outcome(case, outcome, runner="rexecop")
    print(f"governance_conformance_ok:cases={len(cases)}:runtime_owned=6")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
