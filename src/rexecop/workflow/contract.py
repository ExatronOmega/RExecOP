from __future__ import annotations

from rexecop.environment.model import Environment
from rexecop.errors import RExecOpValidationError
from rexecop.workflow.model import Workflow

ALLOWED_WORKFLOW_STEP_TYPES = frozenset({"internal", "connector", "evidence"})


def validate_workflow_contract(workflow: Workflow, environment: Environment) -> None:
    """Ensure workflow steps stay within declared connectors and supported types."""
    if not workflow.steps:
        raise RExecOpValidationError(f"workflow has no steps: {workflow.id}")

    for step in workflow.steps:
        step_type = str(step.type or "").strip()
        if step_type not in ALLOWED_WORKFLOW_STEP_TYPES:
            raise RExecOpValidationError(
                f"unsupported workflow step type: {step_type} ({step.id})"
            )
        if step_type != "connector":
            continue
        connector_name = str(step.connector or "").strip()
        if not connector_name:
            raise RExecOpValidationError(
                f"connector step missing connector name: {step.id}"
            )
        config = environment.connectors.get(connector_name)
        if not isinstance(config, dict):
            raise RExecOpValidationError(
                f"connector not configured in environment: {connector_name}"
            )
        if not bool(config.get("enabled", True)):
            raise RExecOpValidationError(f"connector disabled: {connector_name}")
