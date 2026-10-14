"""Local cancellation after the admission repository records exact host proof."""
import time

from ....errors import ErrorCode, OktoNexusError


class SqliteCapacityCompensation:
    def __init__(self, *, cancellations, pool_factory):
        self.cancellations, self.pool_factory = cancellations, pool_factory

    def cancel(self, uow, admission):
        conn, identity = uow.connection, admission.operation_id
        row = conn.execute('SELECT d.* FROM delivery_outbox d JOIN execution_capacity_compensations c '
            'ON c.domain_operation_id=d.operation_id WHERE d.operation_id=?', (identity,)).fetchone()
        if (row is None or row['status'] not in {'PENDING', 'CLAIMED', 'ACCEPTED'} or row['ack_level'] != 'NONE'
                or any(row[k] is not None for k in ('reconciliation_id', 'terminal_event_id',
                    'canonical_terminal_operation_id', 'native_thread_id', 'native_turn_id', 'external_completed_at'))):
            raise OktoNexusError(ErrorCode.CONFLICT, 'Admission crossed its no-effect boundary.', {})
        refs = conn.execute('SELECT p.operation_id,p.action,p.intent_hash,p.server_id,p.executor_id,p.session_id '
            'FROM execution_domain_deliveries m JOIN execution_operations p USING(server_id,executor_id,operation_id) '
            'WHERE m.domain_operation_id=?', (identity,)).fetchall()
        consumption, scope = admission.consumption, admission.reservation.request.scope
        expected = {consumption.turn_operation_id: ('turn.submit', consumption.turn_intent_hash)}
        if consumption.opening_operation_id is not None:
            expected[consumption.opening_operation_id] = ('runtime.open', consumption.opening_intent_hash)
        if ({ref['operation_id']: (ref['action'], ref['intent_hash']) for ref in refs} != expected
                or len(refs) != len(expected) or any(tuple(ref[k] for k in ('server_id', 'executor_id', 'session_id'))
                    != (scope.server_id, scope.executor_id, scope.session_id) for ref in refs)):
            raise OktoNexusError(ErrorCode.CONFLICT, 'Capacity proof does not match the canonical operations.', {})
        self.cancellations.cancel(uow, identity, code='CAPACITY_NOT_CONSUMED')
        call = conn.execute('SELECT state,started_at,outcome_json FROM one_shot_calls WHERE call_id=?', (identity,)).fetchone()
        if call:
            if call['state'] not in {'QUEUED', 'ADMITTED'} or call['started_at'] is not None or call['outcome_json'] is not None:
                raise OktoNexusError(ErrorCode.CONFLICT, 'One-shot admission may have started.', {})
            self.pool_factory(conn).fail(request_id=identity, code='CAPACITY_NOT_CONSUMED', stage='dispatch',
                message='The reserved execution was not consumed.', now=time.time(), cancelled=True)
        conn.execute("UPDATE delivery_outbox SET status='CANCELLED',reason='capacity_not_consumed',"
            "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE operation_id=?", (identity,))
        # Keep this internal envelope's push ownership as history. Reopening
        # must not expose the cancelled instruction to an MCP inbox, or invent
        # an acknowledgement. The original broadcast notice remains separate.
