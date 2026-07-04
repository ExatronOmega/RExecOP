from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import typer

from rexecop.cli_errors import cli_error_json, cli_error_payload, validation_cli_error

CLI_OUTPUT_CONTEXT_SCHEMA = 'rexecop.cli_output_context.v0.1'
SUPPORTED_FORMATS = frozenset({'json', 'table', 'markdown'})


@dataclass(frozen=True)
class CliOutputContext:
    json_mode: bool = False
    output_format: str = 'json'
    quiet: bool = False
    verbose: bool = False
    no_color: bool = False


_DEFAULT_CONTEXT = CliOutputContext()
_OUTPUT_CONTEXT: ContextVar[CliOutputContext] = ContextVar(
    'rexecop_cli_output',
    default=_DEFAULT_CONTEXT,
)


def configure_cli_output(
    *,
    json_mode: bool = False,
    output_format: str = 'json',
    quiet: bool = False,
    verbose: bool = False,
    no_color: bool = False,
) -> None:
    normalized = output_format.strip().lower() or 'json'
    if normalized not in SUPPORTED_FORMATS:
        normalized = 'json'
    _OUTPUT_CONTEXT.set(
        CliOutputContext(
            json_mode=json_mode,
            output_format=normalized,
            quiet=quiet,
            verbose=verbose,
            no_color=no_color,
        )
    )


def active_cli_output() -> CliOutputContext:
    return _OUTPUT_CONTEXT.get()


def effective_output_format(ctx: CliOutputContext | None = None) -> str:
    state = ctx or active_cli_output()
    return 'json' if state.json_mode else state.output_format


