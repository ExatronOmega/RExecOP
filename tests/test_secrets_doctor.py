from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from rexecop.cli import app
from rexecop.secrets.doctor import REDACTION_PROBE, run_secrets_doctor

ROOT = Path(__file__).resolve().parents[1]
STAGING_ENV = ROOT / "examples/environments/runtime-fixture.staging.example.yaml"

runner = CliRunner()


def _write_secrets_file(path: Path, values: dict[str, str]) -> None:
    path.write_text(yaml.safe_dump({"secrets": values}))
    path.chmod(0o600)


def test_secrets_doctor_passes_with_env_backed_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REXECOP_SECRET_FIXTURE_API_TOKEN", "hidden-token-value")
    monkeypatch.setenv("REXECOP_SECRET_FIXTURE_BASE_URL", "https://fixture.example")

    result = run_secrets_doctor(env_path=STAGING_ENV)

    assert result["status"] == "passed"
    assert result["blockers"] == []
    assert "missing_refs" not in result["blockers"]
    rendered = json.dumps(result, sort_keys=True)
    assert "hidden-token-value" not in rendered
    assert REDACTION_PROBE not in rendered


def test_secrets_doctor_reports_missing_refs(tmp_path: Path) -> None:
    env_path = tmp_path / "env.yaml"
    env_path.write_text(
        yaml.safe_dump(
            {
                "environment": {
                    "id": "secrets-doctor-missing",
                    "profile": "runtime_fixture",
                    "targets": {"host": {"type": "fixture", "criticality": "low"}},
                    "connectors": {
                        "fixture_source": {
                            "enabled": True,
                            "backend": "http_api",
                            "auth": {"secret_ref": "missing_token"},
                        }
                    },
                }
            }
        )
    )

    result = run_secrets_doctor(env_path=env_path)

    assert result["status"] == "blocker"
    assert "missing_refs" in result["blockers"]
    missing = next(
        check for check in result["checks"] if check["id"] == "missing_refs"
    )
    assert missing["details"]["missing"][0]["ref"] == "missing_token"


def test_secrets_doctor_reports_duplicate_ref_usage(tmp_path: Path) -> None:
    env_path = tmp_path / "env.yaml"
    env_path.write_text(
        yaml.safe_dump(
            {
                "environment": {
                    "id": "secrets-doctor-duplicate",
                    "profile": "runtime_fixture",
                    "targets": {"host": {"type": "fixture", "criticality": "low"}},
                    "connectors": {
                        "fixture_source": {
                            "enabled": True,
                            "backend": "http_api",
                            "base_url_secret_ref": "shared_ref",
                            "auth": {"secret_ref": "shared_ref"},
                        }
                    },
                }
            }
        )
    )
    secrets_file = tmp_path / "secrets.yaml"
    _write_secrets_file(secrets_file, {"shared_ref": "shared-value"})

    result = run_secrets_doctor(env_path=env_path, secrets_file=secrets_file)

    assert result["status"] == "warning"
    assert "duplicate_refs" in result["warnings"]
    assert "shared-value" not in json.dumps(result)


def test_secrets_doctor_reports_secrets_file_permission_blocker(tmp_path: Path) -> None:
    env_path = tmp_path / "env.yaml"
    env_path.write_text(
        yaml.safe_dump(
            {
                "environment": {
                    "id": "secrets-doctor-perms",
                    "profile": "runtime_fixture",
                    "targets": {"host": {"type": "fixture", "criticality": "low"}},
                    "connectors": {
                        "fixture_source": {
                            "enabled": True,
                            "backend": "http_api",
                            "auth": {"secret_ref": "fixture_api_token"},
                        }
                    },
                }
            }
        )
    )
    secrets_file = tmp_path / "secrets.yaml"
    _write_secrets_file(secrets_file, {"fixture_api_token": "hidden"})
    secrets_file.chmod(0o640)

    result = run_secrets_doctor(env_path=env_path, secrets_file=secrets_file)

    assert result["status"] == "blocker"
    assert "secrets_file_permissions" in result["blockers"]
    assert "hidden" not in json.dumps(result)


def test_secrets_doctor_redaction_self_test_passes() -> None:
    result = run_secrets_doctor(env_path=STAGING_ENV)
    redaction = next(
        check for check in result["checks"] if check["id"] == "redaction_self_test"
    )
    assert redaction["status"] == "passed"


def test_cli_secrets_doctor_requires_input() -> None:
    result = runner.invoke(app, ["secrets", "doctor"])
    assert result.exit_code == 1
    assert "provide --env and/or --catalog" in result.stderr


def test_cli_secrets_doctor_passes_with_env_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REXECOP_SECRET_FIXTURE_API_TOKEN", "hidden-token-value")
    monkeypatch.setenv("REXECOP_SECRET_FIXTURE_BASE_URL", "https://fixture.example")

    result = runner.invoke(app, ["secrets", "doctor", "--env", str(STAGING_ENV)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema"] == "rexecop.secrets_doctor.v0.1"
    assert payload["status"] == "passed"
    assert "hidden-token-value" not in result.stdout