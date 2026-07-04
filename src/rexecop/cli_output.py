from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import typer

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