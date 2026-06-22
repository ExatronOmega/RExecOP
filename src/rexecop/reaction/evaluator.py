from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rexecop.reaction.model import (
    ReactionCondition,
    ReactionContext,
    ReactionEvaluation,
    ReactionPack,
)

_MISSING = object()


def _resolve(value: Mapping[str, Any], path: str) -> Any:
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _matches(condition: ReactionCondition, observation: Mapping[str, Any]) -> bool:
    actual = _resolve(observation, condition.path)
    if condition.operator == "exists":
        return actual is not _MISSING
    if actual is _MISSING:
        return False
    if condition.operator == "equals":
        return actual == condition.value
    if condition.operator == "not_equals":
        return actual != condition.value
    if condition.operator == "in":
        return actual in condition.value
    if not isinstance(actual, (int, float)) or isinstance(actual, bool):
        return False
    if condition.operator == "gt":
        return actual > condition.value
    if condition.operator == "gte":
        return actual >= condition.value
    if condition.operator == "lt":
        return actual < condition.value
    if condition.operator == "lte":
        return actual <= condition.value
    return False


def evaluate_reaction(
    pack: ReactionPack, observation: Mapping[str, Any], context: ReactionContext
) -> ReactionEvaluation:
    if context.depth >= pack.max_depth:
        return ReactionEvaluation(
            pack.fallback, "escalate", None, "max_reaction_depth_exceeded", False, True
        )
    if context.reaction_count >= pack.max_reactions:
        return ReactionEvaluation(
            pack.fallback, "escalate", None, "reaction_budget_exhausted", False, True
        )
    for rule in pack.rules:
        if all(_matches(condition, observation) for condition in rule.conditions):
            if rule.digest in context.visited_rule_digests:
                return ReactionEvaluation(
                    pack.fallback, "escalate", None, "reaction_cycle_detected", False, True
                )
            return ReactionEvaluation(
                rule, rule.outcome, rule.intent_ref, f"matched:{rule.rule_id}", True
            )
    return ReactionEvaluation(
        pack.fallback,
        pack.fallback.outcome,
        pack.fallback.intent_ref,
        "no_matching_reaction_rule",
        False,
    )
