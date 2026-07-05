from __future__ import annotations

import json

import typer

from rexecop.cli_context import controller, emit_cli_error
from rexecop.cli_errors import cli_error_payload, validation_cli_error
from rexecop.errors import RExecOpError
from rexecop.runtime_ops.recovery import run_startup_recovery
from rexecop.runtime_ops.triage import (
    collect_ops_snapshot,
    collect_runtime_status,
    explain_error,
    list_dead_letter_manifest,
    list_locks_manifest,
    show_dead_letter_item,
)

runtime_app = typer.Typer(help="Runtime triage and status.", no_args_is_help=True)
dead_letter_app = typer.Typer(help="Inspect dead-letter items.", no_args_is_help=True)
locks_app = typer.Typer(help="Inspect advisory target locks.", no_args_is_help=True)


@runtime_app.command("recover")
def runtime_recover_cmd(
    as_json: bool = typer.Option(True, "--json", help="Emit JSON recovery report."),
) -> None:
    """Reconcile stale leases, interrupted operations and receipt gaps after restart."""
    if not as_json:
        typer.secho("error: only --json output is supported", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    try:
        runtime_controller = controller()
        result = run_startup_recovery(
            runtime_controller.store,
            controller=runtime_controller,
        )
    except RExecOpError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@runtime_app.command("status")
def runtime_status_cmd(
    as_json: bool = typer.Option(True, "--json/--no-json", help="Emit JSON status."),
) -> None:
    """Show runtime queue, active operations, locks and dead-letter summary."""
    if not as_json:
        emit_cli_error(
            validation_cli_error(
                command=("runtime", "status"),
                reason_code="unsupported_output_format",
                message="only --json output is supported",
                safe_next_actions=("Re-run with --json.",),
            )
        )
    try:
        result = collect_runtime_status(controller().store)
    except RExecOpError as exc:
        emit_cli_error(
            validation_cli_error(
                command=("runtime", "status"),
                reason_code="runtime_status_unavailable",
                message=str(exc),
                safe_next_actions=("Run rexecop init in the runtime root first.",),
            )
        )
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@dead_letter_app.command("list")
def dead_letter_list_cmd() -> None:
    """List dead-letter inbox payloads moved by watchdog."""
    try:
        result = list_dead_letter_manifest(controller().store)
    except RExecOpError as exc:
        emit_cli_error(
            validation_cli_error(
                command=("dead-letter", "list"),
                reason_code="dead_letter_list_unavailable",
                message=str(exc),
                safe_next_actions=("Run rexecop init in the runtime root first.",),
            )
        )
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@dead_letter_app.command("show")
def dead_letter_show_cmd(
    name: str = typer.Argument(..., help="Dead-letter file name."),
) -> None:
    """Show one redacted dead-letter payload."""
    try:
        result = show_dead_letter_item(controller().store, name)
    except RExecOpError as exc:
        emit_cli_error(
            validation_cli_error(
                command=("dead-letter", "show"),
                reason_code="dead_letter_lookup_failed",
                message=str(exc),
                safe_next_actions=(
                    "Run rexecop dead-letter list.",
                    "Use the exact dead-letter file name from the manifest.",
                ),
            )
        )
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@locks_app.command("list")
def locks_list_cmd() -> None:
    """List advisory target locks and stale holders."""
    try:
        result = list_locks_manifest(controller().store)
    except RExecOpError as exc:
        emit_cli_error(
            validation_cli_error(
                command=("locks", "list"),
                reason_code="locks_list_unavailable",
                message=str(exc),
                safe_next_actions=("Run rexecop init in the runtime root first.",),
            )
        )
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


def register_root_commands(root_app: typer.Typer) -> None:
    @root_app.command("ops")
    def ops_cmd() -> None:
        """Aggregate queue, active operations, blockers and action-required items."""
        try:
            result = collect_ops_snapshot(controller().store)
        except RExecOpError as exc:
            emit_cli_error(
                validation_cli_error(
                    command=("ops",),
                    reason_code="ops_unavailable",
                    message=str(exc),
                    safe_next_actions=("Run rexecop runtime status --json.",),
                )
            )
        if result.get("blockers"):
            emit_cli_error(
                cli_error_payload(
                    error_class="runtime_failure",
                    reason_code="runtime_blockers_present",
                    message="runtime blockers require operator action",
                    command=("ops",),
                    safe_next_actions=("Inspect details.blockers and action_required.",),
                    details=result,
                )
            )
        typer.echo(json.dumps(result, indent=2, sort_keys=True))

    @root_app.command("explain-error")
    def explain_error_cmd(
        ref: str = typer.Argument(
            ...,
            help="Operation id, dead-letter name or watchdog record id.",
        ),
    ) -> None:
        """Map a runtime failure reference to a bounded failure class and next actions."""
        try:
            result = explain_error(controller().store, ref)
        except RExecOpError as exc:
            emit_cli_error(
                validation_cli_error(
                    command=("explain-error",),
                    reason_code="explain_error_unavailable",
                    message=str(exc),
                    safe_next_actions=(
                        "Use an operation id, dead-letter file name, or watchdog record id.",
                        "Run rexecop ops --json for action-required items.",
                    ),
                )
            )
        typer.echo(json.dumps(result, indent=2, sort_keys=True))
