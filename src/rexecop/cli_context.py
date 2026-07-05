from __future__ import annotations

import os
from pathlib import Path

import typer

from rexecop.cli_errors import cli_error_json
from rexecop.operation.controller import OperationController
from rexecop.reaction.service import ReactionService
from rexecop.runtime.root import resolve_runtime_instance, resolve_runtime_root
from rexecop.storage.factory import create_store, resolve_storage_backend

_runtime_root: Path | None = None
_runtime_instance: str | None = None


def configure_runtime(
    *,
    root: Path | None,
    instance: str | None,
    storage: str,
) -> None:
    global _runtime_instance, _runtime_root
    _runtime_instance = resolve_runtime_instance(instance)
    _runtime_root = resolve_runtime_root(root, instance=_runtime_instance)
    os.environ["REXECOP_STORAGE"] = resolve_storage_backend(storage)


def runtime_root() -> Path:
    return _runtime_root or resolve_runtime_root()


def runtime_instance() -> str | None:
    return _runtime_instance


def controller() -> OperationController:
    return OperationController(store=create_store(_runtime_root))


def reaction_service() -> ReactionService:
    return ReactionService(controller())


def emit_cli_error(payload: dict[str, object]) -> None:
    typer.echo(cli_error_json(payload))
    raise typer.Exit(code=1)
