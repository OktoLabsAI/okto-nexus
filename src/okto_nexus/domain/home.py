"""HOME v1 read DTOs and pure presentation. These references confer no authority."""
from __future__ import annotations

import base64
import json
from typing import Generic, Literal, NotRequired, TypedDict, TypeVar
from .home_delivery_semantics import DeliverySemantics

from ..errors import ErrorCode, OktoNexusError
from .attention import canonical, digest


class SourceRef(TypedDict):
    type: str
    id: str
    revision: str


class _TargetScope(TypedDict):
    server_id: str
    workspace_id: str | None


class HandoffTarget(_TargetScope):
    kind: Literal['handoff']
    handoff_id: str


class ExecutionTarget(_TargetScope):
    kind: Literal['execution', 'result']
    executor_id: str
    session_id: str
    operation_id: str


class SessionTarget(TypedDict):
    kind: Literal['session']
    server_id: str
    executor_id: str
    workspace_id: str
    session_id: str


class ConnectionTarget(TypedDict):
    kind: Literal['connection']
    server_id: str
    executor_id: str
    workspace_id: str
    binding_id: str
    agent_id: str


class MessageTarget(_TargetScope):
    kind: Literal['message']
    message_id: str


class ApprovalTarget(_TargetScope):
    kind: Literal['approval']
    approval_id: str


class ExternalTarget(_TargetScope):
    kind: Literal['external_observation']
    source_id: str
    observed_instance_id: str
    generation: int


HomeTarget = HandoffTarget | ExecutionTarget | SessionTarget | ConnectionTarget | MessageTarget | ApprovalTarget | ExternalTarget


class RuntimeRef(TypedDict):
    executor_id: str
    session_id: str
    operation_id: str


class HomeActivity(TypedDict):
    id: str
    kind: Literal['handoff', 'conversation_turn', 'direct_operation']
    source_ref: SourceRef
    workspace_id: str
    title: str
    title_origin: Literal['canonical_title', 'message_subject', 'fallback']
    agent_ids: list[str]
    display_state: str
    state_since: str | None
    last_activity_at: str | None
    evidence_status: Literal['confirmed', 'unknown']
    attention_refs: list[str]
    runtime_refs: list[RuntimeRef]
    detail_target: HomeTarget
    running_count: int
    attempt_count: int


class HomeResult(TypedDict):
    delivery_semantics: NotRequired[DeliverySemantics]
    id: str
    source_ref: SourceRef
    workspace_id: str
    agent_id: str | None
    title: str
    preview: str | None
    truncated: bool
    outcome: str
    verification_state: str | None
    cleanup_state: str | None
    created_at: str | None
    detail_target: HomeTarget
    artifacts: list[dict[str, str]]
    view_state: Literal['unseen', 'seen', 'not_tracked']
    attention: dict | None


T = TypeVar('T')


class HomeSection(TypedDict, Generic[T]):
    status: Literal['ready', 'partial', 'unavailable', 'disabled', 'forbidden']
    as_of: str | None
    next_refresh_at: str | None
    items: list[T]
    total: int | None
    total_is_exact: bool
    has_more: bool
    next_cursor: str | None
    reason_code: NotRequired[str]
    revision: NotRequired[str]


class HomeScope(TypedDict):
    workspace_id: str | None
    agent_id: NotRequired[str]
    state: NotRequired[str]


class HomeAgent(TypedDict):
    agent_id: str
    name: str
    workspace_ids: list[str]
    presence: str
    connectivity: str
    activity: Literal['not_reported']


class HomeCounter(TypedDict):
    value: int | None
    total_is_exact: bool
    label: str
    unit: Literal['activities', 'occurrences', 'results', 'external_instances']
    reason_code: NotRequired[str]


class HomeSummary(TypedDict):
    running: HomeCounter
    waiting_start: HomeCounter
    needs_you: HomeCounter
    results: HomeCounter
    external: HomeCounter


