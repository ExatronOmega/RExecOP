from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_workflow_security.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "rexecop_validate_workflow_security",
        SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_workflow_actions_are_pinned_to_reviewed_full_shas() -> None:
    report = _load_validator().validate_workflow_security()

    assert report["workflows"] == 3
    assert report["actions"] >= 20
