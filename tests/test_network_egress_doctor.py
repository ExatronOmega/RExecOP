from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from rexecop.runtime.doctor import _check_network_egress_posture

pytestmark = pytest.mark.security_regression


def _environment(tmp_path: Path, connector: dict[str, object]) -> Path:
    path = tmp_path / "environment.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "environment": {
                    "id": "network-doctor",
                    "profile": "fixture",
                    "targets": {"target": {"type": "fixture"}},
                    "connectors": {"api": {"enabled": True, "backend": "http_api", **connector}},
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_doctor_blocks_stable_plaintext_http(tmp_path: Path) -> None:
    check = _check_network_egress_posture(
        _environment(tmp_path, {"base_url": "http://api.example"})
    )
    assert check["status"] == "blocker"
    assert "api:https_required" in check["details"]["blockers"]


def test_doctor_blocks_stable_dns_without_egress_dependency(tmp_path: Path) -> None:
    check = _check_network_egress_posture(
        _environment(tmp_path, {"base_url": "https://api.example"})
    )
    assert check["status"] == "blocker"
    assert "api:dns_rebinding_control_missing" in check["details"]["blockers"]


def test_doctor_accepts_stable_dns_with_operator_egress_dependency(tmp_path: Path) -> None:
    check = _check_network_egress_posture(
        _environment(
            tmp_path,
            {
                "base_url": "https://api.example",
                "operator_egress_enforced": True,
                "dns_rebinding_protection": "operator_egress",
            },
        )
    )
    assert check["status"] == "passed"
    assert check["details"]["connectors"][0]["origin_binding_digest"].startswith(
        "sha256:"
    )


def test_doctor_accepts_explicit_loopback_lab(tmp_path: Path) -> None:
    check = _check_network_egress_posture(
        _environment(
            tmp_path,
            {"base_url": "http://127.0.0.1:8080", "deployment_posture": "lab"},
        )
    )
    assert check["status"] == "passed"
    assert check["details"]["connectors"][0]["address_class"] == "loopback"