class HomePage(HomeSection[T], Generic[T]):
    version: Literal[1]
    scope: HomeScope
    server_id: str
    generated_at: str
    snapshot_id: str


class HomeOverview(TypedDict):
    version: Literal[1]
    scope: HomeScope
    server_id: str
    generated_at: str
    snapshot_id: str
    event_cursor: int
    event_low_watermark: int | None
    summary: HomeSummary
    work: HomeSection[HomeActivity]
    results: HomeSection[HomeResult]
    agents: HomeSection[HomeAgent]
    attention: HomeSection[dict]
    server_attention: HomeSection[dict]
    external_activity: HomeSection[dict]


STATES = frozenset({'all', 'running', 'awaiting_owner', 'claimed', 'queued', 'native_accepted',
    'awaiting_dependency', 'awaiting_operator', 'awaiting_agent', 'awaiting_verification',
    'outcome_unknown', 'completed', 'turn_completed', 'result_available_cleanup_pending', 'failed', 'cancelled'})
TARGET_FIELDS = {
    'handoff': {'handoff_id'}, 'execution': {'executor_id', 'session_id', 'operation_id'},
    'result': {'executor_id', 'session_id', 'operation_id'}, 'message': {'message_id'},
    'approval': {'approval_id'}, 'external_observation': {'source_id', 'observed_instance_id', 'generation'},
    'session': {'executor_id', 'session_id'}, 'connection': {'executor_id', 'binding_id', 'agent_id'},
}


def invalid(message='Invalid Home read parameters.'):
    raise OktoNexusError(ErrorCode.VALIDATION_ERROR, message, {})


def identity(value):
    if type(value) is not str or not 1 <= len(value) <= 256 or any(ord(c) < 32 for c in value):
        invalid()
    return value


def filters(value=None):
    value = value or {}
    if type(value) is not dict or set(value) - {'workspace_id', 'agent_id', 'state'}:
        invalid()
    result = {'workspace_id': value.get('workspace_id')}
    for key in ('workspace_id', 'agent_id'):
        if value.get(key) is not None:
            result[key] = identity(value[key])
    if result['workspace_id'] == 'all':
        invalid('Omit workspace_id for all workspaces.')
    if value.get('state') is not None:
        if type(value['state']) is not str or value['state'] not in STATES:
            invalid()
        result['state'] = value['state']
    return result


def limit(value):
    if type(value) is not int or not 1 <= value <= 100:
        invalid('Home page size must be between 1 and 100.')
    return value


def target(value):
    if type(value) is not dict or type(value.get('kind')) is not str or value.get('kind') not in TARGET_FIELDS:
        invalid('Invalid Home target.')
    fields = TARGET_FIELDS[value['kind']] | {'kind', 'server_id', 'workspace_id'}
    if set(value) != fields:
        invalid('Home target requires exact canonical identifiers.')
    for key in fields - {'generation', 'workspace_id'}:
        identity(value[key])
    if value['workspace_id'] is not None:
        identity(value['workspace_id'])
    elif value['kind'] in ('session', 'connection'):
        invalid('Session and connection targets require their exact workspace.')
    if 'generation' in value and (type(value['generation']) is not int or value['generation'] < 1):
        invalid()
    return value


def encode_cursor(section, scope, revision, key):
    raw = canonical(dict(v=1, section=section, scope=scope, revision=revision, key=key)).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def decode_cursor(value, section, scope):
    if value is None:
        return None
    try:
        if type(value) is not str or len(value) > 4096:
            raise ValueError
        raw = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
        result = json.loads(raw)
        if (set(result) != {'v', 'section', 'scope', 'revision', 'key'} or result['v'] != 1
                or result['section'] != section or result['scope'] != scope
                or type(result['revision']) is not str or type(result['key']) is not list
                or len(result['key']) != 2 or any(type(v) is not str for v in result['key'])):
            raise ValueError
        return result
    except (ValueError, TypeError, KeyError, UnicodeError):
        invalid('Home cursor does not match this scope or section.')


