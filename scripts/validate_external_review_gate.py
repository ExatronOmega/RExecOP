#!/usr/bin/env python3
"""Release-candidate external/security review gate for M8.5."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REVIEW_DIR = ROOT / "docs" / "release-security-review"
REVIEW_SCHEMA = "rexecop.release_security_review.v0.1"
ALLOWED_REVIEW_MODES = frozenset({"independent_review", "solo_reviewed_alpha_risk"})
REQUIRED_SURFACES = frozenset(
    {
        "governance_admission_binding",
        "mutation_gates",
        "connector_output_safety",
        "release_train_scripts",
        "supply_chain_workflow",
    }
)


def current_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def review_record_path(version: str) -> Path:
    return REVIEW_DIR / f"{version}.json"


def load_review_record(version: str) -> dict[str, Any]:
    path = review_record_path(version)
    if not path.is_file():
        raise ValueError(f"review_record_missing:{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"review_record_not_object:{path}")
    return payload


def validate_review_record(payload: dict[str, Any], *, version: str) -> list[str]:
    errors: list[str] = []
    if str(payload.get("schema") or "") != REVIEW_SCHEMA:
        errors.append(f"review_schema_mismatch:{payload.get('schema')}")
    if str(payload.get("version") or "") != version:
        errors.append(f"review_version_mismatch:{payload.get('version')}!={version}")
    mode = str(payload.get("review_mode") or "")
    if mode not in ALLOWED_REVIEW_MODES:
        errors.append(f"review_mode_invalid:{mode}")
    reviewer = str(payload.get("reviewer_ref") or "").strip()
    if not reviewer:
        errors.append("reviewer_ref_missing")
    reviewed_at = str(payload.get("reviewed_at") or "").strip()
    if not reviewed_at:
        errors.append("reviewed_at_missing")
    surfaces = payload.get("surfaces")
    if not isinstance(surfaces, list):
        errors.append("surfaces_not_list")
        return errors
    declared = {str(item).strip() for item in surfaces if str(item).strip()}
    missing = sorted(REQUIRED_SURFACES - declared)
    if missing:
        errors.append(f"review_surfaces_missing:{','.join(missing)}")
    if mode == "solo_reviewed_alpha_risk":
        notes = str(payload.get("notes") or "").strip()
        if not notes:
            errors.append("solo_review_notes_required")
    return errors


def collect_errors(*, version: str | None = None) -> list[str]:
    resolved = version or current_version()
    errors: list[str] = []
    try:
        payload = load_review_record(resolved)
    except ValueError as exc:
        errors.append(str(exc))
        return errors
    errors.extend(validate_review_record(payload, version=resolved))
    return errors


def success_line(version: str, review_mode: str) -> str:
    return f"external_review_gate_ok:rexecop=={version}:mode={review_mode}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate release security review record for a version."
    )
    parser.add_argument(
        "--version",
        default="",
        help="Package version (defaults to pyproject.toml project.version).",
    )
    args = parser.parse_args(argv)
    version = args.version.strip() or current_version()
    errors = collect_errors(version=version)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    payload = load_review_record(version)
    print(success_line(version, str(payload["review_mode"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
