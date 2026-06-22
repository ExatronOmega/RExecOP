from __future__ import annotations

from collections.abc import Iterable
from pathlib import PurePath
from typing import Any

from govengine.execution.command_shape import normalize_argv


def _contains_no_restricted_patterns(
    tool: Any,
    args: Iterable[Any],
) -> tuple[bool, str]:
    normalized_tool = PurePath(str(tool).strip().lower()).name
    tokens = [str(item).strip().lower() for item in args]

    if normalized_tool == "sudo" or "sudo" in tokens:
        return True, "sudo"

    if normalized_tool in {"bash", "dash", "sh", "zsh"} and any(
        token in {"-c", "--command"} for token in tokens
    ):
        return True, "shell_command"

    if normalized_tool == "systemctl":
        action = _first_positional(tokens)
        if action in {"start", "stop", "restart", "reload", "enable", "disable"}:
            return True, f"systemctl_{action}"

    if normalized_tool == "service" and any(
        token in {"start", "stop", "restart", "reload"} for token in tokens
    ):
        return True, "service_mutation"

    if normalized_tool == "docker":
        action_index, action = _first_positional_with_index(tokens)
        if action in {"exec", "restart", "start", "stop", "kill", "rm", "run", "update"}:
            return True, f"docker_{action}"
        if action == "compose":
            compose_action = _first_positional(tokens[action_index + 1 :])
            if compose_action in {"up", "down", "restart"}:
                return True, f"docker_compose_{compose_action}"

    if normalized_tool == "docker-compose":
        action = _first_positional(tokens)
        if action in {"up", "down", "restart"}:
            return True, f"docker_compose_{action}"

    return False, ""


def _first_positional(tokens: list[str]) -> str:
    return _first_positional_with_index(tokens)[1]


def _first_positional_with_index(tokens: list[str]) -> tuple[int, str]:
    for index, token in enumerate(tokens):
        if token and not token.startswith("-"):
            return index, token
    return -1, ""


def normalize_allowlisted_argv(
    *,
    tool: str,
    args: Iterable[Any],
    allowed_tools: Iterable[str],
) -> list[str]:
    """Validate allowlisted shell invocation via GovEngine command_shape."""
    return normalize_argv(
        tool,
        args,
        allowed_tools=allowed_tools,
        contains_tool_restricted_patterns=_contains_no_restricted_patterns,
        normalize_tool=lambda value: str(value).strip().lower(),
    )
