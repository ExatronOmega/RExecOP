import json
from pathlib import Path

from typer.testing import CliRunner

from rexecop import __version__
from rexecop.cli import app

runner = CliRunner()


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "rexecop" in result.stdout.lower()


def test_cli_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_cli_watchdog_manual_record(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "watchdog",
            "manual-record",
            "--action",
            "mark_stale",
            "--reason",
            "operator_break_glass",
            "--actor-ref",
            "operator:local-admin",
            "--scope",
            "operation:op-1",
            "--operation",
            "op-1",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["decision"] == "mark_stale"
    artifacts = list(Path(".rexecop/watchdog/sclite").glob("*.json"))
    assert len(artifacts) == 1
    artifact = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert artifact["manual_recovery"]["actor_ref"] == "operator:local-admin"
    assert artifact["admission"]["allowed"] is True
