from __future__ import annotations

from scripts import validate_g6_release_candidate_gate as gate


def test_g6_gate_covers_required_release_candidate_paths() -> None:
    selected = "\n".join(gate.TESTS)

    assert "allows_readonly_fixture_with_matching_governance" in selected
    assert "enforces_typed_execution_governance_before_backend_io" in selected
    assert "blocked_network_boundary_mismatch" in selected
    assert "http_api_reads_fixture_state_against_staging_server" in selected
    assert "http_api_blocks_mutating_without_governance" in selected
    assert "stable_http_rejects_plaintext_before_io" in selected
    assert "resolved_http_destination_must_match_declared_binding_before_io" in selected
    assert "signed_decision_is_bound_claimed_and_projected_to_runtime_permit" in selected
    assert "full_bundle_review_verdict_pass" in selected
    assert "review_bundle_matches_sclite_govengine_integration_shape" in selected
