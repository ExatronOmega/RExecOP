from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from govengine.api import GovApiError, require_mapping
from govengine.conformance import (
    ConformanceOutcome,
    run_govengine_conformance_case,
    validate_conformance_case,
)
from govengine.governance_decision import GovernanceDecision
from govengine.signing import (
    DemoDigestVerifier,
    SignedArtifact,
    SigningPolicy,
    TrustPolicy,
)

from rexecop.adapters.govengine_port.runtime_authority import (
    RuntimeAttemptGovernanceFacts,
    SignedGovernanceDecisionBundle,
    TrustedGovernanceDecisionConsumer,
)
from rexecop.errors import RExecOpGovernanceDecisionError
from rexecop.storage.file_store import FileStore


class _StaticConformanceAuthority:
    def __init__(
        self,
        decision: GovernanceDecision,
        signed_artifact: SignedArtifact,
    ) -> None:
        self.decision = decision
        self.signed_artifact = signed_artifact

    def authorize_attempt(
        self,
        facts: RuntimeAttemptGovernanceFacts,
    ) -> SignedGovernanceDecisionBundle:
        return SignedGovernanceDecisionBundle(
            decision=self.decision,
            signed_artifact=self.signed_artifact,
        )


def run_rexecop_conformance_case(
    case: Mapping[str, Any],
    *,
    store_root: Path,
) -> ConformanceOutcome:
    checked = validate_conformance_case(case)
    if checked['operation'] != 'consume_decision':
        return run_govengine_conformance_case(checked)

    payload = require_mapping(
        checked['input'],
        reason_code='invalid_conformance_case_input',
    )
    decision = GovernanceDecision.from_mapping(
        require_mapping(
            payload.get('governance_decision'),
            reason_code='invalid_governance_decision',
        )
    )
    signed_artifact = SignedArtifact.from_mapping(
        require_mapping(
            payload.get('signed_artifact'),
            reason_code='invalid_signed_artifact',
        )
    )
    facts_payload = require_mapping(
        payload.get('runtime_facts'),
        reason_code='invalid_runtime_attempt_governance_facts',
    )
    try:
        facts = RuntimeAttemptGovernanceFacts(**dict(facts_payload))
    except TypeError as exc:
        raise GovApiError('invalid_runtime_attempt_governance_facts') from exc
    repeat = payload.get('repeat', 1)
    if isinstance(repeat, bool) or not isinstance(repeat, int) or repeat not in {1, 2}:
        raise GovApiError('invalid_conformance_decision_repeat')
    consumer = TrustedGovernanceDecisionConsumer(
        store=FileStore(store_root),
        authority=_StaticConformanceAuthority(decision, signed_artifact),
        verifier=DemoDigestVerifier(
            allowed_signer_ids=('conformance-decision-signer',)
        ),
        signing_policy=SigningPolicy(
            require_signature=True,
            allowed_modes=('detached_demo_digest',),
            required_signer_ids=('conformance-decision-signer',),
        ),
        trust_policy=TrustPolicy(),
    )
    if decision.authorization is None:
        raise GovApiError('conformance_decision_without_authorization')
    checked_at = datetime.fromisoformat(decision.authorization.issued_at) + timedelta(
        seconds=1
    )
    try:
        for _ in range(repeat):
            consumer.authorize_and_claim(facts, now=checked_at)
    except RExecOpGovernanceDecisionError as exc:
        return ConformanceOutcome('rejected', exc.reason_code)
    return ConformanceOutcome('allowed', 'governance_decision_claimed')
