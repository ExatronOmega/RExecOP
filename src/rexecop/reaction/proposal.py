from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sclite.artifacts import artifact_sha256

from rexecop.contracts.orchestration import validate_escalation_proposal
from rexecop.errors import RExecOpValidationError
from rexecop.operation.model import utc_now_iso
from rexecop.profile.loader import load_profile
from rexecop.profile.resolver import resolve_profile_path
from rexecop.reaction.service import _validate_reaction_intent
from rexecop.storage.atomic import atomic_write_text, secure_directory

PROPOSAL_REVIEW_SCHEMA = "rexecop.proposal_review.v0.1"
PROPOSAL_SUBMISSION_SCHEMA = "rexecop.proposal_submission.v0.1"
PROPOSAL_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
SUBMISSION_DECISIONS = frozenset({"accept_for_planning", "reject"})


def review_escalation_proposal(
    *,
    profile_path: str | Path,
    proposal_path: Path,
) -> dict[str, Any]:
    profile = load_profile(resolve_profile_path(profile_path))
    proposal = _read_proposal(proposal_path)
    _validate_profile_compatibility(profile, proposal)
    return {
        "schema": PROPOSAL_REVIEW_SCHEMA,
        "status": "reviewable",
        "proposal": _proposal_summary(proposal),
        "profile": profile.name,
        "verdict": {
            "shape": "valid",
            "profile_compatible": True,
            "trusted": False,
            "may_execute": False,
            "requires_govengine_admission": True,
            "submit_decisions": sorted(SUBMISSION_DECISIONS),
        },
        "safe_next_actions": [
            "rexecop reaction-proposal-submit --decision accept_for_planning "
            "--reviewer <operator> --reason <reason>",
            "rexecop reaction-proposal-submit --decision reject "
            "--reviewer <operator> --reason <reason>",
        ],
        "non_claims": _non_claims(),
    }


def submit_escalation_proposal(
    *,
    root: Path,
    profile_path: str | Path,
    proposal_path: Path,
    decision: str,
    reviewer: str,
    reason: str,
) -> dict[str, Any]:
    normalized_decision = decision.strip()
    if normalized_decision not in SUBMISSION_DECISIONS:
        raise RExecOpValidationError(f"unsupported proposal decision: {decision}")
    reviewer_ref = reviewer.strip()
    if not reviewer_ref:
        raise RExecOpValidationError("proposal reviewer is required")
    reason_code = reason.strip()
    if not reason_code:
        raise RExecOpValidationError("proposal review reason is required")
    if len(reason_code) > 160:
        raise RExecOpValidationError("proposal review reason is too long")

    review = review_escalation_proposal(
        profile_path=profile_path,
        proposal_path=proposal_path,
    )
    proposal = review["proposal"]
    submission = {
        "schema": PROPOSAL_SUBMISSION_SCHEMA,
        "status": "recorded",
        "decision": normalized_decision,
        "proposal": proposal,
        "reviewer_ref": reviewer_ref,
        "reason": reason_code,
        "submitted_at": utc_now_iso(),
        "may_execute": False,
        "requires_normal_plan": normalized_decision == "accept_for_planning",
        "requires_govengine_admission": True,
        "record_path": "",
        "safe_next_actions": _submit_safe_next_actions(normalized_decision, proposal),
        "non_claims": _non_claims(),
    }
    path = _submission_path(root, str(proposal["proposal_id"]))
    submission["record_path"] = str(path)
    atomic_write_text(
        path,
        json.dumps(submission, indent=2, sort_keys=True) + "\n",
    )
    return submission


def _read_proposal(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RExecOpValidationError("proposal must be a JSON object")
    validate_escalation_proposal(payload)
    proposal_id = str(payload.get("proposal_id") or "")
    if not PROPOSAL_ID.fullmatch(proposal_id):
        raise RExecOpValidationError("proposal_id contains unsupported characters")
    return payload


def _validate_profile_compatibility(profile: Any, proposal: dict[str, Any]) -> None:
    outcome = str(proposal.get("suggested_outcome") or "")
    intent_ref = str(proposal.get("intent_ref") or "").strip() or None
    if outcome in {"run_intent", "retry_intent"}:
        if intent_ref is None:
            raise RExecOpValidationError("proposal intent_ref is required")
        _validate_reaction_intent(profile, intent_ref)
    elif intent_ref is not None:
        raise RExecOpValidationError("proposal intent_ref is only valid for intent outcomes")


def _proposal_summary(proposal: dict[str, Any]) -> dict[str, Any]:
    authority = proposal.get("authority")
    if not isinstance(authority, dict):
        authority = {}
    explanation = str(proposal.get("explanation") or "")
    return {
        "proposal_id": str(proposal.get("proposal_id") or ""),
        "reaction_id": str(proposal.get("reaction_id") or ""),
        "schema_ref": str(proposal.get("schema_ref") or ""),
        "proposal_digest": _sha256_ref(proposal),
        "suggested_outcome": str(proposal.get("suggested_outcome") or ""),
        "intent_ref": str(proposal.get("intent_ref") or ""),
        "evidence_refs": [str(item) for item in proposal.get("evidence_refs") or []],
        "explanation_chars": len(explanation),
        "authority": {
            "trusted": bool(authority.get("trusted")),
            "may_execute": bool(authority.get("may_execute")),
            "requires_profile_validation": bool(authority.get("requires_profile_validation")),
            "requires_govengine_admission": bool(authority.get("requires_govengine_admission")),
        },
    }


def _submission_path(root: Path, proposal_id: str) -> Path:
    directory = root / "proposal_reviews"
    secure_directory(directory)
    return directory / f"{proposal_id}.json"


def _submit_safe_next_actions(decision: str, proposal: dict[str, Any]) -> list[str]:
    if decision == "reject":
        return ["Record is final for this proposal; no operation is planned."]
    intent_ref = str(proposal.get("intent_ref") or "").strip() or "<intent>"
    return [
        "Create a normal RExecOp plan only after operator review of environment, target and mode.",
        "rexecop plan --profile <profile> --env <env> "
        f"--intent {intent_ref} --target <target> --mode dry_run",
        "GovEngine admission and SCLite evidence remain required before execution claims.",
    ]


def _non_claims() -> list[str]:
    return [
        "Does not execute the proposal.",
        "Does not create an operation plan.",
        "Does not approve GovEngine admission.",
        "Does not expose raw proposal explanation text or secret values.",
        "SCLite remains authority for escalation_proposal artifact shape.",
    ]


def _sha256_ref(value: dict[str, Any]) -> str:
    digest = artifact_sha256(value)
    return digest if digest.startswith("sha256:") else f"sha256:{digest}"
