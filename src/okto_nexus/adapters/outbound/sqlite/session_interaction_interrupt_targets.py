"""Read authenticated terminal evidence for an interrupt's retained target."""

import hashlib
import json


def interrupt_target_status(conn, exact, target):
    if target['target_operation_id'] is None:
        return 'unconfirmed'
    facts = conn.execute("""
        SELECT x.delivery_outcome, ingress.payload_json, ingress.event_hash, receipt.stage
        FROM execution_operations o
        JOIN execution_results x USING (server_id,executor_id,operation_id)
        JOIN execution_event_ingress ingress ON ingress.server_id=x.server_id AND ingress.executor_id=x.executor_id
          AND ingress.session_id=x.session_id AND ingress.stream_epoch=x.stream_epoch
          AND ingress.sequence=x.terminal_sequence
        JOIN execution_event_watermarks w ON w.server_id=x.server_id AND w.executor_id=x.executor_id
          AND w.session_id=x.session_id AND w.stream_epoch=x.stream_epoch
        JOIN execution_receipts receipt ON receipt.server_id=o.server_id AND receipt.executor_id=o.executor_id
          AND receipt.operation_id=o.operation_id AND receipt.receipt_revision=(
            SELECT MAX(r.receipt_revision) FROM execution_receipts r WHERE r.server_id=o.server_id
              AND r.executor_id=o.executor_id AND r.operation_id=o.operation_id)
        WHERE o.server_id=:server_id AND o.executor_id=:executor_id AND o.session_id=:session_id
          AND o.operation_id=:target_operation_id AND o.binding_id=:binding_id AND o.workspace_id=:workspace_id
          AND o.workspace_binding_id=:workspace_binding_id AND o.subject_agent_id=:agent_id AND o.action='turn.submit'
          AND json_extract(o.expected_revisions_json,'$.session_owner_generation')=:session_owner_generation
          AND x.session_id=:session_id AND x.stream_epoch=:target_stream_epoch
          AND w.committed_contiguous>=x.terminal_sequence AND ingress.event_type='turn_state'
    """, {**exact, 'target_operation_id': target['target_operation_id'],
           'target_stream_epoch': target['target_stream_epoch']}).fetchone()
    if facts is None:
        return 'unconfirmed'
    raw = facts['payload_json']
    if 'sha256:' + hashlib.sha256(raw.encode()).hexdigest() != facts['event_hash']:
        return 'unconfirmed'
    event = json.loads(raw)
    payload = event['payload']
    outcome = facts['delivery_outcome']
    terminal = {'interrupted': 'CANCELLED', 'failed': 'FAILED', 'success': 'SUCCEEDED'}
    if target['target_kind'] == 'current_run' and event.get('native_type') == 'agent_settled':
        reference = payload.get('hosted_pi_run_id')
    elif target['target_kind'] == 'native_turn_id':
        reference = payload.get('turn_id')
    else:
        return 'unconfirmed'
    if (event.get('operation_id') != target['target_operation_id'] or reference is None or reference != target['target_ref']
            or payload.get('delivery_phase') != 'terminal' or payload.get('delivery_outcome') != outcome
            or terminal.get(outcome) != facts['stage']):
        return 'unconfirmed'
    return 'interrupted' if outcome == 'interrupted' else 'finished'
