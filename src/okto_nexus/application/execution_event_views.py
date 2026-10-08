"""Authorized, bounded replay of committed canonical events, without a runtime."""
import hashlib
import json

from ..errors import ErrorCode, OktoNexusError
from .execution_session_views import read_execution_session

PAGE_BYTES = 512 * 1024


def read_execution_events(factory, *, server_id, session_id, context, access,
                          executor_id=None, stream_epoch=None, after_sequence=0, limit=200):
    with factory.unit_of_work(write=False) as uow:
        view = read_execution_session(factory, server_id=server_id, session_id=session_id,
            context=context, access=access, executor_id=executor_id, _uow=uow)
        if (type(after_sequence) is not int or not 0 <= after_sequence <= 9007199254740991
                or type(limit) is not int or not 1 <= limit <= 1000
                or (stream_epoch is not None and (type(stream_epoch) is not str
                    or not 1 <= len(stream_epoch) <= 160 or not stream_epoch.isprintable()))):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid canonical event replay cursor or limit.', {})
        scope = view['scope']
        key = (server_id, scope['executor_id'], session_id)
        if stream_epoch is None:
            stream_epoch = uow.connection.execute('SELECT stream_epoch FROM execution_sessions '
                'WHERE server_id=? AND executor_id=? AND session_id=?', key).fetchone()[0]
        watermark = uow.connection.execute('SELECT committed_contiguous,gap_state FROM execution_event_watermarks '
            'WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?', (*key, stream_epoch)).fetchone()
        if stream_epoch is not None and watermark is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'The event stream was not found in this session.', {})
        committed = watermark['committed_contiguous'] if watermark else 0
        rows = uow.connection.execute('SELECT sequence,event_hash,payload_json,received_at FROM execution_event_ingress '
            'WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=? '
            'AND sequence>? AND sequence<=? ORDER BY sequence LIMIT ?',
            (*key, stream_epoch, after_sequence, committed, limit + 1)).fetchall()
        events, used = [], 0
        if not rows and after_sequence < committed:
            raise OktoNexusError(ErrorCode.DB_ERROR, 'Committed canonical events are missing.', {})
        for row in rows[:limit]:
            raw = row['payload_json'].encode('utf-8')
            try:
                if len(raw) > 64 * 1024 or 'sha256:' + hashlib.sha256(raw).hexdigest() != row['event_hash']:
                    raise ValueError('Invalid event integrity')
                event = json.loads(raw)
                if tuple(event[k] for k in ('server_id', 'executor_id', 'session_id', 'stream_epoch', 'sequence')) != (*key, stream_epoch, row['sequence']):
                    raise ValueError('Invalid event scope')
                if row['sequence'] != after_sequence + len(events) + 1:
                    raise ValueError('Missing committed event')
            except (ValueError, TypeError, KeyError) as exc:
                raise OktoNexusError(ErrorCode.DB_ERROR, 'Stored canonical event integrity is invalid.', {}) from exc
            if used + len(raw) > PAGE_BYTES:
                break
            # Ingress retains the exact proposal for native reply validation.
            # Public history must expose only the Core's scrubbed presentation;
            # verify stored integrity above before constructing this view.
            payload = dict(event.get('payload', {}))
            if 'native_approval' in payload:
                payload.pop('native_approval')
                display = payload.get('native_approval_display')
                if isinstance(display, dict):
                    payload['native_approval'] = display
            event = {**event, 'payload': payload}
            events.append({**event, 'received_at': row['received_at']})
            used += len(raw)
        return dict(scope=scope, stream_epoch=stream_epoch, events=events, count=len(events),
            next_after_sequence=events[-1]['sequence'] if events else after_sequence,
            committed_contiguous=committed, gap_pending=bool(watermark and watermark['gap_state'] != 'none'),
            has_more=len(rows) > len(events))
