from __future__ import annotations

from pathlib import Path

from govengine.conformance import (
    assert_conformance_outcome,
    iter_conformance_cases,
)

from rexecop.conformance import run_rexecop_conformance_case


def test_rexecop_consumes_all_govengine_v1_conformance_cases(
    tmp_path: Path,
) -> None:
    cases = iter_conformance_cases()

    assert len(cases) == 33
    assert sum(case['owner'] == 'rexecop' for case in cases) == 6
    for case in cases:
        outcome = run_rexecop_conformance_case(
            case,
            store_root=tmp_path / str(case['case_id']),
        )
        assert_conformance_outcome(case, outcome, runner='rexecop')
