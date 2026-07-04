from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from rexecop.cli import app
from rexecop.cli_errors import CLI_ERROR_SCHEMA
from rexecop.errors import RExecOpError

runner = CliRunner()


def test_global_json_flag_on_init_emits_runtime_init_schema(tmp_path) -> None:
    root = tmp_path / 'runtime'
    result = runner.invoke(app, ['--root', str(root), '--json', 'init'])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload['status'] == 'initialized'
    assert payload['root'] == str(root)


def test_global_format_table_on_doctor_renders_human_summary(tmp_path) -> None:
    root = tmp_path / 'runtime'
    runner.invoke(app, ['--root', str(root), 'init'])
    result = runner.invoke(app, ['--root', str(root), '--format', 'table', 'doctor'])

    assert result.exit_code == 1
    assert 'doctor status=blocker' in result.stdout
    assert 'runtime_root' not in result.stdout


def test_global_format_markdown_on_init_renders_heading(tmp_path) -> None:
    root = tmp_path / 'runtime'
    result = runner.invoke(
        app,
        ['--root', str(root), '--format', 'markdown', 'init', '--guided'],
    )

    assert result.exit_code == 0
    assert '# RExecOp init' in result.stdout
    assert 'next_steps' not in result.stdout


def test_global_json_init_failure_emits_cli_error_envelope(tmp_path) -> None:
    root = tmp_path / 'runtime'

    with patch(
        'rexecop.cli.initialize_runtime_root',
        side_effect=RExecOpError('runtime root is not writable'),
    ):
        result = runner.invoke(app, ['--root', str(root), '--json', 'init'])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload['schema'] == CLI_ERROR_SCHEMA
    assert payload['command'] == 'init'
    assert payload['reason_code'] == 'runtime_init_failed'