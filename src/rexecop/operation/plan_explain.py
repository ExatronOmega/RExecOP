from __future__ import annotations

from pathlib import Path
from typing import Any

from rexecop.catalog.service import CatalogService
from rexecop.errors import RExecOpValidationError
from rexecop.policy.explain import explain_operation_policy
from rexecop.profile.loader import load_profile
from rexecop.profile.operator_metadata import explain_profile_operation
from rexecop.profile.resolver import resolve_profile_path

PLAN_EXPLAIN_SCHEMA = 'rexecop.plan_explain.v0.1'


def _resolve_profile_path_for_plan(
    *,
    profile_path: str | Path | None,
    environment_path: Path | None,
    intent: str,
    target: str,
    catalog_path: Path | None,
) -> Path | str:
    resolved_profile_path = profile_path
    if catalog_path is not None:
        catalog_resolution = CatalogService(catalog_path.expanduser().resolve()).resolve_operation(
            target,
            intent,
        )
        if not catalog_resolution.applicability.applicable:
            raise RExecOpValidationError(
                'catalog operation is not applicable: '
                f'{catalog_resolution.applicability.status}'
            )
        if profile_path is not None:
            supplied_profile = resolve_profile_path(profile_path).resolve()
            if supplied_profile.is_file():
                supplied_profile = supplied_profile.parent
            if supplied_profile != catalog_resolution.target.profile_path.resolve():
                raise RExecOpValidationError('catalog profile does not match supplied profile')
        if environment_path is not None and (
            environment_path.expanduser().resolve()
            != catalog_resolution.target.environment_path.resolve()
        ):
            raise RExecOpValidationError('catalog environment does not match supplied environment')
        resolved_profile_path = catalog_resolution.target.profile_path
    if resolved_profile_path is None:
        raise RExecOpValidationError('profile is required without a target catalog')
    return resolved_profile_path


def explain_operation_plan_request(
    *,
    profile_path: str | Path | None,
    environment_path: Path | None,
    intent: str,
    target: str,
    mode: str,
    catalog_path: Path | None = None,
) -> dict[str, Any]:
    """Project profile and policy context for a plan request without creating an operation."""
    resolved_profile_path = _resolve_profile_path_for_plan(
        profile_path=profile_path,
        environment_path=environment_path,
        intent=intent,
        target=target,
        catalog_path=catalog_path,
    )
    profile = load_profile(resolve_profile_path(resolved_profile_path))
    operation_projection = explain_profile_operation(profile, intent)
    policy_projection = explain_operation_policy(
        profile_path=profile_path,
        environment_path=environment_path,
        intent=intent,
        target=target,
        mode=mode,
        catalog_path=catalog_path,
    )
    policy_status = str(policy_projection.get('status') or '')
    status = 'blocked' if policy_status == 'blocked' else 'ready'
    return {
        'schema': PLAN_EXPLAIN_SCHEMA,
        'status': status,
        'profile': profile.name,
        'intent': intent,
        'target': target,
        'mode': mode,
        'operation_projection': operation_projection,
        'policy_projection': policy_projection,
        'non_claims': [
            'Does not create or persist an operation.',
            'Does not execute connectors or mutate infrastructure.',
            'Policy projection is advisory; admission happens at plan/start time.',
        ],
    }