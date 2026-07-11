from __future__ import annotations

import json
from collections.abc import Mapping
from importlib.resources import files
from typing import Any

from sclite import ImmutableSchemaResolver, SchemaInventoryEntry, verify_artifact

OWNER_SCHEMA_REFS = {
    "observation_envelope": "rexecop.io/observation_envelope@v0.1",
    "finding": "rexecop.io/finding@v0.1",
    "reaction_plan": "rexecop.io/reaction_plan@v0.1",
    "escalation_proposal": "rexecop.io/escalation_proposal@v0.1",
    "trigger_decision": "rexecop.io/trigger_decision@v0.1",
    "watchdog_decision": "rexecop.io/watchdog_decision@v0.1",
    "automation_chain": "rexecop.io/automation_chain@v0.1",
}
LEGACY_REF_TO_FAMILY = {
    f"schemas/{family}.v0.1.schema.json": family for family in OWNER_SCHEMA_REFS
} | {f"{family}.v0.1": family for family in OWNER_SCHEMA_REFS}


def _contract_set() -> dict[str, Mapping[str, Any]]:
    root = files("rexecop.contracts").joinpath("schemas")
    return {
        schema_ref: json.loads(
            root.joinpath(f"{name}.v0.1.schema.json").read_text(encoding="utf-8")
        )
        for name, schema_ref in OWNER_SCHEMA_REFS.items()
    }


_NAMESPACED_SCHEMA_RESOLVER = ImmutableSchemaResolver(_contract_set())


class OwnerSchemaResolver:
    """Resolve owner namespaced ids and read-only v0.1 artifact aliases."""

    def resolve(self, schema_ref: str) -> Mapping[str, Any]:
        family = LEGACY_REF_TO_FAMILY.get(schema_ref)
        resolved_ref = OWNER_SCHEMA_REFS[family] if family else schema_ref
        return _NAMESPACED_SCHEMA_RESOLVER.resolve(resolved_ref)

    def inventory(self) -> tuple[SchemaInventoryEntry, ...]:
        return _NAMESPACED_SCHEMA_RESOLVER.inventory()


ORCHESTRATION_SCHEMA_RESOLVER = OwnerSchemaResolver()


def validate_artifact(
    value: Mapping[str, Any], schema_ref: str, *, strict_jsonschema: bool = False, **_: Any
) -> None:
    family = LEGACY_REF_TO_FAMILY.get(schema_ref)
    if family is None:
        raise ValueError(f"unknown RExecOp contract schema: {schema_ref}")
    verify_artifact(
        value,
        schema_ref=OWNER_SCHEMA_REFS[family],
        resolver=ORCHESTRATION_SCHEMA_RESOLVER,
        strict_jsonschema=strict_jsonschema,
    )


def verify_owner_artifact(value: Mapping[str, Any], family: str) -> None:
    try:
        schema_ref = OWNER_SCHEMA_REFS[family]
    except KeyError as exc:
        raise ValueError(f"unknown RExecOp contract family: {family}") from exc
    verify_artifact(value, schema_ref=schema_ref, resolver=ORCHESTRATION_SCHEMA_RESOLVER)
