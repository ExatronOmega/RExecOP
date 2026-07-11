from __future__ import annotations

import json
from collections.abc import Mapping
from importlib.resources import files
from typing import Any

from sclite import ImmutableSchemaResolver, verify_artifact
from sclite.automation import (
    automation_edge,
    automation_node,
    build_automation_chain,
    verify_automation_chain,
)
from sclite.reactions import (
    build_finding,
    build_observation_envelope,
    build_reaction_chain_manifest,
    build_reaction_plan,
    reaction_idempotency_key,
    validate_escalation_proposal,
    verify_reaction_chain_manifest,
)
from sclite.triggers import (
    build_trigger_decision,
    trigger_decision_descriptor,
    trigger_decision_digest,
)
from sclite.watchdog import build_watchdog_decision

OWNER_SCHEMA_REFS = {
    "observation_envelope": "rexecop.io/observation_envelope@v0.1",
    "finding": "rexecop.io/finding@v0.1",
    "reaction_plan": "rexecop.io/reaction_plan@v0.1",
    "escalation_proposal": "rexecop.io/escalation_proposal@v0.1",
    "trigger_decision": "rexecop.io/trigger_decision@v0.1",
    "watchdog_decision": "rexecop.io/watchdog_decision@v0.1",
    "automation_chain": "rexecop.io/automation_chain@v0.1",
}


def _contract_set() -> dict[str, Mapping[str, Any]]:
    root = files("rexecop.contracts").joinpath("schemas")
    return {
        schema_ref: json.loads(
            root.joinpath(f"{name}.v0.1.schema.json").read_text(encoding="utf-8")
        )
        for name, schema_ref in OWNER_SCHEMA_REFS.items()
    }


ORCHESTRATION_SCHEMA_RESOLVER = ImmutableSchemaResolver(_contract_set())


def verify_owner_artifact(value: Mapping[str, Any], family: str) -> None:
    """Verify an orchestration artifact through RExecOp's explicit contract set."""
    try:
        schema_ref = OWNER_SCHEMA_REFS[family]
    except KeyError as exc:
        raise ValueError(f"unknown RExecOp contract family: {family}") from exc
    verify_artifact(value, schema_ref=schema_ref, resolver=ORCHESTRATION_SCHEMA_RESOLVER)


__all__ = (
    "OWNER_SCHEMA_REFS",
    "ORCHESTRATION_SCHEMA_RESOLVER",
    "automation_edge",
    "automation_node",
    "build_automation_chain",
    "build_finding",
    "build_observation_envelope",
    "build_reaction_chain_manifest",
    "build_reaction_plan",
    "build_trigger_decision",
    "build_watchdog_decision",
    "reaction_idempotency_key",
    "trigger_decision_descriptor",
    "trigger_decision_digest",
    "validate_escalation_proposal",
    "verify_automation_chain",
    "verify_owner_artifact",
    "verify_reaction_chain_manifest",
)
