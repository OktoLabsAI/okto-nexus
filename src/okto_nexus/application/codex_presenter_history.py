"""Scoped Codex pages from the Server's committed, sanitized event history."""

import hashlib
import hmac
import secrets
from copy import deepcopy
from dataclasses import dataclass, field

from nexus_connector_core.protocol import canonical_json

from ..adapters.outbound.sqlite.session_interaction import _scope_params
from ..domain.presentation_protocol import MAX_PRESENTATION_NOTIFICATIONS
from ..errors import ErrorCode, OktoNexusError
from .codex_presenter_requests import CodexHistoryPage
from .execution_event_views import read_execution_events
from .execution_native_session_mapping import ManagedNativeSession
from .session_interaction_transcript import _bounded_body, _native_id

_MAX_CAPTURE_EVENTS = 512
_MAX_TEXT_PARTS = 8


@dataclass(frozen=True, slots=True)
class CodexHistorySnapshot:
    """One bounded event position. Cursors are valid only on this snapshot."""

    committed_through: int
    omitted_items: int
    _turns: tuple[dict, ...] = field(repr=False)
    _items: tuple[dict, ...] = field(repr=False)
    _cursor_key: bytes = field(default_factory=lambda: secrets.token_bytes(32), repr=False)

    @property
    def active_turn(self):
        active = [turn['id'] for turn in self._turns if turn['status'] == 'inProgress']
        if len(active) > 1:
            raise OktoNexusError(ErrorCode.CONFLICT, 'The active Codex turn is ambiguous.', {})
        return active[0] if active else None

    def page(self, request: CodexHistoryPage) -> dict:
        if request.turn_id is not None and not any(turn['id'] == request.turn_id for turn in self._turns):
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'The history turn is outside this presentation.', {})
        data = self._turns if request.kind == 'turns' else self._items
        if request.turn_id is not None:
            data = tuple(item for item in data if item['turnId'] == request.turn_id)
        if request.direction == 'desc':
            data = data[::-1]
        offset = self._offset(request)
        if offset and offset >= len(data):
            raise OktoNexusError(ErrorCode.CONFLICT, 'The presentation history cursor is unavailable.', {})
        end = min(offset + request.limit, len(data))
        if request.kind == 'turns':
            results = [{**turn, 'items': [], 'itemsView': 'notLoaded'} for turn in data[offset:end]]
        else:
            results = deepcopy(list(data[offset:end]))
        opposite = 'asc' if request.direction == 'desc' else 'desc'
        return {
            'data': results,
            'nextCursor': self._cursor(request, end, request.direction) if end < len(data) else None,
            'backwardsCursor': self._cursor(request, len(data) - end, opposite) if results else None,
        }

    def _cursor(self, request, offset, direction):
        payload = canonical_json([request.kind, request.turn_id, direction, request.items_view, offset])
        signature = hmac.new(self._cursor_key, payload, hashlib.sha256).hexdigest()
        return f'{offset}.{signature}'

    def _offset(self, request):
        if request.cursor is None:
            return 0
        offset, _, signature = request.cursor.partition('.')
        if (not offset.isascii() or not offset.isdecimal() or len(offset) > 3 or len(signature) != 64
                or not hmac.compare_digest(request.cursor, self._cursor(request, int(offset), request.direction))):
            raise OktoNexusError(ErrorCode.CONFLICT, 'The presentation history cursor is unavailable.', {})
        return int(offset)


def read_codex_history_snapshot(factory, *, mapping: ManagedNativeSession, context, access) -> CodexHistorySnapshot:
    """Capture one authorized, contiguous event range for an exact owner and stream."""
    page = _read_page(factory, mapping=mapping, context=context, access=access,
                      after_sequence=0, limit=_MAX_CAPTURE_EVENTS)
    if page['gap_pending'] or page['has_more'] or page['next_after_sequence'] != page['committed_contiguous']:
        raise OktoNexusError(ErrorCode.CONFLICT, 'A bounded complete history range is unavailable.', {})
    return _project(page['events'], mapping.codex_thread_id, page['committed_contiguous'])