def emit_failure(
    *,
    command: tuple[str, ...],
    message: str,
    reason_code: str = 'validation_error',
    error_class: str = 'validation_error',
    details: dict[str, Any] | None = None,
    safe_next_actions: tuple[str, ...] = (),
) -> None:
    ctx = active_cli_output()
    if ctx.json_mode:
        if error_class == 'validation_error':
            payload = validation_cli_error(
                command=command,
                message=message,
                reason_code=reason_code,
                safe_next_actions=safe_next_actions,
                details=details,
            )
        else:
            payload = cli_error_payload(
                error_class=error_class,
                reason_code=reason_code,
                message=message,
                command=command,
                safe_next_actions=safe_next_actions,
                details=details,
            )
        typer.echo(cli_error_json(payload))
    elif ctx.no_color:
        typer.echo(f'error: {message}', err=True)
    else:
        typer.secho(f'error: {message}', fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def emit_failure_payload(payload: dict[str, Any]) -> None:
    ctx = active_cli_output()
    message = str(payload.get('message') or payload.get('reason_code') or 'command failed')
    if ctx.json_mode:
        typer.echo(cli_error_json(payload))
    elif ctx.no_color:
        typer.echo(f'error: {message}', err=True)
    else:
        typer.secho(f'error: {message}', fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def emit_payload(
    payload: dict[str, Any],
    *,
    renderers: Mapping[str, Callable[[dict[str, Any]], str]] | None = None,
) -> None:
    ctx = active_cli_output()
    fmt = effective_output_format(ctx)
    if fmt == 'json' or renderers is None or fmt not in renderers:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(renderers[fmt](payload))


def render_doctor_table(payload: dict[str, Any]) -> str:
    lines = [
        f"doctor status={payload.get('status')}",
        f"root={payload.get('root')}",
    ]
    blockers = payload.get('blockers') or []
    warnings = payload.get('warnings') or []
    if blockers:
        lines.append('blockers=' + ','.join(str(item) for item in blockers))
    if warnings and not active_cli_output().quiet:
        lines.append('warnings=' + ','.join(str(item) for item in warnings))
    if active_cli_output().verbose:
        for check in payload.get('checks') or []:
            if not isinstance(check, dict):
                continue
            lines.append(
                f"check {check.get('id')}:{check.get('status')}:{check.get('summary')}"
            )
    return '\n'.join(lines) + '\n'


def render_doctor_markdown(payload: dict[str, Any]) -> str:
    lines = [
        '# RExecOp doctor',
        '',
        f"- status: `{payload.get('status')}`",
        f"- root: `{payload.get('root')}`",
    ]
    blockers = payload.get('blockers') or []
    warnings = payload.get('warnings') or []
    if blockers:
        lines.extend(['', '## Blockers', ''])
        lines.extend(f"- `{item}`" for item in blockers)
    if warnings and not active_cli_output().quiet:
        lines.extend(['', '## Warnings', ''])
        lines.extend(f"- `{item}`" for item in warnings)
    if active_cli_output().verbose:
        lines.extend(['', '## Checks', ''])
        for check in payload.get('checks') or []:
            if not isinstance(check, dict):
                continue
            lines.append(
                f"- `{check.get('id')}`: {check.get('status')} — {check.get('summary')}"
            )
    return '\n'.join(lines) + '\n'


def render_init_table(payload: dict[str, Any]) -> str:
    lines = [
        f"init status={payload.get('status')}",
        f"root={payload.get('root')}",
        f"storage={payload.get('storage_backend')}",
    ]
    if payload.get('guided') and not active_cli_output().quiet:
        for step in payload.get('next_steps') or []:
            lines.append(f"next={step}")
    return '\n'.join(lines) + '\n'


def render_init_markdown(payload: dict[str, Any]) -> str:
    lines = [
        '# RExecOp init',
        '',
        f"- status: `{payload.get('status')}`",
        f"- root: `{payload.get('root')}`",
        f"- storage: `{payload.get('storage_backend')}`",
    ]
    if payload.get('guided') and not active_cli_output().quiet:
        lines.extend(['', '## Next steps', ''])
        lines.extend(f"- {step}" for step in payload.get('next_steps') or [])
    return '\n'.join(lines) + '\n'


DOCTOR_RENDERERS = {
    'table': render_doctor_table,
    'markdown': render_doctor_markdown,
}

INIT_RENDERERS = {
    'table': render_init_table,
    'markdown': render_init_markdown,
}


def _status_heading(title: str, payload: dict[str, Any]) -> list[str]:
    return [f'{title} status={payload.get("status")}']


def render_env_lint_table(payload: dict[str, Any]) -> str:
    environment = payload.get('environment') or {}
    lines = _status_heading('env lint', payload)
    lines.append(f"environment={environment.get('id')}")
    lines.append(f"profile={environment.get('profile')}")
    lines.append(f"targets={environment.get('target_count')}")
    return '\n'.join(lines) + '\n'


def render_env_lint_markdown(payload: dict[str, Any]) -> str:
    environment = payload.get('environment') or {}
    return (
        '# RExecOp env lint\n\n'
        f"- status: `{payload.get('status')}`\n"
        f"- environment: `{environment.get('id')}`\n"
        f"- profile: `{environment.get('profile')}`\n"
        f"- targets: `{environment.get('target_count')}`\n"
    )


def render_profile_lint_table(payload: dict[str, Any]) -> str:
    lines = _status_heading('profile lint', payload)
    lines.append(f"profile={payload.get('profile')}")
    lines.append(f"track={payload.get('track')}")
    if payload.get('mutation_candidate_intents') and not active_cli_output().quiet:
        lines.append(
            'mutation_candidates='
            + ','.join(str(item) for item in payload.get('mutation_candidate_intents') or [])
        )
    return '\n'.join(lines) + '\n'


def render_profile_lint_markdown(payload: dict[str, Any]) -> str:
    lines = [
        '# RExecOp profile lint',
        '',
        f"- status: `{payload.get('status')}`",
        f"- profile: `{payload.get('profile')}`",
        f"- track: `{payload.get('track')}`",
    ]
    if payload.get('mutation_candidate_intents') and not active_cli_output().quiet:
        lines.extend(['', '## Mutation candidates', ''])
        lines.extend(
            f"- `{item}`" for item in payload.get('mutation_candidate_intents') or []
        )
    return '\n'.join(lines) + '\n'


def render_policy_explain_table(payload: dict[str, Any]) -> str:
    lines = _status_heading('policy explain', payload)
    lines.append(f"decision={payload.get('decision')}")
    lines.append(f"reason={payload.get('reason_code')}")
    return '\n'.join(lines) + '\n'


def render_policy_explain_markdown(payload: dict[str, Any]) -> str:
    return (
        '# RExecOp policy explain\n\n'
        f"- status: `{payload.get('status')}`\n"
        f"- decision: `{payload.get('decision')}`\n"
        f"- reason: `{payload.get('reason_code')}`\n"
    )


def _operation_explain_fields(payload: dict[str, Any]) -> dict[str, Any]:
    operation = payload.get('operation') or {}
    if not isinstance(operation, dict):
        operation = {}
    return {
        'intent': operation.get('intent') or operation.get('intent_id'),
        'profile': operation.get('profile'),
        'title': operation.get('title'),
    }


def render_operations_explain_table(payload: dict[str, Any]) -> str:
    fields = _operation_explain_fields(payload)
    lines = ['operations explain']
    lines.append(f"intent={fields.get('intent')}")
    lines.append(f"profile={fields.get('profile')}")
    lines.append(f"title={fields.get('title')}")
    return '\n'.join(lines) + '\n'


def render_operations_explain_markdown(payload: dict[str, Any]) -> str:
    fields = _operation_explain_fields(payload)
    return (
        '# RExecOp operations explain\n\n'
        f"- intent: `{fields.get('intent')}`\n"
        f"- profile: `{fields.get('profile')}`\n"
        f"- title: `{fields.get('title')}`\n"
    )


def render_secrets_doctor_table(payload: dict[str, Any]) -> str:
    lines = _status_heading('secrets doctor', payload)
    blockers = payload.get('blockers') or []
    if blockers:
        lines.append('blockers=' + ','.join(str(item) for item in blockers))
    summary = payload.get('summary') or {}
    if isinstance(summary, dict) and 'secret_ref_count' in summary:
        lines.append(f"secret_ref_count={summary['secret_ref_count']}")
    return '\n'.join(lines) + '\n'


def render_secrets_doctor_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get('summary') or {}
    lines = [
        '# RExecOp secrets doctor',
        '',
        f"- status: `{payload.get('status')}`",
    ]
    if isinstance(summary, dict):
        for key, value in sorted(summary.items()):
            lines.append(f'- {key}: `{value}`')
    return '\n'.join(lines) + '\n'


ENV_LINT_RENDERERS = {
    'table': render_env_lint_table,
    'markdown': render_env_lint_markdown,
}

PROFILE_LINT_RENDERERS = {
    'table': render_profile_lint_table,
    'markdown': render_profile_lint_markdown,
}

POLICY_EXPLAIN_RENDERERS = {
    'table': render_policy_explain_table,
    'markdown': render_policy_explain_markdown,
}

OPERATIONS_EXPLAIN_RENDERERS = {
    'table': render_operations_explain_table,
    'markdown': render_operations_explain_markdown,
}

SECRETS_DOCTOR_RENDERERS = {
    'table': render_secrets_doctor_table,
    'markdown': render_secrets_doctor_markdown,
}


def render_lifecycle_state_table(payload: dict[str, Any]) -> str:
    lines = [
        f"operation_id={payload.get('operation_id')}",
        f"state={payload.get('state')}",
    ]
    if payload.get('current_step_id'):
        lines.append(f"current_step_id={payload.get('current_step_id')}")
    return '\n'.join(lines) + '\n'


def render_lifecycle_state_markdown(payload: dict[str, Any]) -> str:
    lines = [
        '# RExecOp operation state',
        '',
        f"- operation_id: `{payload.get('operation_id')}`",
        f"- state: `{payload.get('state')}`",
    ]
    if payload.get('current_step_id'):
        lines.append(f"- current_step_id: `{payload.get('current_step_id')}`")
    return '\n'.join(lines) + '\n'


def render_history_table(payload: dict[str, Any]) -> str:
    lines = [
        f"history operation_id={payload.get('operation_id')}",
        f"state={payload.get('state')}",
        f"transitions={len(payload.get('transitions') or [])}",
        f"evidence_events={len(payload.get('evidence_events') or [])}",
    ]
    if active_cli_output().verbose:
        for transition in payload.get('transitions') or []:
            if not isinstance(transition, dict):
                continue
            lines.append(
                f"transition {transition.get('from_state')}->{transition.get('to_state')}"
            )
    return '\n'.join(lines) + '\n'


def render_history_markdown(payload: dict[str, Any]) -> str:
    lines = [
        '# RExecOp history',
        '',
        f"- operation_id: `{payload.get('operation_id')}`",
        f"- state: `{payload.get('state')}`",
        f"- transitions: `{len(payload.get('transitions') or [])}`",
        f"- evidence_events: `{len(payload.get('evidence_events') or [])}`",
    ]
    return '\n'.join(lines) + '\n'


def render_plan_explain_table(payload: dict[str, Any]) -> str:
    operation = payload.get('operation_projection') or {}
    policy = payload.get('policy_projection') or {}
    if isinstance(operation, dict):
        op_fields = _operation_explain_fields(operation)
    else:
        op_fields = {}
    lines = [
        f"plan explain status={payload.get('status')}",
        f"intent={payload.get('intent')}",
        f"target={payload.get('target')}",
        f"mode={payload.get('mode')}",
        f"title={op_fields.get('title')}",
        f"policy_status={policy.get('status')}",
    ]
    return '\n'.join(lines) + '\n'


def render_plan_explain_markdown(payload: dict[str, Any]) -> str:
    operation = payload.get('operation_projection') or {}
    policy = payload.get('policy_projection') or {}
    if isinstance(operation, dict):
        op_fields = _operation_explain_fields(operation)
    else:
        op_fields = {}
    return (
        '# RExecOp plan explain\n\n'
        f"- status: `{payload.get('status')}`\n"
        f"- intent: `{payload.get('intent')}`\n"
        f"- target: `{payload.get('target')}`\n"
        f"- mode: `{payload.get('mode')}`\n"
        f"- title: `{op_fields.get('title')}`\n"
        f"- policy_status: `{policy.get('status')}`\n"
    )


LIFECYCLE_STATE_RENDERERS = {
    'table': render_lifecycle_state_table,
    'markdown': render_lifecycle_state_markdown,
}

HISTORY_RENDERERS = {
    'table': render_history_table,
    'markdown': render_history_markdown,
}

PLAN_EXPLAIN_RENDERERS = {
    'table': render_plan_explain_table,
    'markdown': render_plan_explain_markdown,
}