"""Read canonical release evidence and close only its exact SQLite session."""
import json

from nexus_connector_core import CoreError
from nexus_connector_core.session_release import session_receipts_digest

from ....application.execution_reconciliation import _receipt
from ....application.execution_session_release import SessionReleaseObservation


class SqliteSessionReleaseRepository:
    def _revision(self, uow, request, channel):
        key = channel.server_id, channel.executor_id, request['scope']['session_id']
        # Canonical receipts are append-only. The high water plus count also
        # catches deletion by maintenance; new dispatches without receipts are
        # separately fenced even when no event has arrived yet.
        receipts = uow.connection.execute('SELECT coalesce(max(r.rowid),0),count(*) FROM execution_receipts r '
            'JOIN execution_operations p USING(server_id,executor_id,operation_id) '
            'WHERE p.server_id=? AND p.executor_id=? AND p.session_id=?', key).fetchone()
        operations = uow.connection.execute('SELECT coalesce(max(p.rowid),0),count(*),'
            "sum(CASE WHEN d.dispatch_state IN ('SENDING','DISPATCHED','RECONCILING') "
            'AND NOT EXISTS (SELECT 1 FROM execution_receipts r WHERE r.server_id=p.server_id '
            'AND r.executor_id=p.executor_id AND r.operation_id=p.operation_id) THEN 1 ELSE 0 END) '
            'FROM execution_operations p LEFT JOIN execution_dispatch_outbox d USING(server_id,executor_id,operation_id) '
            'WHERE p.server_id=? AND p.executor_id=? AND p.session_id=?', key).fetchone()
        state = uow.connection.execute(
            'SELECT s.open_operation_id,s.owner_generation,s.lifecycle_state,s.lease_state,s.stream_epoch,'
            'e.owner_instance_id,e.generation,e.control_state,e.revoked_at,c.request_json,c.state,c.release_proof_json,'
            'p.intent_hash,p.expected_revisions_json,w.committed_contiguous,w.gap_state '
            'FROM execution_sessions s JOIN execution_executors e USING(server_id,executor_id) '
            'JOIN execution_session_containment c USING(server_id,executor_id,session_id) '
            'JOIN execution_operations p ON p.server_id=s.server_id AND p.executor_id=s.executor_id AND p.operation_id=s.open_operation_id '
            'LEFT JOIN execution_event_watermarks w ON w.server_id=s.server_id AND w.executor_id=s.executor_id '
            'AND w.session_id=s.session_id AND w.stream_epoch=? '
            'WHERE s.server_id=? AND s.executor_id=? AND s.session_id=? AND c.owner_generation=?',
            (request['stream_epoch'], *key, request['scope']['session_owner_generation'])).fetchone()
        return tuple(receipts) + tuple(operations) + tuple(state) if state is not None else ()

    def unchanged(self, uow, request, channel, revision):
        return bool(revision) and self._revision(uow, request, channel) == revision

    def observe(self, uow, request, channel):
        conn, scope = uow.connection, request['scope']
        key = channel.server_id, channel.executor_id, scope['session_id']
        row = conn.execute(
            'SELECT c.*,s.owner_generation AS current_owner,s.open_operation_id AS current_open,'
            's.lifecycle_state,s.lease_state,s.stream_epoch,p.intent_hash AS current_hash,p.expected_revisions_json '
            'FROM execution_session_containment c JOIN execution_sessions s USING(server_id,executor_id,session_id) '
            'JOIN execution_executors e USING(server_id,executor_id) '
            'JOIN execution_operations p ON p.server_id=s.server_id AND p.executor_id=s.executor_id '
            "AND p.operation_id=s.open_operation_id AND p.session_id=s.session_id AND p.action='runtime.open' "
            'WHERE c.server_id=? AND c.executor_id=? AND c.session_id=? AND c.owner_generation=? '
            "AND e.owner_instance_id=? AND e.generation=? AND e.control_state='CONTROL_READY' AND e.revoked_at IS NULL",
            (*key, scope['session_owner_generation'], channel.connection_id, channel.connection_generation)).fetchone()
        if (row is None or row['owner_generation'] != row['current_owner']
                or row['opening_operation_id'] != row['current_open'] or row['opening_intent_hash'] != row['current_hash']):
            return None
        previous = json.loads(row['release_proof_json']) if row['state'] == 'RELEASED' else None
        if previous is not None and (row['lifecycle_state'], row['lease_state']) != ('CLOSED', 'CLOSED'):
            return None
        # A cursor bounds memory even for long-lived shared session histories.
        opening = None
        def receipts():
            nonlocal opening
            cursor = conn.execute(
                'SELECT p.operation_id AS expected_operation,p.intent_hash AS expected_hash,r.* '
                'FROM execution_operations p LEFT JOIN execution_dispatch_outbox d USING(server_id,executor_id,operation_id) '
                'LEFT JOIN execution_receipts r ON r.rowid=(SELECT max(r2.rowid) FROM execution_receipts r2 '
                'WHERE r2.server_id=p.server_id AND r2.executor_id=p.executor_id AND r2.operation_id=p.operation_id '
                'AND r2.receipt_revision=(SELECT max(r3.receipt_revision) FROM execution_receipts r3 '
                'WHERE r3.server_id=p.server_id AND r3.executor_id=p.executor_id AND r3.operation_id=p.operation_id)) '
                'WHERE p.server_id=? AND p.executor_id=? AND p.session_id=? '
                "AND (r.operation_id IS NOT NULL OR d.dispatch_state IN ('SENDING','DISPATCHED','RECONCILING')) "
                'ORDER BY p.operation_id', key)
            for stored in cursor:
                receipt = _receipt(stored)
                if (receipt is None or receipt['operation_id'] != stored['expected_operation']
                        or receipt['intent_hash'] != stored['expected_hash']
                        or any(receipt[k] != scope[k] for k in ('server_id','executor_id','binding_id','agent_id','session_id'))):
                    raise CoreError('RECONCILIATION_REQUIRED', 'session_release_receipts')
                if receipt['operation_id'] == row['opening_operation_id']:
                    opening = receipt
                yield receipt
        try:
            count, digest = session_receipts_digest(receipts())
        except CoreError:
            return None
        watermark = conn.execute('SELECT committed_contiguous,gap_state FROM execution_event_watermarks '
            'WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?',
            (*key, request['stream_epoch'])).fetchone()
        return SessionReleaseObservation(json.loads(row['expected_revisions_json']), json.loads(row['request_json']),
            row['opening_operation_id'], row['opening_intent_hash'], row['owner_generation'], opening,
            count, digest, row['stream_epoch'], watermark['committed_contiguous'] if watermark else 0,
            watermark is not None and watermark['gap_state'] != 'none', previous,
            self._revision(uow, request, channel))

    def close(self, uow, request):
        scope = request['scope']
        changed = uow.connection.execute(
            "UPDATE execution_sessions SET lifecycle_state='CLOSED',lease_state='CLOSED' "
            'WHERE server_id=? AND executor_id=? AND session_id=? AND owner_generation=? AND open_operation_id=?',
            (scope['server_id'],scope['executor_id'],scope['session_id'],scope['session_owner_generation'],
             request['opening_operation_id']))
        if changed.rowcount != 1:
            raise ValueError('Session release owner changed.')
