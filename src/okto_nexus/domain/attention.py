"""Versioned attention metadata; never a source of execution authority."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json

from ..errors import ErrorCode, OktoNexusError

VERSION = 1
KINDS = frozenset({
    'native_permission_pending', 'native_question_pending', 'question_waiting_for_agent',
    'verification_pending', 'execution_outcome_unknown', 'delivery_parked',
    'runtime_recovery_attention', 'execution_authority_blocking',
    'executor_disconnected_with_work', 'handoff_unclaimed_aged', 'result_unseen',
    'cleanup_attention', 'approval_pending',
    'external_blocked', 'external_completion_unseen', 'external_observation_stale',
})
CATEGORIES = frozenset({'action_required', 'watch'})
SEVERITIES = frozenset({'info', 'warning', 'error'})
PRIORITIES = frozenset({10, 20, 30})
RESOLUTIONS = frozenset({'open', 'resolved', 'expired'})
FRESHNESS = frozenset({'current', 'stale', 'unavailable'})
ACTIONS = frozenset({
    'inspect_approval', 'respond_native', 'decide_native', 'inspect_handoff',
    'verify_handoff', 'inspect_operation', 'inspect_recovery', 'review_authority',
    'inspect_executor', 'inspect_result', 'inspect_cleanup', 'inspect_delivery', 'decide_approval',
    'inspect_external_observation',
})
FILTERS = frozenset({'workspace_id', 'agent_id', 'category', 'kind', 'state', 'priority', 'seen'})


def invalid(message):
    raise OktoNexusError(ErrorCode.VALIDATION_ERROR, message, {})


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def instant(value):
    if type(value) is not str or len(value) > 64:
        invalid('Use an ISO-8601 timestamp with an explicit timezone.')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        invalid('Use an ISO-8601 timestamp with an explicit timezone.')


def stamp(value):
    return instant(value).isoformat(timespec='microseconds')


def identity(value, *, optional=False):
    if optional and value is None:
        return None
    if type(value) is not str or not 1 <= len(value) <= 2048 or any(ord(c) < 32 for c in value):
        invalid('Attention references must be nonempty canonical identifiers.')
    return value


def occurrence(*, kind, source_type, source_id, episode, source_revision,
               first_detected_at, last_changed_at, agent_id=None, workspace_id=None,
               session_id=None, operation_id=None, message_id=None, result_id=None, executor_id=None,
               category='watch', severity='info',
               priority=10, resolution='open', allowed_actions=(), freshness='current',
               next_change_at=None, active=None, summary_code=None):
    """Build a secret-free reference from a canonical fact and durable episode.

    Callers supply material revisions, never the time of the current GET. Action
    names describe navigation to existing controls; commands revalidate authority.
    """
    if (kind not in KINDS or category not in CATEGORIES or severity not in SEVERITIES
            or type(priority) is not int or priority not in PRIORITIES
            or resolution not in RESOLUTIONS or freshness not in FRESHNESS
            or not isinstance(allowed_actions, (list, tuple))
            or any(type(action) is not str or action not in ACTIONS for action in allowed_actions)
            or active is not None and type(active) is not bool):
        invalid('Invalid attention occurrence metadata.')
    source_type, source_id = identity(source_type), identity(source_id)
    first, changed = stamp(first_detected_at), stamp(last_changed_at)
    if changed < first:
        invalid('An occurrence cannot change before its recorded beginning.')
    return dict(
        attention_id='att_' + digest([VERSION, kind, source_type, source_id, episode]),
        kind=kind, category=category, severity=severity, priority=priority,
        agent_id=identity(agent_id, optional=True), workspace_id=identity(workspace_id, optional=True),
        session_id=identity(session_id, optional=True), operation_id=identity(operation_id, optional=True),
        message_id=identity(message_id, optional=True), result_id=identity(result_id, optional=True),
        executor_id=identity(executor_id, optional=True),
        source_type=source_type, source_id=source_id,
        source_revision=digest([VERSION, source_revision]),
        first_detected_at=first, last_changed_at=changed, freshness=freshness,
        summary_code=identity(summary_code or kind), allowed_actions=list(dict.fromkeys(allowed_actions)),
        resolution=resolution, active=resolution == 'open' if active is None else active,
        next_change_at=stamp(next_change_at) if next_change_at is not None else None,
    )


def normalize_filters(value=None):
    if value is None:
        value = {}
    if type(value) is not dict or set(value) - FILTERS:
        invalid('Unknown attention filter.')
    result = {key: item for key, item in value.items() if item is not None}
    result.setdefault('state', 'active')
    result.setdefault('seen', 'all')
    for key in ('workspace_id', 'agent_id'):
        if key in result:
            identity(result[key])
    choices = dict(category=CATEGORIES, kind=KINDS, state=RESOLUTIONS | {'active', 'all'},
                   seen={'all', 'seen', 'unseen', 'snoozed'})
    for key, allowed in choices.items():
        if key in result and (type(result[key]) is not str or result[key] not in allowed):
            invalid('Invalid attention ' + key + ' filter.')
    if 'priority' in result:
        if type(result['priority']) is not int or result['priority'] not in PRIORITIES:
            invalid('Attention priority must be 10, 20 or 30.')
    return result


def with_preferences(item, *, seen_at=None, snoozed_until=None, revision=0, now):
    """Viewing preferences do not change a canonical resolution or action."""
    result = dict(item)
    seen = seen_at is not None
    snoozed = snoozed_until is not None and instant(snoozed_until) > instant(now)
    result['seen_state'] = dict(seen=seen, seen_at=seen_at, snoozed=snoozed,
                                snoozed_until=snoozed_until, revision=revision)
    # Seeing a result ends its notification, never the work or its resolution.
    result['active'] = item['active'] and not snoozed and not (
        item['kind'] in {'result_unseen', 'external_completion_unseen'} and seen)
    if snoozed:
        result['next_change_at'] = min(filter(None, (result.get('next_change_at'), stamp(snoozed_until))))
    return result


def encode_cursor(*, filters, snapshot_revision, item):
    value = dict(version=VERSION, principal='operator', filters=filters,
                 snapshot_revision=snapshot_revision,
                 after=[item['priority'], item['first_detected_at'], item['attention_id']])
    return base64.urlsafe_b64encode(canonical(value).encode()).decode().rstrip('=')


def decode_cursor(value, *, filters):
    try:
        if type(value) is not str or not 1 <= len(value) <= 8192:
            raise ValueError
        raw = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
        item = json.loads(raw)
        if (type(item) is not dict or set(item) != {'version', 'principal', 'filters', 'snapshot_revision', 'after'}
                or type(item['version']) is not int or item['version'] != VERSION
                or item['principal'] != 'operator' or item['filters'] != filters
                or type(item['snapshot_revision']) is not str or len(item['snapshot_revision']) != 64
                or type(item['after']) is not list or len(item['after']) != 3
                or type(item['after'][0]) is not int or item['after'][0] not in PRIORITIES
                or stamp(item['after'][1]) != item['after'][1]
                or type(item['after'][2]) is not str or len(item['after'][2]) != 68
                or not item['after'][2].startswith('att_')):
            raise ValueError
        int(item['snapshot_revision'], 16)
        int(item['after'][2][4:], 16)
        return item
    except (ValueError, TypeError, KeyError, UnicodeError, OktoNexusError):
        raise OktoNexusError(ErrorCode.CONFLICT, 'The attention cursor does not match this view. Refresh the snapshot.',
                             {'reason': 'ATTENTION_CURSOR_INVALID'}) from None
