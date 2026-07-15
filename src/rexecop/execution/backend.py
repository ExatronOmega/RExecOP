from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepExecutionContext:
    operation_id: str
    target: str
    mode: str
    step: dict[str, Any]
    shared_state: dict[str, Any]


@dataclass
class StepExecutionResult:
    step_id: str
    success: bool
    output: dict[str, Any]
    error: str = ""
    runtime_receipt_binding: dict[str, Any] = field(default_factory=dict)
    receipt_conformance: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "step_id": self.step_id,
            "success": self.success,
            "output": dict(self.output),
            "error": self.error,
        }
        if self.runtime_receipt_binding:
            payload["runtime_receipt_binding"] = dict(self.runtime_receipt_binding)
        if self.receipt_conformance:
            payload["receipt_conformance"] = dict(self.receipt_conformance)
        return payload
