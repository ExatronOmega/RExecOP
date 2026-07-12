from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_evidence.py"


def _load():
    spec = importlib.util.spec_from_file_location("rexecop_release_evidence", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_distribution_digests_require_wheel_and_sdist(tmp_path: Path) -> None:
    evidence = _load()
    (tmp_path / "rexecop-1.0.0-py3-none-any.whl").write_bytes(b"wheel")
    try:
        evidence.distribution_digests(tmp_path)
    except ValueError as exc:
        assert str(exc) == "release_evidence_missing_sdist"
    else:
        raise AssertionError("missing sdist must fail closed")


def test_public_artifact_identity_mismatch_is_rejected() -> None:
    evidence = _load()
    record = {
        "schema": evidence.SCHEMA,
        "status": "passed",
        "version": "1.0.0",
        "source_commit": "a" * 40,
        "workflow_run_id": "123",
        "workflow_run_url": "https://github.com/rozmiarD/RExecOP/actions/runs/123",
        "artifacts": {
            "rexecop-1.0.0-py3-none-any.whl": "b" * 64,
            "rexecop-1.0.0.tar.gz": "c" * 64,
        },
        "public_artifacts": {
            "rexecop-1.0.0-py3-none-any.whl": "d" * 64,
            "rexecop-1.0.0.tar.gz": "c" * 64,
        },
        "installed_versions": {
            "rexecop": "1.0.0",
            "govengine": "1.0.0",
            "sclite-core": "2.0.0",
            "tecrax": "1.0.0",
        },
        "doctor_status": "passed",
    }
    sealed = evidence.seal_record(record)
    assert "release_evidence_public_artifact_identity_mismatch" in evidence.validate_record(
        sealed,
        expected_version="1.0.0",
    )
