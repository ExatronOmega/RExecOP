from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rexecop.operation.state import OperationState

if TYPE_CHECKING:
    from rexecop.operation.controller import OperationController

TERMINAL_PROJECTION_STATES = frozenset(
    {
        OperationState.COMPLETED.value,
        OperationState.FAILED.value,
        OperationState.ESCALATED.value,
    }
)


def mark_projection_pending(
    metadata: dict[str, Any],
    *,
    operation_revision: int,
    state: str,
) -> None:
    """Embed the outbox marker in the operation CAS write, not a second truth store."""
    metadata["sclite_projection"] = {
        "status": "pending",
        "operation_revision": operation_revision,
        "state": state,
    }


def reconcile_pending_projections(
    controller: OperationController,
) -> dict[str, list[str]]:
    projected: list[str] = []
    deferred: list[str] = []
    for operation in controller.store.list_pending_projection_operations():
        if operation.state not in TERMINAL_PROJECTION_STATES:
            deferred.append(operation.id)
            continue
        controller.export_receipt(operation.id)
        projected.append(operation.id)
    return {"projected": projected, "deferred": deferred}
