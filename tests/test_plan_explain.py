from __future__ import annotations

from pathlib import Path

import pytest

from rexecop.errors import RExecOpValidationError
from rexecop.operation.plan_explain import explain_operation_plan_request

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE = REPO_ROOT / 'examples/profiles/runtime-fixture/profile.yaml'
ENVIRONMENT_POLICY = REPO_ROOT / 'examples/environments/runtime-fixture.policy.example.yaml'


def test_explain_operation_plan_request_without_profile_raises() -> None:
    with pytest.raises(RExecOpValidationError, match='profile is required'):
        explain_operation_plan_request(
            profile_path=None,
            environment_path=None,
            intent='inspect_fixture_state',
            target='fixture-target',
            mode='dry_run',
        )


def test_explain_operation_plan_request_combines_profile_and_policy() -> None:
    payload = explain_operation_plan_request(
        profile_path=PROFILE,
        environment_path=ENVIRONMENT_POLICY,
        intent='inspect_fixture_state',
        target='fixture-target',
        mode='dry_run',
    )

    assert payload['schema'] == 'rexecop.plan_explain.v0.1'
    assert payload['status'] == 'ready'
    assert payload['operation_projection']['operation']['id'] == 'inspect_fixture_state'
    assert payload['policy_projection']['schema'] == 'rexecop.policy_explain.v0.1'