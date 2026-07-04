from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from rexecop.catalog.service import CatalogService
from rexecop.catalog.unavailable import build_unavailable_operations_report
from rexecop.cli import app
from rexecop.profile.discoverability import show_profile_manifest
from rexecop.profile.loader import load_profile
from rexecop.profile.operator_metadata import (
    OPERATION_PROFILE_EXPLAIN_SCHEMA,
    collect_operator_metadata_errors,
    explain_profile_operation,
    intent_operator_metadata,
    resolve_failure_operator_hints,
)
from rexecop.profile.resolver import resolve_profile_path

REGISTERED_PROFILE = "tecrax"
ROOT = Path(__file__).resolve().parents[1]
TECRAX_CATALOG = (
    Path(__file__).resolve().parents[2]
    / "tecrax"
    / "examples"
    / "catalogs"
    / "targets.readonly.example.yaml"
)

runner = CliRunner()


def test_tecrax_operator_metadata_covers_all_intents() -> None:
    profile = load_profile(resolve_profile_path(REGISTERED_PROFILE))

    errors = collect_operator_metadata_errors(profile)

    assert errors == []
    assert intent_operator_metadata(profile, "diagnose_monitoring_host") is not None


def test_explain_profile_operation_includes_operator_metadata() -> None:
    profile = load_profile(resolve_profile_path(REGISTERED_PROFILE))

    payload = explain_profile_operation(profile, "collect_basic_host_inventory")

    assert payload["schema"] == OPERATION_PROFILE_EXPLAIN_SCHEMA
    assert payload["operation"]["id"] == "collect_basic_host_inventory"
    assert payload["operator_metadata"]["label"] == "Collect basic host inventory"
    assert payload["operator_metadata"]["runbook_hint"]
    assert payload["operator_metadata"]["failure_mapping"]["policy"]["operator_summary"]


def test_failure_operator_hints_are_profile_owned() -> None:
    profile = load_profile(resolve_profile_path(REGISTERED_PROFILE))

    hints = resolve_failure_operator_hints(profile, "diagnose_monitoring_host", "policy")

    assert hints["operator_summary"]
    assert hints["safe_next_options"]


def test_unavailable_operations_merge_profile_safe_next_options() -> None:
    service = CatalogService(TECRAX_CATALOG)
    payload = build_unavailable_operations_report(
        service,
        "network-device-01",
        intent="diagnose_monitoring_host",
    )

    entry = payload["unavailable"][0]
    assert entry["operation_id"] == "diagnose_monitoring_host"
    options = entry["safe_next_options"]
    assert any("runbook show diagnose_monitoring_host" in item for item in options)


def test_profiles_show_reports_operator_metadata_coverage() -> None:
    payload = show_profile_manifest(REGISTERED_PROFILE)

    assert payload["operator_metadata"]["status"] == "passed"
    assert payload["operator_metadata"]["intent_count"] == 14
    assert payload["developer_check"]["operator_metadata"]["status"] == "passed"


def test_collect_operator_metadata_errors_flags_missing_intent(tmp_path: Path) -> None:
    profile_root = tmp_path / "broken-profile"
    intents = profile_root / "intents"
    intents.mkdir(parents=True)
    (profile_root / "profile.yaml").write_text(
        """
profile_contract:
  name: broken
  version: "0.0.1"
  intents: {required: true}
  workflows: {required: true}
  connector_requirements: {required: true}
  risk_classes: {required: true}
  evidence_requirements: {required: true}
  governance_expectations: {required: true}
  validation_rules: {required: true}
  escalation_rules: {required: true}
""".strip(),
        encoding="utf-8",
    )
    (intents / "demo.yaml").write_text("intent: {id: demo}\n", encoding="utf-8")
    (profile_root / "operator_metadata.yaml").write_text(
        """
operator_metadata:
  schema_version: v0.1
  profile:
    label: Broken
  intents: {}
""".strip(),
        encoding="utf-8",
    )

    profile = load_profile(profile_root)
    errors = collect_operator_metadata_errors(profile)

    assert "operator_metadata.intents:required" in errors


def test_operations_explain_cli_emits_profile_operator_metadata() -> None:
    result = runner.invoke(
        app,
        ["operations", "explain", "diagnose_monitoring_host", "--profile", REGISTERED_PROFILE],
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema"] == OPERATION_PROFILE_EXPLAIN_SCHEMA
    assert payload["operator_metadata"]["intent"] == "diagnose_monitoring_host"