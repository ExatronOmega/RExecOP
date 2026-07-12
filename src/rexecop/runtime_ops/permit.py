from __future__ import annotations

import hmac
from datetime import UTC, datetime, timedelta
from typing import Any

from rexecop.catalog.digest import canonical_digest
from rexecop.errors import RExecOpValidationError
from rexecop.operation.model import Operation
from rexecop.operation.plan import OperationPlan
from rexecop.storage.port import RuntimeStore

EXECUTION_PERMIT_SCHEMA = "rexecop.execution_permit.v0.1"
DEFAULT_PERMIT_TTL_SECONDS = 60.0


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class ExecutionPermitManager:
    """Bind existing admission/runtime facts; never evaluate or grant policy."""

    def __init__(self, store: RuntimeStore) -> None:
        self.store = store

    def issue(
        self,
        *,
        operation: Operation,
        plan: OperationPlan,
        step_id: str,
        execution_spec: dict[str, Any],
        target_binding: dict[str, Any],
        lease: dict[str, Any],
        governance_admission_digest: str,
        now: datetime | None = None,
        ttl_seconds: float = DEFAULT_PERMIT_TTL_SECONDS,
    ) -> dict[str, Any]:
        issued_at = now or _now()
        permit = {
            "schema": EXECUTION_PERMIT_SCHEMA,
            "operation_id": operation.id,
            "operation_revision": operation.operation_revision,
            "step_id": step_id,
            "plan_digest": "sha256:" + canonical_digest(plan.as_dict()),
            "execution_spec_digest": str(execution_spec.get("digest") or ""),
            "govengine_decision_type": operation.govengine_decision_type,
            "governance_admission_digest": governance_admission_digest,
            "target_binding": target_binding,
            "target_binding_digest": "sha256:" + canonical_digest(target_binding),
            "mode": operation.mode,
            "lease_epoch": int(lease.get("lease_epoch") or 0),
            "process_instance_id": str(lease.get("process_instance_id") or ""),
            "issued_at": issued_at.isoformat(),
            "expires_at": (issued_at + timedelta(seconds=ttl_seconds)).isoformat(),
            "authority": {
                "governance": "govengine",
                "runtime_binding": "rexecop",
                "truth": "sclite",
            },
            "non_claims": [
                "This record does not evaluate policy or grant governance authority.",
                "This record is a freshness binding, not a SCLite truth artifact.",
            ],
        }
        permit["permit_digest"] = self._digest(permit)
        self.store.save_execution_permit(permit)
        return permit

    def require_fresh(
        self,
        permit: dict[str, Any],
        *,
        operation: Operation,
        plan: OperationPlan,
        execution_spec: dict[str, Any],
        target_binding: dict[str, Any],
        lease: dict[str, Any],
        governance_admission_digest: str,
        now: datetime | None = None,
    ) -> None:
        if permit.get("schema") != EXECUTION_PERMIT_SCHEMA:
            raise RExecOpValidationError("execution_permit_invalid: unsupported schema")
        expected_digest = self._digest(permit)
        if not hmac.compare_digest(str(permit.get("permit_digest") or ""), expected_digest):
            raise RExecOpValidationError("execution_permit_invalid: digest mismatch")
        expires_at = datetime.fromisoformat(str(permit["expires_at"]))
        if (now or _now()) >= expires_at:
            raise RExecOpValidationError("execution_permit_stale: permit expired")
        expected = {
            "operation_id": operation.id,
            "operation_revision": operation.operation_revision,
            "plan_digest": "sha256:" + canonical_digest(plan.as_dict()),
            "execution_spec_digest": str(execution_spec.get("digest") or ""),
            "govengine_decision_type": operation.govengine_decision_type,
            "governance_admission_digest": governance_admission_digest,
            "target_binding_digest": "sha256:" + canonical_digest(target_binding),
            "mode": operation.mode,
            "lease_epoch": int(lease.get("lease_epoch") or 0),
            "process_instance_id": str(lease.get("process_instance_id") or ""),
        }
        drift = [key for key, value in expected.items() if permit.get(key) != value]
        if drift:
            raise RExecOpValidationError(
                "execution_permit_stale: binding drift: " + ",".join(sorted(drift))
            )
        self.store.validate_execution_lease(lease)

    @staticmethod
    def _digest(permit: dict[str, Any]) -> str:
        payload = {key: value for key, value in permit.items() if key != "permit_digest"}
        return "sha256:" + canonical_digest(payload)
