from __future__ import annotations

from pathlib import Path

import typer

from rexecop.cli_output import SECRETS_DOCTOR_RENDERERS, emit_failure, emit_payload
from rexecop.errors import RExecOpError
from rexecop.runtime.doctor import CHECK_BLOCKER
from rexecop.secrets.doctor import run_secrets_doctor
from rexecop.secrets.suggest import suggest_secret_refs

app = typer.Typer(
    help="Inspect secret references without resolving or printing values.",
    no_args_is_help=True,
)


@app.command("doctor")
def secrets_doctor_cmd(
    env: Path | None = typer.Option(None, "--env", help="Environment YAML to inspect."),
    catalog: Path | None = typer.Option(None, "--catalog", help="Optional catalog YAML."),
    secrets_file: Path | None = typer.Option(
        None,
        "--secrets-file",
        help="Optional secrets YAML path; defaults to REXECOP_SECRETS_FILE.",
    ),
) -> None:
    """Check secret refs, duplicates, secrets-file policy and redaction self-test."""
    if env is None and catalog is None:
        emit_failure(
            command=("secrets", "doctor"),
            message="provide --env and/or --catalog",
            reason_code="missing_input",
        )
    try:
        result = run_secrets_doctor(
            env_path=env,
            catalog_path=catalog,
            secrets_file=secrets_file,
        )
    except RExecOpError as exc:
        emit_failure(command=("secrets", "doctor"), message=str(exc))
    emit_payload(result, renderers=SECRETS_DOCTOR_RENDERERS)
    if result["status"] == CHECK_BLOCKER:
        raise typer.Exit(code=1)


@app.command("suggest-ref")
def secrets_suggest_ref_cmd(
    env: Path = typer.Option(..., "--env", help="Environment YAML to inspect."),
    connector: str | None = typer.Option(None, "--connector", help="Optional connector name."),
) -> None:
    """Suggest secret reference names without reading secret stores."""
    try:
        result = suggest_secret_refs(env_path=env, connector=connector)
    except RExecOpError as exc:
        emit_failure(command=("secrets", "suggest-ref"), message=str(exc))
    emit_payload(result)
