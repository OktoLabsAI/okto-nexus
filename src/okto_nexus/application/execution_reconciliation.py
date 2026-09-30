"""Connection-owned reconciliation pages; readiness follows durable facts."""
import secrets
import hashlib

from nexus_connector_core import CoreError, R4_PREVIEW_REVISION, decode_r4_frame, r4_resource_release_digest


def _receipt(row):
    if row is None or not row['canonical_frame']:
        return None
    raw = row['canonical_frame'].encode('utf-8')
    if 'sha256:' + hashlib.sha256(raw).hexdigest() != row['frame_digest']:
        return None
    try:
        frame = decode_r4_frame(raw)
    except (CoreError, ValueError):
        return None
    if frame['type'] != 'operation.receipt' or any(frame[k] != row[k] for k in (
            'server_id','executor_id','operation_id','intent_hash','receipt_revision','stage')):
        return None
    return frame


class ExecutionReconciliation:
    def __init__(self, factory, channel):
        self.factory, self.channel = factory, channel
        self._reset()

    def _reset(self):
        self.reconcile_id = 'rec_' + secrets.token_hex(16)
        self.cursor = None
        self.op_after = self.session_after = 0
        self.op_high = self.session_high = None
        self.blocked = False
        self.pending = None
        self.pages = 0

    def _owner(self, conn):
        c = self.channel
        if conn.execute("SELECT 1 FROM execution_executors WHERE server_id=? AND executor_id=? "
            "AND owner_instance_id=? AND generation=? AND control_state='RECOVERING' AND revoked_at IS NULL",
            (c.server_id, c.executor_id, c.connection_id, c.connection_generation)).fetchone() is None:
            raise ValueError('The reconciliation owner is no longer current.')

    def request(self):
        if self.pending is not None:
            return self.pending
        if self.pages >= 128:
            raise ValueError('The reconciliation page budget is exhausted.')
        c = self.channel
        with self.factory.unit_of_work(write=False) as uow:
            conn = uow.connection
            self._owner(conn)
            if self.op_high is None:
                self.receipt_high = conn.execute('SELECT coalesce(max(rowid),0) FROM execution_receipts '
                    'WHERE server_id=? AND executor_id=?', (c.server_id,c.executor_id)).fetchone()[0]
                self.op_high = conn.execute('SELECT coalesce(max(rowid),0) FROM execution_operations '
                    'WHERE server_id=? AND executor_id=?', (c.server_id, c.executor_id)).fetchone()[0]
                self.session_high = conn.execute('SELECT coalesce(max(rowid),0) FROM execution_sessions '
                    'WHERE server_id=? AND executor_id=?', (c.server_id, c.executor_id)).fetchone()[0]
            operations = conn.execute("SELECT rowid,operation_id FROM execution_operations WHERE server_id=? "
                "AND executor_id=? AND rowid>? AND rowid<=? AND admission_state<>'RESOLVED_TERMINAL' "
                "ORDER BY rowid LIMIT 256", (c.server_id,c.executor_id,self.op_after,self.op_high)).fetchall()
            sessions = conn.execute("SELECT rowid,session_id FROM execution_sessions WHERE server_id=? "
                "AND executor_id=? AND rowid>? AND rowid<=? AND lifecycle_state NOT IN ('CLOSED','FAILED') "
                "ORDER BY rowid LIMIT 256", (c.server_id,c.executor_id,self.session_after,self.session_high)).fetchall()
        self.next_op = operations[-1][0] if operations else self.op_high
        self.next_session = sessions[-1][0] if sessions else self.session_high
        self.pending = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION,
            type='reconcile.request', reconcile_id=self.reconcile_id, cursor=self.cursor,
            server_id=c.server_id, executor_id=c.executor_id, connection_id=c.connection_id,
            connection_generation=c.connection_generation, operation_ids=[r[1] for r in operations],
            session_ids=[r[1] for r in sessions], stream_watermarks=[])
        return self.pending

    def accept(self, report):
        request = self.pending
        if request is None or any(report[k] != request[k] for k in (
                'server_id','executor_id','connection_id','connection_generation','reconcile_id','cursor')):
            raise ValueError('The reconciliation response is stale.')
        if report['complete'] != (report['next_cursor'] is None) or (
                report['next_cursor'] is not None and report['next_cursor'] == self.cursor):
            raise ValueError('The reconciliation cursor did not advance.')
        c = self.channel
        ready = False
        with self.factory.unit_of_work() as uow:
            conn = uow.connection
            self._owner(conn)
            submitted = {r['operation_id']: r for r in report['receipts']}
            if len(submitted) != len(report['receipts']) or not set(submitted).issubset(request['operation_ids']):
                raise ValueError('The reconciliation receipts do not match this page.')
            if set(submitted) != set(request['operation_ids']):
                self.blocked = True
            for operation_id, summary in submitted.items():
                receipt = _receipt(conn.execute('SELECT * FROM execution_receipts '
                    'WHERE server_id=? AND executor_id=? AND operation_id=? ORDER BY receipt_revision DESC LIMIT 1',
                    (c.server_id,c.executor_id,operation_id)).fetchone())
                if receipt is None or any(receipt[k] != summary[k] for k in ('intent_hash','receipt_revision','stage')):
                    self.blocked = True
                if summary['stage'] not in ('SUBMITTED','SUCCEEDED','FAILED','CANCELLED'):
                    self.blocked = True
            facts = {r['session_id']: r for r in report['ownership_facts']}
            claims = {r['session_id']: r for r in report['claims']}
            if len(facts) != len(report['ownership_facts']) or len(claims) != len(report['claims']) or set(facts) != set(claims):
                raise ValueError('The ownership facts do not match the claims.')
            for session_id, claim in claims.items():
                fact = facts[session_id]
                session = conn.execute('SELECT owner_generation FROM execution_sessions WHERE '
                    'server_id=? AND executor_id=? AND session_id=?', (c.server_id,c.executor_id,session_id)).fetchone()
                if session is None or fact['owner_generation'] != claim['owner_generation']:
                    raise ValueError('The claim has no matching canonical session.')
                if (claim['state'] != 'RELEASED' or fact['process_state'] != 'EXITED' or
                        fact.get('proof_digest') is None or session['owner_generation'] != claim['owner_generation']):
                    self.blocked = True
                    continue
                closed = conn.execute("SELECT r.* FROM execution_operations o "
                    "JOIN execution_receipts r ON r.server_id=o.server_id AND r.executor_id=o.executor_id "
                    "AND r.operation_id=o.operation_id WHERE o.server_id=? AND o.executor_id=? "
                    "AND o.session_id=? AND o.action='runtime.close' AND r.stage='SUCCEEDED' "
                    "AND r.intent_hash=o.intent_hash "
                    "AND json_extract(o.expected_revisions_json,'$.session_owner_generation')=? LIMIT 1",
                    (c.server_id,c.executor_id,session_id,claim['owner_generation'])).fetchone()
                closed = _receipt(closed)
                if closed is None or closed['session_id'] != session_id:
                    # A released managed resource can be reconciled after
                    # lease containment without inventing a close operation.
                    opening = conn.execute(
                        "SELECT r.* FROM execution_sessions s JOIN execution_operations o "
                        "ON o.server_id=s.server_id AND o.executor_id=s.executor_id "
                        "AND o.operation_id=s.open_operation_id JOIN execution_receipts r "
                        "ON r.server_id=o.server_id AND r.executor_id=o.executor_id AND r.operation_id=o.operation_id "
                        "WHERE s.server_id=? AND s.executor_id=? AND s.session_id=? "
                        "AND o.action='runtime.open' AND o.session_id=s.session_id AND r.intent_hash=o.intent_hash "
                        "AND json_extract(o.expected_revisions_json,'$.session_owner_generation')=? "
                        "ORDER BY r.receipt_revision DESC LIMIT 1",
                        (c.server_id,c.executor_id,session_id,claim['owner_generation'])).fetchone()
                    opening = _receipt(opening)
                    if (opening is None or opening['session_id'] != session_id or
                            opening['stage'] not in ('SUBMITTED','SUCCEEDED') or
                            fact['proof_digest'] != r4_resource_release_digest(
                                server_id=c.server_id,executor_id=c.executor_id,session_id=session_id,
                                opening_operation_id=opening['operation_id'],opening_intent_hash=opening['intent_hash'],
                                owner_generation=claim['owner_generation'])):
                        self.blocked = True
                        continue
                conn.execute("UPDATE execution_sessions SET lifecycle_state='CLOSED',lease_state='CLOSED' "
                    "WHERE server_id=? AND executor_id=? AND session_id=? AND owner_generation=?",
                    (c.server_id,c.executor_id,session_id,claim['owner_generation']))
            streams = set()
            for watermark in report['stream_watermarks']:
                stream = (watermark['session_id'], watermark['stream_epoch'])
                if stream in streams or watermark['session_id'] not in claims:
                    raise ValueError('The stream watermark has no matching claim.')
                streams.add(stream)
                persisted = conn.execute("SELECT committed_contiguous,gap_state FROM execution_event_watermarks "
                    "WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?",
                    (c.server_id,c.executor_id,*stream)).fetchone()
                epoch = conn.execute("SELECT stream_epoch FROM execution_sessions WHERE server_id=? AND executor_id=? AND session_id=?",
                    (c.server_id,c.executor_id,watermark['session_id'])).fetchone()[0]
                committed = persisted['committed_contiguous'] if persisted is not None else 0
                self.blocked |= (watermark['sequence'] != committed or
                    epoch not in (None,watermark['stream_epoch']) or
                    (committed>0 and epoch!=watermark['stream_epoch']) or
                    (persisted is not None and persisted['gap_state'] != 'none'))
            if any(claim['state'] == 'RELEASED' and sum(s[0] == session for s in streams) != 1
                   for session, claim in claims.items()):
                self.blocked = True
            if report['complete']:
                self.blocked |= self.receipt_high != conn.execute(
                    'SELECT coalesce(max(rowid),0) FROM execution_receipts WHERE server_id=? AND executor_id=?',
                    (c.server_id,c.executor_id)).fetchone()[0]
                unscanned = conn.execute("SELECT 1 FROM execution_operations WHERE server_id=? AND executor_id=? "
                    "AND rowid>? AND admission_state<>'RESOLVED_TERMINAL' LIMIT 1",
                    (c.server_id,c.executor_id,self.next_op)).fetchone()
                active = conn.execute("SELECT 1 FROM execution_sessions WHERE server_id=? AND executor_id=? "
                    "AND lifecycle_state NOT IN ('CLOSED','FAILED') LIMIT 1", (c.server_id,c.executor_id)).fetchone()
                if not self.blocked and not unscanned and not active:
                    ready = conn.execute("UPDATE execution_executors SET control_state='CONTROL_READY' "
                        "WHERE server_id=? AND executor_id=? AND owner_instance_id=? AND generation=? "
                        "AND control_state='RECOVERING' AND revoked_at IS NULL",
                        (c.server_id,c.executor_id,c.connection_id,c.connection_generation)).rowcount == 1
        response = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, type='reconcile.accepted',
            server_id=c.server_id, executor_id=c.executor_id, connection_id=c.connection_id,
            connection_generation=c.connection_generation, reconcile_id=self.reconcile_id,
            recovery_remaining=not ready, ready_lane_ids=[], session_lease_requirements=[])
        self.pending = None
        self.op_after, self.session_after = self.next_op, self.next_session
        self.cursor = report['next_cursor']
        self.pages += 1
        if report['complete'] and not ready:
            self._reset()
        return response
