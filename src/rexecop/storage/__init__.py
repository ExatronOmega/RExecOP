"""Storage public API with cycle-safe lazy exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "FileStore": ("rexecop.storage.file_store", "FileStore"),
    "OperationStoragePort": ("rexecop.storage.port", "OperationStoragePort"),
    "RuntimeStore": ("rexecop.storage.port", "RuntimeStore"),
    "SqliteStore": ("rexecop.storage.sqlite_store", "SqliteStore"),
    "create_store": ("rexecop.storage.factory", "create_store"),
    "resolve_storage_backend": ("rexecop.storage.factory", "resolve_storage_backend"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
