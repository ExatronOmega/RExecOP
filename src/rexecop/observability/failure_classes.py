from __future__ import annotations

FAILURE_CLASSES = frozenset(
    {
        "config",
        "profile",
        "policy",
        "connector",
        "target",
        "runtime",
        "evidence",
        "mutation-contract",
    }
)


def is_valid_failure_class(value: str) -> bool:
    return str(value or "") in FAILURE_CLASSES


def normalize_failure_class(value: str, *, default: str = "runtime") -> str:
    normalized = str(value or "").strip()
    if normalized in FAILURE_CLASSES:
        return normalized
    if default in FAILURE_CLASSES:
        return default
    return "runtime"