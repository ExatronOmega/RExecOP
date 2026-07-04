from __future__ import annotations

from rexecop.profile.govengine_governance import (
    build_profile_governance_request,
    evaluate_profile_governance,
)


def test_build_profile_governance_request_for_tecrax() -> None:
    request = build_profile_governance_request("tecrax", track="readonly")

    assert request["profile_name"] == "tecrax"
    assert request["supported_tracks"] == ["readonly"]
    assert request["policy_hooks"]
    assert request["required_capabilities"]
    assert request["profile_declared_capabilities"] == request["required_capabilities"]


def test_evaluate_profile_governance_passes_for_tecrax_readonly() -> None:
    result = evaluate_profile_governance("tecrax", track="readonly")

    assert result["status"] == "passed"
    assert result["governance"]["status"] == "passed"
    assert result["compatibility"]["status"] == "passed"
    assert "govengine_governance" not in result
    assert result["schema"] == "rexecop.profile_governance_bundle.v0.1"