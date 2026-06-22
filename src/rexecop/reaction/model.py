from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReactionCondition:
    path: str
    operator: str
    value: Any = None

    def as_dict(self) -> dict[str, Any]:
        result = {"path": self.path, "operator": self.operator}
        if self.operator != "exists":
            result["value"] = self.value
        return result


@dataclass(frozen=True)
class ReactionRule:
    rule_id: str
    priority: int
    conditions: tuple[ReactionCondition, ...]
    finding_kind: str
    finding_severity: str
    finding_summary: str
    outcome: str
    intent_ref: str | None
    digest: str


@dataclass(frozen=True)
class ReactionPack:
    pack_id: str
    version: str
    max_depth: int
    max_reactions: int
    rules: tuple[ReactionRule, ...]
    fallback: ReactionRule
    digest: str
    profile_digest: str


@dataclass(frozen=True)
class ReactionContext:
    depth: int = 0
    reaction_count: int = 0
    visited_rule_digests: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReactionEvaluation:
    rule: ReactionRule
    outcome: str
    intent_ref: str | None
    reason: str
    matched: bool
    blocked: bool = False
