"""Project private Pi boundary facts onto an exact operator control."""

import hashlib
import json

from ....domain.session_interaction import PiSteerBoundary
from .session_interaction import _scope_params


def read_pi_steer_boundary(uow, *, scope, operation_id) -> PiSteerBoundary | None:
    proof = uow.connection.execute("""
        SELECT c.target_ref, p.target_operation_id, p.target_stream_epoch,
               w.committed_contiguous, w.gap_state
        FROM session_interaction_pi_steer_targets p
        JOIN session_interaction_controls c USING(server_id,executor_id,operation_id)
        JOIN execution_event_watermarks w ON w.server_id=c.server_id AND w.executor_id=c.executor_id
          AND w.session_id=c.session_id AND w.stream_epoch=p.target_stream_epoch
        WHERE c.server_id=:server_id AND c.executor_id=:executor_id AND c.session_id=:session_id
          AND c.operation_id=:operation_id AND c.owner_generation=:owner_generation
          AND c.confirmed_effect_revision IS NOT NULL
    """, _scope_params(scope) | {'operation_id': operation_id}).fetchone()
    if proof is None:
        return None
    params = _scope_params(scope) | dict(proof) | {'operation_id': operation_id}
    facts = uow.connection.execute("""
        SELECT payload_json,event_hash FROM execution_event_ingress
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
          AND stream_epoch=:target_stream_epoch AND sequence<=:committed_contiguous
          AND event_type='tool_activity' AND json_extract(payload_json,'$.native_type')='nexus_pi_steer'
          AND json_extract(payload_json,'$.operation_id')=:operation_id
        ORDER BY sequence LIMIT 3
    """, params).fetchall()
    stages = []
    for fact in facts:
        raw = fact['payload_json']
        if 'sha256:' + hashlib.sha256(raw.encode()).hexdigest() != fact['event_hash']:
            return None
        payload = json.loads(raw)['payload']
        if (payload.get('run_id'), payload.get('turn_operation_id')) != (
                proof['target_ref'], proof['target_operation_id']):
            return None
        stages.append(payload.get('stage'))
    if stages == ['queued', 'consumed']:
        return 'applied'
    if stages == ['queued', 'discarded']:
        return 'discarded'
    if stages != ['queued'] or proof['gap_state'] != 'none':
        return None
    finished = uow.connection.execute("""
        SELECT 1 FROM execution_event_ingress
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
          AND stream_epoch=:target_stream_epoch AND sequence<=:committed_contiguous
          AND event_type='turn_state' AND json_extract(payload_json,'$.operation_id')=:target_operation_id
          AND json_extract(payload_json,'$.payload.delivery_phase')='terminal'
        LIMIT 1
    """, params).fetchone()
    return 'awaiting_boundary' if finished is None else None
