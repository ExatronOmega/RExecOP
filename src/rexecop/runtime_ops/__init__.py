"""Runtime operation mechanics with cycle-safe lazy public exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "OperationMonitor": ("rexecop.runtime_ops.monitor", "OperationMonitor"),
    "RunNowQueue": ("rexecop.runtime_ops.queue", "RunNowQueue"),
    "RollbackExecutor": ("rexecop.runtime_ops.rollback", "RollbackExecutor"),
    "RuntimeCoordinator": ("rexecop.runtime_ops.coordinator", "RuntimeCoordinator"),
    "StepMonitorStatus": ("rexecop.runtime_ops.monitor", "StepMonitorStatus"),
    "TargetLockManager": ("rexecop.runtime_ops.target_lock", "TargetLockManager"),
    "WatchdogService": ("rexecop.runtime_ops.watchdog", "WatchdogService"),
    "maintenance_window_allows": (
        "rexecop.runtime_ops.maintenance",
        "maintenance_window_allows",
    ),
    "parse_timeout_seconds": ("rexecop.runtime_ops.monitor", "parse_timeout_seconds"),
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
