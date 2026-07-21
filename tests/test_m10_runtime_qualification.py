from __future__ import annotations

from pathlib import Path

import yaml

from rexecop.cli_output import render_doctor_table
from rexecop.profile.extension_manifest import build_plugin_compatibility_report
from rexecop.runtime.doctor import run_runtime_doctor
from rexecop.runtime.init import initialize_runtime_root

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE = REPO_ROOT / "examples/first-run-demo/profile/profile.yaml"
ENVIRONMENT = REPO_ROOT / "examples/first-run-demo/environment.yaml"
CATALOG = REPO_ROOT / "examples/first-run-demo/catalog.yaml"


def _initialize(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    initialize_runtime_root(root, backend="file")
    return root


def _installed_plugin_allowlist() -> str:
    inventory = build_plugin_compatibility_report()["inventory"]
    names = {
        str(item.get("name") or "")
        for group in ("connector_backends", "internal_action_registrars")
        for item in inventory.get(group) or []
    }
    names.discard("")
    assert names, "M10 runtime qualification requires installed plugin inventory"
    return ",".join(sorted(names))


def _check(report: dict[str, object], check_id: str) -> dict[str, object]:
    checks = report["checks"]
    assert isinstance(checks, list)
    return next(
        item for item in checks if isinstance(item, dict) and item.get("id") == check_id
    )


def test_stable_doctor_reports_complete_runtime_qualification(tmp_path: Path) -> None:
    allowlist = _installed_plugin_allowlist()

    report = run_runtime_doctor(
        _initialize(tmp_path),
        profile=str(PROFILE),
        env_path=ENVIRONMENT,
        catalog_path=CATALOG,
        deployment_posture="stable",
        plugin_allowlist=allowlist,
    )

    assert report["status"] == "passed"
    assert report["blockers"] == []
    assert report["security_blockers"] == []
    assert _check(report, "storage_backend")["details"]["certification_tier"] == (
        "stable_single_host"
    )
    assert _check(report, "executor_posture")["details"]["certified"] == (
        "single_executor"
    )
    assert _check(report, "mutation_posture")["details"]["certified"] == (
        "stable_read_only"
    )
    plugin = _check(report, "plugin_posture")
    assert plugin["status"] == "passed"
    assert plugin["details"]["installed"] == plugin["details"]["allowlist"]


def test_doctor_classifies_mutation_and_plugin_failures_as_security_blockers(
    tmp_path: Path,
) -> None:
    root = _initialize(tmp_path)

    mutation = run_runtime_doctor(root, mutation_posture="lab_only")
    plugins = run_runtime_doctor(root, deployment_posture="stable")

    assert mutation["security_blockers"] == ["mutation_posture"]
    assert plugins["security_blockers"] == ["plugin_posture"]
    assert "security_blockers=mutation_posture" in render_doctor_table(mutation)


def test_doctor_classifies_unsafe_network_posture_as_security_blocker(
    tmp_path: Path,
) -> None:
    environment = tmp_path / "unsafe-network.yaml"
    environment.write_text(
        yaml.safe_dump(
            {
                "environment": {
                    "id": "unsafe-network",
                    "profile": "fixture",
                    "targets": {"target": {"type": "fixture"}},
                    "connectors": {
                        "api": {
                            "enabled": True,
                            "backend": "http_api",
                            "base_url": "http://api.example",
                        }
                    },
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    report = run_runtime_doctor(_initialize(tmp_path), env_path=environment)

    assert report["security_blockers"] == ["network_egress_posture"]
    assert "api:https_required" in _check(report, "network_egress_posture")[
        "details"
    ]["blockers"]


def test_storage_certification_blocker_is_not_mislabeled_as_security(
    tmp_path: Path,
) -> None:
    report = run_runtime_doctor(_initialize(tmp_path), storage_backend="sqlite")

    assert "storage_backend" in report["blockers"]
    assert report["security_blockers"] == []
