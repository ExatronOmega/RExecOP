from __future__ import annotations

import os

from rexecop.adapters.govengine_port.contracts import is_mutating_mode
from rexecop.errors import RExecOpMutationNotCertified

MUTATION_POSTURE_ENV = "REXECOP_MUTATION_POSTURE"
STABLE_READ_ONLY_POSTURE = "stable_read_only"
LAB_ONLY_POSTURE = "lab_only"
SUPPORTED_MUTATION_POSTURES = frozenset(
    {STABLE_READ_ONLY_POSTURE, LAB_ONLY_POSTURE}
)


def resolve_mutation_posture(value: str | None = None) -> str:
    posture = (
        value if value is not None else os.environ.get(MUTATION_POSTURE_ENV, "")
    ).strip().lower()
    if not posture:
        return STABLE_READ_ONLY_POSTURE
    if posture not in SUPPORTED_MUTATION_POSTURES:
        raise RExecOpMutationNotCertified(
            f"unsupported {MUTATION_POSTURE_ENV} value: {posture}"
        )
    return posture


def mutation_execution_enabled(value: str | None = None) -> bool:
    try:
        return resolve_mutation_posture(value) == LAB_ONLY_POSTURE
    except RExecOpMutationNotCertified:
        return False


def require_mutation_execution_enabled(
    mode: str,
    *,
    value: str | None = None,
) -> None:
    if not is_mutating_mode(mode):
        return
    posture = resolve_mutation_posture(value)
    if posture != LAB_ONLY_POSTURE:
        raise RExecOpMutationNotCertified(
            "mutation_not_certified: stable runtime posture is read-only"
        )
