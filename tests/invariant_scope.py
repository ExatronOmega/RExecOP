"""Canonical stack invariant test scope for M8.5 property/invariant gates."""

from __future__ import annotations

from pathlib import Path

INVARIANT_TEST_MODULE = "test_stack_invariants"
INVARIANT_PYTEST_MARKER = "invariant"
INVARIANT_GATE_SCRIPT = "scripts/validate_stack_invariants.py"

# Themes exercised by tests/test_stack_invariants.py (values are section docstrings).
INVARIANT_THEMES: dict[str, str] = {
    "canonical_digest_normalization": "canonical JSON and digest normalization",
    "unknown_major_fail_closed": "unknown major schema versions fail closed",
    "policy_admission_spec_binding": "policy/admission/spec/receipt binding invariants",
    "public_projection_allowlist": "public projection allowlist before redaction",
    "idempotency_replay_recovery": "idempotency keys and replay/recovery invariants",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
