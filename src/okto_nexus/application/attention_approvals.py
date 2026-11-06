"""Passive operator review of noncanonical-native approval references.

``decide_approval`` opens the existing review control. It does not predict
that approved re-execution will pass current permissions, policy or quotas;
the same pending request may still be rejected by its operator. In particular,
feature_hitl gates interception, not decisions already in the canonical queue.
"""
from __future__ import annotations

from ..domain.attention import instant, occurrence
from ..errors import OktoNexusError


_COORDINATION_ACTIONS = frozenset({'message_create', 'broadcast', 'handoff_create'})
_LEGACY_NATIVE_ACTIONS = frozenset({'runtime_native_approval', 'execution.native.respond'})


def _coordination(facts, now):
    """Validate retained request identity without executing approval recovery."""
    reference = facts['coordination']
    if not facts['has_coordination']:
        return None, None
    if reference is None:
        return 'unavailable', None
    deadline = reference['expires_at']
    if instant(now) < instant(reference['created_at']) or instant(now) >= instant(deadline):
        return 'expired', deadline
    if (facts['action'] not in _COORDINATION_ACTIONS or not facts['coordination_matches']
            or reference['state'] != 'pending_approval' or reference['resource_id'] is not None):
        return 'stale', deadline
    return None, deadline


def project(facts: dict, now: str, policy: dict) -> list[dict]:
    """One immutable approval identity, retaining closed/expired references."""
    status = facts['status']
    archived = facts['archived_at']
    pending = status == 'pending' and not archived
    resolution = 'open' if pending else 'resolved'
    reason, deadline = _coordination(facts, now)
    if not facts['payload_valid']:
        reason = 'unavailable'
    # Ordinary governance payloads have no expiry contract. Only a correlated
    # durable source may supply a deadline; never interpret arbitrary kwargs.
    if facts['action'] == 'execution.binding.authorize':
        proposal = facts['proposal']
        if proposal is None or not facts['proposal_matches']:
            reason = 'unavailable'
        else:
            deadline = proposal['expires_at']
            if instant(now) >= instant(deadline):
                reason = 'expired'
            elif proposal['status'] != 'PREPARED':
                reason = 'stale'
    if facts['action'] in _LEGACY_NATIVE_ACTIONS:
        legacy = facts['legacy']
        reason = 'stale' if legacy else 'unavailable'
        if legacy:
            deadline = legacy['expires_at']
        elif facts['action'] == 'execution.native.respond':
            deadline = facts['orphan_native_expires_at']
            # An orphan's old request is not a trusted source of a timestamp.
            # Retain its reference without letting malformed legacy payloads
            # turn a passive list into a failed read for every other source.
            if deadline is not None:
                try:
                    instant(deadline)
                except OktoNexusError:
                    deadline = None
        if deadline is not None and instant(now) >= instant(deadline):
            reason = 'expired'
    if pending and reason == 'expired':
        resolution = 'expired'
    recipient = facts['recipient_agent_id']
    if facts['recipient_type'] is None:
        recipient = 'operator'
    recipient_valid = facts['recipient_type'] in (None, 'text') and isinstance(recipient, str) and bool(recipient)
    if not recipient_valid and reason is None:
        reason = 'unavailable'
    wired = policy.get('decision_registry', {}).get(facts['action'], {})
    recognized = any(wired.get(key) is True for key in ('executor', 'validator', 'transactional'))
    actionable = bool(pending and reason is None and recipient_valid and recipient == 'operator'
        and policy['viewer_is_operator'] and policy['viewer_actor'] == 'operator' and recognized
        and facts['action'] not in _LEGACY_NATIVE_ACTIONS)
    changed = max((value for value in (facts['created_at'], facts['decided_at'], archived,
        deadline if resolution == 'expired' else None) if value is not None), key=instant)
    revision = dict(decision_revision=facts['decision_revision'], status=status, archived_at=archived,
        has_result=facts['has_result'], action=facts['action'], recipient=recipient,
        source=facts['source_revision'], resolution=resolution, reason=reason, actionable=actionable)
    freshness = 'unavailable' if reason == 'unavailable' else 'stale' if reason == 'stale' else 'current'
    if facts['action'] in _LEGACY_NATIVE_ACTIONS:
        freshness = 'stale' if facts['legacy'] else 'unavailable'
    return [occurrence(kind='approval_pending', source_type='approval', source_id=facts['approval_id'],
        # A failed executor can return the same request to pending. Its decision
        # revision changes the view fence, not the original request's episode.
        episode='request', source_revision=revision, first_detected_at=facts['created_at'],
        last_changed_at=changed, workspace_id=facts['workspace_id'], agent_id=facts['agent_id'] or None,
        category='action_required' if actionable else 'watch', severity='info', priority=20 if actionable else 10,
        resolution=resolution, allowed_actions=['inspect_approval'] + (['decide_approval'] if actionable else []),
        freshness=freshness,
        next_change_at=deadline if pending and deadline is not None and instant(deadline) > instant(now) else None)]
