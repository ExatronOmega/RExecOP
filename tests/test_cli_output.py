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


def test_global_format_table_on_env_lint(tmp_path) -> None:
    env_path = tmp_path / 'env.yaml'
    env_path.write_text(
        (
            'environment:\n'
            '  id: demo-env\n'
            '  profile: demo\n'
            '  targets:\n'
            '    host-1:\n'
            '      type: fixture\n'
            '  connectors:\n'
            '    fixture:\n'
            '      enabled: true\n'
            '      backend: static_fixture\n'
            '      fixture_only: true\n'
            '      actions:\n'
            '        read:\n'
            '          data:\n'
            '            ok: true\n'
        ),
        encoding='utf-8',
    )

    result = runner.invoke(
        app,
        ['--format', 'table', 'env', 'lint', '--env', str(env_path)],
    )

    assert result.exit_code == 0
    assert 'env lint status=passed' in result.stdout
    assert 'environment=demo-env' in result.stdout


def test_global_json_on_policy_explain_failure_emits_cli_error(tmp_path) -> None:
    result = runner.invoke(
        app,
        [
            '--json',
            'policy',
            'explain',
            '--intent',
            'missing',
            '--target',
            'host-1',
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload['schema'] == CLI_ERROR_SCHEMA
    assert payload['command'] == 'policy explain'


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