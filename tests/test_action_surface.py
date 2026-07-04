from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import yaml
from typer.testing import CliRunner

from rexecop.action.surface import (
    ACTION_LIST_SCHEMA,
    ACTION_SHOW_SCHEMA,
    ACTION_VALIDATE_SCHEMA,
    list_actions,
    show_action,
    validate_actions,
)
from rexecop.cli import app

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "examples/first-run-demo/profile/profile.yaml"
ENVIRONMENT = ROOT / "examples/first-run-demo/environment.yaml"
CATALOG = ROOT / "examples/first-run-demo/catalog.yaml"

runner = CliRunner()


def test_action_list_reports_profile_env_actions_without_backend_io() -> None:
    with patch("rexecop.connectors.http_api.urllib.request.urlopen") as backend:
        payload = list_actions(profile=PROFILE, env=ENVIRONMENT)

    backend.assert_not_called()
    assert payload["schema"] == ACTION_LIST_SCHEMA
    actions = {item["id"]: item for item in payload["actions"]}
    assert set(actions) == {"inspect"}
    assert actions["inspect"]["backend_classes"] == ["static_fixture"]
    assert actions["inspect"]["side_effect_class"] == "none"
    assert actions["inspect"]["operation_descriptor_digest"]
    assert payload["non_claims"]


def test_action_show_redacts_config_and_reports_contract_sources() -> None:
    payload = show_action("inspect", profile=PROFILE, env=ENVIRONMENT)

    assert payload["schema"] == ACTION_SHOW_SCHEMA
    assert payload["action"]["id"] == "inspect"
    assert payload["source_contracts"]["profile_digest"]
    assert payload["source_contracts"]["environment_digest"]
    assert payload["workflow"]["connector_steps"] == [
        {
            "id": "read",
            "connector": "fixture",
            "action": "read",
            "backend_class": "static_fixture",
            "enabled": True,
            "shape_digest": "",
            "contract_declared": True,
            "environment_configured": True,
        }
    ]
    rendered = json.dumps(payload, sort_keys=True)
    assert "secret_ref" not in rendered
    assert "first-run-demo" not in rendered
    assert "Does not request or imply GovEngine admission." in payload["non_claims"]


def test_action_validate_all_passes_without_backend_io() -> None:
    with patch("rexecop.connectors.http_api.urllib.request.urlopen") as backend:
        payload = validate_actions(profile=PROFILE, env=ENVIRONMENT)

    backend.assert_not_called()
    assert payload["schema"] == ACTION_VALIDATE_SCHEMA
    assert payload["status"] == "passed"
    assert payload["actions_checked"] == ["inspect"]
    assert payload["blockers"] == []


def test_action_list_can_resolve_profile_and_env_from_catalog() -> None:
    payload = list_actions(catalog=CATALOG, target="fixture-target")

    assert payload["catalog"]["digest"]
    assert payload["catalog"]["target"] == "fixture-target"
    assert str(CATALOG) not in json.dumps(payload, sort_keys=True)
    assert payload["actions"][0]["applicability"]["applicable"] is True


def test_action_validate_reports_shape_drift_without_backend_io(tmp_path: Path) -> None:
    env = yaml.safe_load(ENVIRONMENT.read_text(encoding="utf-8"))
    env["environment"]["connectors"]["fixture"]["enabled"] = False
    env_path = tmp_path / "drift-env.yaml"
    env_path.write_text(yaml.safe_dump(env, sort_keys=False), encoding="utf-8")

    with patch("rexecop.connectors.http_api.urllib.request.urlopen") as backend:
        payload = validate_actions(
            profile=PROFILE,
            env=env_path,
            intent="inspect",
        )

    backend.assert_not_called()
    assert payload["status"] == "failed"
    assert "inspect:workflow_contract" in payload["blockers"]
    check = next(
        item
        for item in payload["checks"][0]["checks"]
        if item["id"] == "workflow_contract"
    )
    assert check["id"] == "workflow_contract"
    assert "connector disabled" in check["summary"]


def test_cli_action_commands_emit_json() -> None:
    commands = [
        ["action", "list", "--profile", str(PROFILE), "--env", str(ENVIRONMENT)],
        [
            "action",
            "show",
            "inspect",
            "--profile",
            str(PROFILE),
            "--env",
            str(ENVIRONMENT),
        ],
        [
            "action",
            "validate",
            "--all",
            "--profile",
            str(PROFILE),
            "--env",
            str(ENVIRONMENT),
        ],
    ]
    for command in commands:
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.stdout + result.stderr
        assert isinstance(json.loads(result.stdout), dict)


def test_cli_action_validate_requires_scope() -> None:
    result = runner.invoke(
        app,
        ["action", "validate", "--profile", str(PROFILE), "--env", str(ENVIRONMENT)],
    )

    assert result.exit_code == 1
    assert "requires --all or --intent" in result.stderr
