"""Read retained progress for one reviewed Claude interruption and resend."""

import hashlib
import json

from ....domain.session_interaction import ClaudeSteerReceipt
from .session_interaction import _scope_params

_REPLACEMENT = {
    'replacement_submitted': 'submitted',
    'replacement_not_sent': 'not_sent',
    'replacement_write_unknown': 'write_unknown',
}


def read_claude_steer_receipt(uow, *, scope, operation_id) -> ClaudeSteerReceipt | None:
    rows = uow.connection.execute("""
        SELECT p.target_operation_id, e.payload_json, e.event_hash
        FROM session_interaction_claude_steer_targets p
        JOIN session_interaction_controls c USING(server_id,executor_id,operation_id)
        JOIN execution_event_watermarks w ON w.server_id=c.server_id AND w.executor_id=c.executor_id
          AND w.session_id=c.session_id AND w.stream_epoch=p.target_stream_epoch
        JOIN execution_event_ingress e ON e.server_id=w.server_id AND e.executor_id=w.executor_id
          AND e.session_id=w.session_id AND e.stream_epoch=w.stream_epoch
          AND e.sequence<=w.committed_contiguous
        WHERE c.server_id=:server_id AND c.executor_id=:executor_id AND c.session_id=:session_id
          AND c.operation_id=:operation_id AND c.owner_generation=:owner_generation
          AND c.confirmed_effect_revision IS NOT NULL AND c.target_ref=p.target_operation_id
          AND e.event_type='tool_activity' AND json_extract(e.payload_json,'$.native_type')='nexus_claude_steer'
          AND json_extract(e.payload_json,'$.operation_id')=c.operation_id
        ORDER BY e.sequence LIMIT 4
    """, _scope_params(scope) | {'operation_id': operation_id}).fetchall()
    stages = []
    request_id = None
    for row in rows:
        raw = row['payload_json']
        if 'sha256:' + hashlib.sha256(raw.encode()).hexdigest() != row['event_hash']:
            return None
        payload = json.loads(raw).get('payload')
        if not isinstance(payload, dict) or payload.get('turn_operation_id') != row['target_operation_id']:
            return None
        observed_request = payload.get('interrupt_request_id')
        if not isinstance(observed_request, str) or not observed_request:
            return None
        if request_id is not None and observed_request != request_id:
            return None
        request_id = observed_request
        stage = payload.get('stage')
        if not isinstance(stage, str):
            return None
        stages.append(stage)
    match stages:
        case ['interrupt_submitted']:
            return ClaudeSteerReceipt('submitted', 'pending')
        case ['interrupt_submitted', 'replacement_not_sent']:
            return ClaudeSteerReceipt('submitted', 'not_sent')
        case ['interrupt_write_unknown']:
            return ClaudeSteerReceipt('write_unknown', 'pending')
        case ['interrupt_write_unknown', 'replacement_not_sent']:
            return ClaudeSteerReceipt('write_unknown', 'not_sent')
        case ['interrupt_submitted', 'interrupt_confirmed']:
            return ClaudeSteerReceipt('confirmed', 'pending')
        case ['interrupt_submitted', 'interrupt_confirmed', replacement] if replacement in _REPLACEMENT:
            return ClaudeSteerReceipt('confirmed', _REPLACEMENT[replacement])
        case _:
            return None
