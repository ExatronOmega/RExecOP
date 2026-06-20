from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from rexecop.errors import RExecOpValidationError

EXECUTION_REQUEST_SCHEMA_VERSION = "v0.1"
EXECUTION_RECEIPT_SCHEMA_VERSION = "v0.1"


@dataclass(frozen=True)
class ResourceLimits:
    timeout_seconds: float = 0.0
    max_steps: int = 0
    max_output_bytes: int = 65536

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> ResourceLimits:
        raw = dict(value or {})
        timeout = float(raw.get("timeout_seconds") or 0.0)
        max_steps = int(raw.get("max_steps") or 0)
        max_output_bytes = int(raw.get("max_output_bytes") or 65536)
        if timeout < 0 or max_steps < 0 or max_output_bytes < 1:
            raise RExecOpValidationError("invalid execution resource limits")
        return cls(
            timeout_seconds=timeout,
            max_steps=max_steps,
            max_output_bytes=max_output_bytes,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionStep:
    step_id: str
    step_type: str
    action: str
    connector: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ExecutionStep:
        step_id = str(value.get("id") or value.get("step_id") or "").strip()
        if not step_id:
            raise RExecOpValidationError("execution step missing id")
        return cls(
            step_id=step_id,
            step_type=str(value.get("type") or "internal").strip() or "internal",
            action=str(value.get("action") or "").strip(),
            connector=str(value.get("connector") or "").strip(),
            metadata=_public_metadata(value),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_type": self.step_type,
            "action": self.action,
            "connector": self.connector,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ExecutionRequest:
    request_id: str
    operation_id: str
    target_ref: str
    mode: str
    source: str = "approved_workflow_plan"
    schema_version: str = EXECUTION_REQUEST_SCHEMA_VERSION
    steps: tuple[ExecutionStep, ...] = field(default_factory=tuple)
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id:
            raise RExecOpValidationError("execution request missing id")
        if not self.operation_id:
            raise RExecOpValidationError("execution request missing operation id")
        if not self.target_ref:
            raise RExecOpValidationError("execution request missing target")
        if self.schema_version != EXECUTION_REQUEST_SCHEMA_VERSION:
            raise RExecOpValidationError("unsupported execution request schema")

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "operation_id": self.operation_id,
            "target_ref": self.target_ref,
            "mode": self.mode,
            "source": self.source,
            "schema_version": self.schema_version,
            "steps": [step.as_dict() for step in self.steps],
            "resource_limits": self.resource_limits.as_dict(),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ExecutionStepReceipt:
    step_id: str
    success: bool
    error_class: str = ""
    output_digest_refs: Mapping[str, str] = field(default_factory=dict)
    output_truncated: Mapping[str, bool] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "success": self.success,
            "error_class": self.error_class,
            "output_digest_refs": dict(self.output_digest_refs),
            "output_truncated": dict(self.output_truncated),
        }


@dataclass(frozen=True)
class ExecutionReceipt:
    receipt_id: str
    request_id: str
    operation_id: str
    success: bool
    schema_version: str = EXECUTION_RECEIPT_SCHEMA_VERSION
    executed_steps: tuple[str, ...] = field(default_factory=tuple)
    step_receipts: tuple[ExecutionStepReceipt, ...] = field(default_factory=tuple)
    error: str = ""
    error_class: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "request_id": self.request_id,
            "operation_id": self.operation_id,
            "schema_version": self.schema_version,
            "success": self.success,
            "executed_steps": list(self.executed_steps),
            "step_receipts": [step.as_dict() for step in self.step_receipts],
            "error": self.error,
            "error_class": self.error_class,
        }


def execution_request_from_workflow(
    *,
    operation_id: str,
    target: str,
    mode: str,
    planned_steps: list[dict[str, Any]],
    max_steps: int | None = None,
    max_output_bytes: int = 65536,
) -> ExecutionRequest:
    return ExecutionRequest(
        request_id=f"exec-request:{operation_id}",
        operation_id=operation_id,
        target_ref=target,
        mode=mode,
        steps=tuple(ExecutionStep.from_mapping(step) for step in planned_steps),
        resource_limits=ResourceLimits(
            max_steps=max_steps or len(planned_steps),
            max_output_bytes=max_output_bytes,
        ),
    )


def execution_receipt_from_results(
    *,
    request: ExecutionRequest,
    success: bool,
    executed_steps: list[str],
    step_results: Mapping[str, Mapping[str, Any]],
    error: str = "",
    error_class: str = "",
) -> ExecutionReceipt:
    return ExecutionReceipt(
        receipt_id=f"exec-receipt:{request.operation_id}",
        request_id=request.request_id,
        operation_id=request.operation_id,
        success=success,
        executed_steps=tuple(executed_steps),
        step_receipts=tuple(
            _step_receipt(step_id, result)
            for step_id, result in step_results.items()
        ),
        error=error,
        error_class=error_class,
    )


def _step_receipt(step_id: str, result: Mapping[str, Any]) -> ExecutionStepReceipt:
    output = result.get("output")
    output_data = output if isinstance(output, Mapping) else {}
    data = output_data.get("data")
    response_data = data if isinstance(data, Mapping) else output_data
    digests = response_data.get("output_digests")
    truncated = response_data.get("output_truncated")
    return ExecutionStepReceipt(
        step_id=step_id,
        success=bool(result.get("success")),
        error_class=str(output_data.get("error_class") or response_data.get("error_class") or ""),
        output_digest_refs=dict(digests) if isinstance(digests, Mapping) else {},
        output_truncated=dict(truncated) if isinstance(truncated, Mapping) else {},
    )


def _public_metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "declared_type": str(value.get("type") or ""),
        "declared_connector": str(value.get("connector") or ""),
    }
