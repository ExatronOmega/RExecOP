from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TargetDescriptor:
    id: str
    target_kind: str
    profile_ref: str
    environment_id: str
    environment_target: str
    capabilities: tuple[str, ...]
    connector_refs: tuple[str, ...]
    classification: dict[str, str | int | float | bool] = field(default_factory=dict)
    environment_path: Path = field(repr=False, compare=False, default=Path("."))
    profile_path: Path = field(repr=False, compare=False, default=Path("."))

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target_kind": self.target_kind,
            "profile_ref": self.profile_ref,
            "environment_id": self.environment_id,
            "environment_target": self.environment_target,
            "capabilities": list(self.capabilities),
            "connector_refs": list(self.connector_refs),
            "classification": dict(sorted(self.classification.items())),
        }


@dataclass(frozen=True)
class OperationDescriptor:
    id: str
    title: str
    summary: str
    profile_ref: str
    profile_version: str
    target_kinds: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    required_connectors: tuple[str, ...]
    modes: tuple[str, ...]
    risk: str
    side_effect_class: str
    validation_ref: str
    runbook_ref: str
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "profile_ref": self.profile_ref,
            "profile_version": self.profile_version,
            "target_kinds": list(self.target_kinds),
            "required_capabilities": list(self.required_capabilities),
            "required_connectors": list(self.required_connectors),
            "modes": list(self.modes),
            "risk": self.risk,
            "side_effect_class": self.side_effect_class,
            "validation_ref": self.validation_ref,
            "runbook_ref": self.runbook_ref,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class ApplicabilityResult:
    target_id: str
    operation_id: str
    applicable: bool
    status: str
    reason_codes: tuple[str, ...]
    missing_capabilities: tuple[str, ...] = ()
    missing_connectors: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "operation_id": self.operation_id,
            "applicable": self.applicable,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "missing_capabilities": list(self.missing_capabilities),
            "missing_connectors": list(self.missing_connectors),
        }


@dataclass(frozen=True)
class CatalogBinding:
    catalog_version: str
    catalog_digest: str
    target_descriptor_digest: str
    operation_descriptor_digest: str
    profile_digest: str
    environment_digest: str
    target_id: str
    environment_id: str
    environment_target: str
    profile_ref: str

    def as_dict(self) -> dict[str, str]:
        return {
            "catalog_version": self.catalog_version,
            "catalog_digest": self.catalog_digest,
            "target_descriptor_digest": self.target_descriptor_digest,
            "operation_descriptor_digest": self.operation_descriptor_digest,
            "profile_digest": self.profile_digest,
            "environment_digest": self.environment_digest,
            "target_id": self.target_id,
            "environment_id": self.environment_id,
            "environment_target": self.environment_target,
            "profile_ref": self.profile_ref,
        }