def _read_page(factory, *, mapping, context, access, after_sequence, limit):
    if mapping.codex_thread_id is None or mapping.stream_epoch is None:
        raise OktoNexusError(ErrorCode.CONFLICT, 'The exact Codex history is unavailable.', {})
    scope = _scope_params(mapping.scope)
    scope['session_owner_generation'] = scope.pop('owner_generation')
    page = read_execution_events(factory, server_id=scope['server_id'], executor_id=scope['executor_id'],
        session_id=scope['session_id'], context=context, access=access, stream_epoch=mapping.stream_epoch,
        after_sequence=after_sequence, limit=limit, hydrate_artifacts=False)
    if page['stream_epoch'] != mapping.stream_epoch or any(
            page['scope'].get(field) != expected for field, expected in scope.items()):
        raise OktoNexusError(ErrorCode.NOT_FOUND, 'The history is outside this presentation.', {})
    return page


def read_codex_history_updates(factory, *, mapping, context, access, after_sequence, active_turn):
    """Continue a viewer's captured stream using only committed native facts."""
    page = _read_page(factory, mapping=mapping, context=context, access=access,
                      after_sequence=after_sequence, limit=MAX_PRESENTATION_NOTIFICATIONS)
    if page['gap_pending'] or page['committed_contiguous'] < after_sequence:
        raise OktoNexusError(ErrorCode.CONFLICT, 'The Codex presentation lost its history position.', {})
    notifications = []
    for event in page['events']:
        method, turn_id, value = _project_event(event, mapping.codex_thread_id)
        if method == 'turn/started':
            if active_turn == turn_id:
                continue
            if active_turn is not None:
                raise OktoNexusError(ErrorCode.CONFLICT, 'The active Codex turn changed without settling.', {})
            active_turn = turn_id
        elif method is None or turn_id != active_turn or value is None:
            continue
        elif method == 'turn/completed':
            active_turn = None
        params = {'threadId': mapping.codex_thread_id}
        if method == 'item/completed':
            params.update(turnId=turn_id, item=value)
        else:
            params['turn'] = {**value, 'items': [], 'itemsView': 'notLoaded', 'error': None}
        notifications.append({'method': method, 'params': params})
    return page['next_after_sequence'], active_turn, {'notifications': notifications, 'has_more': page['has_more']}


def _project(events, thread_id, committed_through):
    turns, items = {}, {}
    omitted = 0
    for event in events:
        method, turn_id, value = _project_event(event, thread_id)
        if (method == 'turn/started' and turn_id not in turns
                or method == 'turn/completed' and turn_id in turns):
            turns[turn_id] = value
        elif method == 'item/completed':
            if turn_id not in turns or value is None:
                omitted += 1
                continue
            items[turn_id, value['id']] = {'turnId': turn_id, 'item': value}
    return CodexHistorySnapshot(committed_through, omitted, tuple(turns.values()), tuple(items.values()))


def _project_event(event, thread_id):
    payload = event['payload']
    turn_id = payload.get('turnId') or payload.get('turn_id')
    if (payload.get('thread_id') != thread_id or payload.get('threadId') != thread_id
            or not _native_id(turn_id) or payload.get('turn_id', turn_id) != turn_id
            or payload.get('turnId', turn_id) != turn_id):
        return None, None, None
    method = event.get('native_type')
    category = event.get('category')
    if method in ('turn/started', 'turn/completed') and category == 'turn_state':
        turn = payload.get('turn')
        status = turn.get('status') if isinstance(turn, dict) and turn.get('id') == turn_id else None
        if (method == 'turn/started' and status == 'inProgress'
                or method == 'turn/completed' and status in ('completed', 'interrupted', 'failed')):
            return method, turn_id, {'id': turn_id, 'status': status}
    if method == 'item/completed' and category == 'tool_activity':
        return method, turn_id, _text_item(payload.get('item'))
    return None, None, None


def _text_item(item):
    if not isinstance(item, dict) or not _native_id(item.get('id')):
        return None
    kind = item.get('type')
    if kind == 'agentMessage':
        body = _clean(item.get('text'))
        return {'type': kind, 'id': item['id'], 'text': body} if body is not None else None
    if kind != 'userMessage':
        return None
    content = item.get('content')
    if not isinstance(content, list) or not 1 <= len(content) <= _MAX_TEXT_PARTS:
        return None
    parts = []
    for part in content:
        if not isinstance(part, dict) or part.get('type') != 'text':
            return None
        body = _clean(part.get('text'))
        if body is None:
            return None
        parts.append({'type': 'text', 'text': body, 'text_elements': []})
    return {'type': kind, 'id': item['id'], 'content': parts}


def _clean(value):
    if type(value) is not str:
        return None
    try:
        body, truncated = _bounded_body(value)
        return None if truncated else body
    except UnicodeEncodeError:
        return None
