"""Pure attention projections for canonical non-native coordination facts.

The classifiers never infer a failure from silence, a normal claim, or a
cleanup retry. Missing proofs produce no occurrence. SQL supplies metadata,
never message bodies, native output, grant credentials or raw error text.
"""
from __future__ import annotations

import json
from datetime import timedelta

from ..domain.attention import instant, occurrence
from ..domain.base import iso_to_epoch
from ..domain.handoff import is_eligible_verifier
from ..domain.permissions import PermissionSet
from ..domain.routing import can_agent_see_event, is_agent_eligible
from ..domain.tag_selector import reachable


def operator_policy(facts: dict | None, *, operator_id: str = "operator", require_active: bool = True) -> dict:
    """Resolve once per read using the same permission/routing primitives.

    The endpoint authenticates the operator before this projection. A missing
    built-in local operator retains the canonical default permission policy;
    a missing named agent is never allowed to act as that operator.
    """
    facts = facts or {}
    return {
        "operator_id": operator_id,
        "operator_capabilities": facts.get("capabilities") or [],
        "operator_role": facts.get("role"),
        "operator_tags": facts.get("tags"),
        "operator_can_verify": bool(
            ((not require_active or facts.get("is_active")) if facts else operator_id == "operator")
            and PermissionSet(facts.get("permissions")).allows("handoffs", "work")
        ),
    }


def handoff_eligible(facts_json: str, now: str) -> int:
    """Canonical current eligibility of one registered potential claimant.

    Dependency satisfaction is a separate SQL EXISTS predicate. Waiting starts
    at the current OPEN generation or its last dependency completion; this
    does not infer when an agent acquired a capability or became available.
    """
    facts = json.loads(facts_json)
    handoff, candidate, creator = facts["handoff"], facts["candidate"], facts["creator"]
    return int(bool(candidate.get("is_active")
        and PermissionSet(candidate.get("permissions")).allows("handoffs", "work")
        and can_agent_see_event(candidate, handoff, now)
        and is_agent_eligible(candidate, handoff["target"], handoff["created_at"], now)
        and reachable(creator, candidate)))


def _base(facts: dict, *, kind: str, source_type: str | None = None) -> dict:
    return dict(
        kind=kind, source_type=source_type or facts["source_type"],
        source_id=facts["source_id"], episode=facts["episode"],
        source_revision=facts["source_revision"],
        first_detected_at=facts["first_detected_at"],
        last_changed_at=facts["last_changed_at"],
        **{key: facts.get(key) for key in
           ("agent_id", "workspace_id", "session_id", "operation_id")},
    )


def _verifier(facts: dict, now: str, policy: dict) -> bool:
    operator = policy.get("operator_id", "operator")
    if not policy.get("operator_can_verify") or operator == facts.get("claimed_by"):
        return False
    viewer = dict(agent_id=operator, workspace_id=facts["workspace_id"],
                  capabilities=policy.get("operator_capabilities", []),
                  role=policy.get("operator_role"), tags=policy.get("operator_tags"))
    if operator != facts.get("from_agent_id") and not can_agent_see_event(viewer, facts, now):
        return False
    return is_eligible_verifier(operator, creator=facts.get("from_agent_id"),
        verify_by=facts.get("verify_by") or {},
        caller_capabilities=policy.get("operator_capabilities", []))


def project(facts: dict, now: str, policy: dict) -> list[dict]:
    """Project one current source snapshot without SQL, I/O or mutation."""
    family = facts.get("family")
    if family == "verification":
        if facts.get("status") != "VERIFYING":
            return []
        can_verify = _verifier(facts, now, policy)
        base = _base(facts, kind="verification_pending")
        base["source_revision"] = [facts["source_revision"], can_verify]
        return [occurrence(**base,
            category="action_required" if can_verify else "watch", severity="info",
            priority=30 if can_verify else 20,
            allowed_actions=["inspect_handoff"] + (["verify_handoff"] if can_verify else []))]
    if family == "unknown":
        if not facts.get("uncertain"):
            return []
        return [occurrence(**_base(facts, kind="execution_outcome_unknown"),
            category="action_required", severity="warning", priority=30,
            allowed_actions=["inspect_operation", "inspect_recovery"])]
    if family == "parked":
        if facts.get("status") != "parked":
            return []
        return [occurrence(**_base(facts, kind="delivery_parked"),
            category="action_required", severity="warning", priority=20,
            allowed_actions=["inspect_delivery"])]
    if family == "recovery":
        if facts.get("status") != "attention" or not facts.get("delivery_pending"):
            return []
        return [occurrence(**_base(facts, kind="runtime_recovery_attention"),
            category="action_required", severity="warning", priority=30,
            allowed_actions=["inspect_recovery"])]
    if family == "authority":
        if not facts.get("pending") or not facts.get("authority_blocked"):
            return []
        return [occurrence(**_base(facts, kind="execution_authority_blocking"),
            category="action_required", severity="warning", priority=30,
            allowed_actions=["inspect_operation", "review_authority"])]
    if family == "disconnected":
        if facts.get("control_state") != "DISCONNECTED" or not facts.get("pending"):
            return []
        threshold = policy.get("executor_disconnected_seconds")
        boundary = ((instant(facts["first_detected_at"]) + timedelta(seconds=threshold)).isoformat(timespec="microseconds")
                    if type(threshold) in (int, float) and threshold > 0 else None)
        escalated = bool(boundary and iso_to_epoch(now) >= iso_to_epoch(boundary))
        base = _base(facts, kind="executor_disconnected_with_work")
        base["source_revision"] = [facts["source_revision"], threshold, escalated]
        if escalated and iso_to_epoch(boundary) > iso_to_epoch(base["last_changed_at"]):
            base["last_changed_at"] = boundary
        return [occurrence(**base,
            category="action_required" if escalated else "watch",
            severity="warning" if escalated else "info", priority=30 if escalated else 20,
            next_change_at=boundary if boundary and not escalated else None,
            allowed_actions=["inspect_executor", "inspect_recovery"])]
    if family == "result":
        if not facts.get("canonical_result"):
            return []
        return [occurrence(**_base(facts, kind="result_unseen"),
            resolution="resolved", active=True, severity="info", priority=10,
            allowed_actions=["inspect_result"])]
    if family == "aged":
        threshold = policy.get("handoff_unclaimed_seconds")
        if (facts.get("status") != "OPEN" or not facts.get("eligible")
                or type(threshold) not in (int, float) or threshold <= 0):
            return []
        boundary = (instant(facts["first_detected_at"]) + timedelta(seconds=threshold)).isoformat(timespec="microseconds")
        if iso_to_epoch(now) < iso_to_epoch(boundary):
            return []
        # Repeated GETs never become a new episode or move the threshold.
        base = _base(facts, kind="handoff_unclaimed_aged")
        base["first_detected_at"] = base["last_changed_at"] = boundary
        return [occurrence(**base, category="watch", severity="info", priority=20,
            allowed_actions=["inspect_handoff"])]
    if family == "cleanup":
        if (facts.get("status") != "PENDING" or facts.get("productive_outcome") != "success"
                or facts.get("failure_code") != "ARTIFACT_CLEANUP_UNCONFIRMED"):
            return []
        return [occurrence(**_base(facts, kind="cleanup_attention"),
            category="action_required", severity="warning", priority=20,
            allowed_actions=["inspect_cleanup"])]
    # No blanket classifier for CLOSING, ordinary RECOVERING/CLAIMED, old
    # failures, elapsed silence, or an OPEN handoff without eligibility proof.
    return []