def activity(f, server_id) -> HomeActivity:
    """Only latest receipts of the current claim contribute productive facts."""
    state = 'outcome_unknown'
    since = None
    if f['kind'] == 'handoff' and f['status'] in ('COMPLETED', 'REJECTED', 'CANCELLED'):
        state = {'COMPLETED': 'completed', 'REJECTED': 'failed', 'CANCELLED': 'cancelled'}[f['status']]
        since = f.get('changed')
    elif f.get('blocked'):
        state = 'awaiting_dependency'
    elif f['status'] == 'VERIFYING':
        state, since = 'awaiting_verification', f.get('changed')
    elif f['kind'] == 'handoff' and f['status'] == 'OPEN':
        state, since = 'awaiting_owner', f.get('changed')
    elif f.get('claim_expired') and f.get('stage') not in ('SUCCEEDED','FAILED','CANCELLED'):
        state = 'outcome_unknown'
    elif f.get('running'):
        state, since = 'running', f.get('running_since')
    elif f.get('stage') == 'SUCCEEDED':
        state = 'result_available_cleanup_pending' if f.get('cleanup') else 'turn_completed'
        since = f.get('receipt_at')
    elif f.get('stage') in ('FAILED', 'CANCELLED'):
        state, since = ('failed' if f['stage'] == 'FAILED' else 'cancelled'), f.get('receipt_at')
    elif f.get('stage') in ('ACCEPTED', 'SUBMITTED'):
        state, since = 'native_accepted', f.get('receipt_at')
    elif f['kind'] == 'handoff' and f['status'] in ('OPEN', 'CLAIMED'):
        state = 'awaiting_owner' if f['status'] == 'OPEN' else 'claimed'
        since = f.get('changed')
    elif f['kind'] == 'conversation_turn' and f['status'] in ('PENDING', 'CLAIMED', 'RETRY_WAIT'):
        state = 'queued'
    ref = dict(type=f['kind'], id=f['source_id'], revision=digest(f))
    if f['kind'] == 'handoff':
        detail = dict(kind='handoff', server_id=server_id, workspace_id=f['workspace_id'], handoff_id=f['source_id'])
    elif f['kind'] == 'conversation_turn':
        detail = dict(kind='message', server_id=server_id, workspace_id=f['workspace_id'], message_id=f['message_id'])
    else:
        detail = dict(kind='execution', server_id=server_id, workspace_id=f['workspace_id'],
            executor_id=f['executor_id'], session_id=f['session_id'], operation_id=f['source_id'])
    # No prompts, result bodies, or tool arguments enter these facts.
    title = f.get('title') or {'handoff': 'Handoff', 'conversation_turn': 'Conversation', 'direct_operation': 'Work request'}[f['kind']]
    identity = [1, server_id, f['kind'], f['source_id']]
    if f['kind'] == 'direct_operation':
        identity.extend([f['executor_id'], f['session_id']])
    return dict(id='home_' + digest(identity), kind=f['kind'], source_ref=ref,
        workspace_id=f['workspace_id'], title=title[:160], title_origin=f.get('title_origin') or 'fallback',
        agent_ids=sorted(set(v for v in f.get('agent_ids', []) if v)), display_state=state,
        state_since=since, last_activity_at=f.get('latest') or f.get('changed') or f.get('created'),
        evidence_status='unknown' if state == 'outcome_unknown' else 'confirmed', attention_refs=[],
        runtime_refs=f.get('runtime_refs', []), detail_target=detail,
        running_count=0 if f.get('claim_expired') or state in ('awaiting_owner','completed','failed','cancelled','awaiting_verification','awaiting_dependency') else int(f.get('running') or 0),
        attempt_count=int(f.get('attempt_count') or 0))
