from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_supply_chain_gate.py"


def _load():
    spec = importlib.util.spec_from_file_location("rexecop_validate_supply_chain_gate", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_supply_chain_gate_filters_documented_exceptions() -> None:
    gate = _load()
    findings = [
        {"id": "GHSA-aaaa-bbbb-cccc", "name": "demo", "version": "1.0.0"},
        {"id": "GHSA-dddd-eeee-ffff", "name": "other", "version": "2.0.0"},
    ]
    filtered = gate.filter_findings(findings, {"GHSA-aaaa-bbbb-cccc"})
    assert filtered == [{"id": "GHSA-dddd-eeee-ffff", "name": "other", "version": "2.0.0"}]


def test_supply_chain_gate_rejects_unallowlisted_vulnerability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = _load()
    exceptions = tmp_path / "exceptions.json"
    exceptions.write_text(
        json.dumps(
            {
                "schema": gate.EXCEPTIONS_SCHEMA,
                "vulnerabilities": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        gate,
        "audit_requirements",
        lambda *_args, **_kwargs: [
            {"id": "GHSA-dddd-eeee-ffff", "name": "other", "version": "2.0.0"},
        ],
    )
    monkeypatch.setattr(
        gate,
        "install_wheel_venv",
        lambda *_args, **_kwargs: (tmp_path / "venv", tmp_path / "venv/bin/python"),
    )
    monkeypatch.setattr(
        gate,
        "_run",
        lambda command, **kwargs: type(
            "Result",
            (),
            {"returncode": 0, "stdout": "demo==1.0.0\n", "stderr": ""},
        )(),
    )
    monkeypatch.setattr(
        gate,
        "generate_sbom",
        lambda *_args, **_kwargs: None,
    )
    errors = gate.collect_errors(tmp_path, exceptions_path=exceptions, write_sbom=True)
    assert any(
        error.startswith("unallowlisted_vulnerability:GHSA-dddd-eeee-ffff")
        for error in errors
    )


def test_supply_chain_gate_cli_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gate = _load()
    version = gate.project_version()
    sbom = tmp_path / f"rexecop-{version}.cdx.json"
    monkeypatch.setattr(gate, "collect_errors", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(gate, "sbom_output_path", lambda *_args, **_kwargs: sbom)
    assert gate.main([str(tmp_path)]) == 0
