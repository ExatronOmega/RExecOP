"""Operation lifecycle public API with cycle-safe lazy exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "Operation": ("rexecop.operation.model", "Operation"),
    "OperationController": ("rexecop.operation.controller", "OperationController"),
    "OperationPlan": ("rexecop.operation.plan", "OperationPlan"),
    "OperationState": ("rexecop.operation.state", "OperationState"),
    "validate_transition": ("rexecop.operation.state", "validate_transition"),
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
