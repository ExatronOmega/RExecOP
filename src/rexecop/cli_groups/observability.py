from __future__ import annotations

import json

import typer

from rexecop.cli_context import controller, emit_cli_error
from rexecop.cli_errors import validation_cli_error
from rexecop.errors import RExecOpError
from rexecop.observability.diagnostics import collect_runtime_diagnostics
from rexecop.observability.structured_log import list_structured_logs

app = typer.Typer(
    help="Bounded structured logs and runtime diagnostics.",
    no_args_is_help=True,
)
logs_app = typer.Typer(
    help="List structured observability logs.",
    no_args_is_help=True,
)
app.add_typer(logs_app, name="logs")


@logs_app.command("list")
def observability_logs_list_cmd(
    operation_id: str = typer.Option("", "--operation", help="Filter by operation id."),
    correlation_id: str = typer.Option("", "--correlation-id", help="Filter by correlation id."),
    limit: int = typer.Option(50, "--limit", min=1, max=200, help="Maximum events."),
) -> None:
    """List bounded structured logs with correlation and artifact refs."""
    try:
        result = list_structured_logs(
            controller().store,
            operation_id=operation_id,
            correlation_id=correlation_id,
            limit=limit,
        )
    except RExecOpError as exc:
        emit_cli_error(
            validation_cli_error(
                command=("observability", "logs", "list"),
                reason_code="structured_logs_unavailable",
                message=str(exc),
                safe_next_actions=("Run rexecop init in the runtime root first.",),
            )
        )
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@app.command("diagnostics")
def observability_diagnostics_cmd() -> None:
    """Show runtime diagnostics using explain-error failure classes."""
    try:
        result = collect_runtime_diagnostics(controller().store)
    except RExecOpError as exc:
        emit_cli_error(
            validation_cli_error(
                command=("observability", "diagnostics"),
                reason_code="runtime_diagnostics_unavailable",
                message=str(exc),
                safe_next_actions=("Run rexecop init in the runtime root first.",),
            )
        )
    typer.echo(json.dumps(result, indent=2, sort_keys=True))
