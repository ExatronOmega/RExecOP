from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from invariant_scope import INVARIANT_TEST_MODULE, INVARIANT_THEMES

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_invariant_module_exists() -> None:
    assert (REPO_ROOT / "tests" / f"{INVARIANT_TEST_MODULE}.py").is_file()


def test_invariant_themes_are_documented() -> None:
    assert len(INVARIANT_THEMES) >= 5


@pytest.mark.invariant
def test_validate_stack_invariants_gate_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/validate_stack_invariants.py"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "stack_invariants_ok" in result.stdout


def test_validate_external_review_gate_passes_for_current_line() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/validate_external_review_gate.py"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "external_review_gate_ok" in result.stdout


def test_validate_external_review_gate_rejects_missing_record(tmp_path: Path) -> None:
    script = REPO_ROOT / "scripts" / "validate_external_review_gate.py"
    result = subprocess.run(
        [sys.executable, str(script), "--version", "9.9.9-not-published"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "review_record_missing" in result.stderr


def test_validate_external_review_gate_rejects_incomplete_surfaces() -> None:
    record = {
        "schema": "rexecop.release_security_review.v0.1",
        "version": "0.0.0-test",
        "review_mode": "solo_reviewed_alpha_risk",
        "reviewed_at": "2026-07-08",
        "reviewer_ref": "reviewer:test",
        "surfaces": ["governance_admission_binding"],
        "notes": "incomplete test fixture",
    }
    module = _load_gate_module("validate_external_review_gate")
    errors = module.validate_review_record(record, version="0.0.0-test")
    assert any(error.startswith("review_surfaces_missing:") for error in errors)


def _load_gate_module(name: str):
    import importlib.util

    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"rexecop_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
