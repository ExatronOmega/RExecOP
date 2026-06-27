from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rexecop.catalog.service import compile_profile_operations
from rexecop.errors import RExecOpValidationError
from rexecop.profile.loader import LoadedProfile, load_profile
from rexecop.profile.resolver import resolve_profile_path
from rexecop.reaction.compiler import compile_reaction_pack
from rexecop.workflow.loader import load_workflow

OBSERVATION_SCHEMA_REF = "schemas/observation_envelope.v0.1.schema.json"
READ_ONLY_MODES = frozenset({"read_only", "observe", "dry_run", "emergency_readonly"})
REACTION_OBSERVATION_KEYS = frozenset(
    {
        "shared_state_key",
        "schema_ref",
        "source_intent",
        "producer_step",
        "requires_completed_operation",
    }
)


@dataclass(frozen=True)
class ProfileConformanceResult:
    profile: str
    version: str
    status: str
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    checked_intents: tuple[str, ...] = ()
    reaction_observation_intents: tuple[str, ...] = ()
    checked_surfaces: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "version": self.version,
            "status": self.status,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "checked_intents": list(self.checked_intents),
            "reaction_observation_intents": list(self.reaction_observation_intents),
            "checked_surfaces": list(self.checked_surfaces),
        }


def validate_profile_conformance(
    profile_path: str | Path,
    *,
    require_reaction_observation: bool = False,
    require_readonly: bool = False,
) -> ProfileConformanceResult:
    profile = load_profile(resolve_profile_path(profile_path))
    errors: list[str] = []
    warnings: list[str] = []
    observation_intents: list[str] = []
    checked_intents: list[str] = []
    checked_surfaces = [
        "profile_contract",
        "operation_catalog_projection",
        "workflow_connector_contracts",
    ]

    try:
        operations = compile_profile_operations(profile)
    except RExecOpValidationError as exc:
        operations = []
        errors.append(f"operation_catalog_projection:{exc}")

    for operation in operations:
        checked_intents.append(operation.id)
        metadata = _intent_metadata(profile, operation.id, errors)
        if not metadata:
            continue
        modes = {str(item) for item in metadata.get("modes") or []}
        if require_readonly and (not modes or not modes <= READ_ONLY_MODES):
            errors.append(f"{operation.id}:non_readonly_modes:{sorted(modes)}")
        if require_readonly and operation.side_effect_class != "none":
            errors.append(f"{operation.id}:side_effect_class:{operation.side_effect_class}")
        workflow = _workflow(profile, operation.id, errors)
        if workflow is not None:
            for connector in workflow.required_connectors():
                try:
                    contract = profile.connector_contract(connector)
                except RExecOpValidationError as exc:
                    errors.append(f"{operation.id}:connector_contract:{connector}:{exc}")
                    continue
                if contract is None:
                    errors.append(f"{operation.id}:missing_connector_contract:{connector}")
        declaration = metadata.get("reaction_observation")
        if declaration is not None:
            _validate_reaction_observation_declaration(
                profile=profile,
                intent_id=operation.id,
                declaration=declaration,
                errors=errors,
            )
            observation_intents.append(operation.id)

    reaction_path = profile.root / "reactions" / "reaction_pack.yaml"
    if reaction_path.is_file():
        checked_surfaces.append("reaction_pack")
        try:
            compile_reaction_pack(profile, reaction_path)
        except RExecOpValidationError as exc:
            errors.append(f"reaction_pack:{exc}")
    else:
        warnings.append("reaction_pack:not_present")

    if require_reaction_observation and not observation_intents:
        errors.append("reaction_observation:not_declared")

    return ProfileConformanceResult(
        profile=profile.name,
        version=profile.version,
        status="passed" if not errors else "failed",
        errors=tuple(sorted(set(errors))),
        warnings=tuple(sorted(set(warnings))),
        checked_intents=tuple(sorted(set(checked_intents))),
        reaction_observation_intents=tuple(sorted(set(observation_intents))),
        checked_surfaces=tuple(checked_surfaces),
    )


def _intent_metadata(
    profile: LoadedProfile,
    intent_id: str,
    errors: list[str],
) -> dict[str, Any]:
    try:
        return profile.intent_metadata(intent_id)
    except RExecOpValidationError as exc:
        errors.append(f"{intent_id}:intent_metadata:{exc}")
        return {}


def _workflow(
    profile: LoadedProfile,
    intent_id: str,
    errors: list[str],
) -> Any | None:
    try:
        return load_workflow(profile.resolve_workflow_path(intent_id))
    except RExecOpValidationError as exc:
        errors.append(f"{intent_id}:workflow:{exc}")
        return None


def _validate_reaction_observation_declaration(
    *,
    profile: LoadedProfile,
    intent_id: str,
    declaration: Any,
    errors: list[str],
) -> None:
    if not isinstance(declaration, dict):
        errors.append(f"{intent_id}:reaction_observation:not_mapping")
        return
    unknown = sorted(str(key) for key in declaration if key not in REACTION_OBSERVATION_KEYS)
    if unknown:
        errors.append(f"{intent_id}:reaction_observation:unknown_keys:{','.join(unknown)}")
    if declaration.get("shared_state_key") != "reaction_observation":
        errors.append(f"{intent_id}:reaction_observation:shared_state_key")
    if declaration.get("schema_ref") != OBSERVATION_SCHEMA_REF:
        errors.append(f"{intent_id}:reaction_observation:schema_ref")
    if declaration.get("source_intent") != intent_id:
        errors.append(f"{intent_id}:reaction_observation:source_intent")
    if declaration.get("requires_completed_operation") is not True:
        errors.append(f"{intent_id}:reaction_observation:requires_completed_operation")
    producer_step = str(declaration.get("producer_step") or "").strip()
    if not producer_step:
        errors.append(f"{intent_id}:reaction_observation:producer_step")
        return
    workflow = _workflow(profile, intent_id, errors)
    if workflow is None:
        return
    steps = {step.id: step for step in workflow.steps}
    step = steps.get(producer_step)
    if step is None:
        errors.append(f"{intent_id}:reaction_observation:producer_step_not_found")
    elif step.type != "internal":
        errors.append(f"{intent_id}:reaction_observation:producer_step_not_internal")
