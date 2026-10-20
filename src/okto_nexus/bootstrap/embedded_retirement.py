"""Retain verified local release across boots; never infer it from CLOSED."""
import json
from contextlib import nullcontext

from nexus_connector_core import CoreError


class EmbeddedRetirement:
    def __init__(self, owner):
        self.owner = owner

    def pending(self, agent_id, *, after=0, limit=128):
        if not 1 <= limit <= 128:
            raise ValueError('Retirement page size must be between 1 and 128')
        with self.owner.factory.unit_of_work(write=False) as uow:
            self.owner.verify(uow=uow)
            # Drive from unverified sessions, not an agent's entire stream history.
            return [dict(r) for r in uow.connection.execute(
                "SELECT s.rowid AS retirement_rowid,s.session_id,s.lifecycle_state,l.stream_epoch FROM execution_sessions s "
                "CROSS JOIN execution_operations o ON o.server_id=s.server_id AND o.executor_id=s.executor_id "
                "AND o.operation_id=s.open_operation_id "
                "LEFT JOIN execution_local_streams l USING(server_id,executor_id,session_id) "
                "WHERE s.server_id=? AND s.executor_id=? AND s.local_retirement_json IS NULL "
                "AND o.subject_agent_id=? AND s.lifecycle_state IN ('CLOSED','FAILED') AND s.rowid>? "
                "ORDER BY s.rowid LIMIT ?",
                (self.owner.channel.server_id, self.owner.channel.executor_id, agent_id, after, limit))]

    def invalidate(self, session_id):
        """A retained occupied Core slot overrides a previous Server checkpoint."""
        with self.owner.factory.unit_of_work() as uow:
            self.owner.verify(uow=uow)
            uow.connection.execute('UPDATE execution_sessions SET local_retirement_json=NULL, '
                'local_retirement_revision=local_retirement_revision+1 '
                'WHERE server_id=? AND executor_id=? AND session_id=?',
                (self.owner.channel.server_id, self.owner.channel.executor_id, session_id))

    def snapshot(self, session_id):
        """Capture publication revision after producers and final publication drain."""
        key = self.owner.channel.server_id, self.owner.channel.executor_id, session_id
        with self.owner.factory.unit_of_work(write=False) as uow:
            self.owner.verify(uow=uow)
            db = uow.connection
            if db.execute('SELECT 1 FROM execution_local_publications p '
                    'WHERE p.server_id=? AND p.executor_id=? AND p.session_id=? AND p.terminal=0 '
                    'AND NOT EXISTS (SELECT 1 FROM execution_receipts r WHERE r.server_id=p.server_id '
                    'AND r.executor_id=p.executor_id AND r.operation_id=p.operation_id) LIMIT 1', key).fetchone():
                return None
            return db.execute('SELECT local_retirement_revision FROM execution_sessions '
                'WHERE server_id=? AND executor_id=? AND session_id=?', key).fetchone()[0]

    def commit(self, session_id, proof, *, uow=None):
        """Called after exact Core release, final receipt publication and tool cleanup.

        The proof comes from EmbeddedReconciliation.release_session, not from
        client data. Recheck its exact generation and committed stream while
        retiring publication obligations and persisting the checkpoint atomically.
        """
        owner = self.owner
        key = owner.channel.server_id, owner.channel.executor_id, session_id
        with (owner.factory.unit_of_work() if uow is None else nullcontext(uow)) as uow:
            owner.verify(uow=uow)
            db = uow.connection
            session = db.execute('SELECT * FROM execution_sessions '
                'WHERE server_id=? AND executor_id=? AND session_id=?', key).fetchone()
            if (session is None or session['lifecycle_state'] not in ('CLOSED', 'FAILED')
                    or session['lease_state'] != 'CLOSED'
                    or proof['owner_generation'] != session['owner_generation']
                    or proof['opening_operation_id'] != session['open_operation_id']
                    or tuple(proof[k] for k in ('server_id', 'executor_id', 'session_id')) != key):
                raise CoreError('RECONCILIATION_REQUIRED', 'embedded_retirement_identity')
            if session['local_retirement_revision'] != proof['retirement_revision']:
                return False  # A new obligation won the race; the next pass republishes it.
            streams = db.execute('SELECT stream_epoch,opening_operation_id FROM execution_local_streams '
                'WHERE server_id=? AND executor_id=? AND session_id=?', key).fetchall()
            if (len(streams) != 1 or streams[0]['stream_epoch'] != proof['stream_epoch']
                    or streams[0]['opening_operation_id'] != proof['opening_operation_id']):
                raise CoreError('RECONCILIATION_REQUIRED', 'embedded_retirement_stream')
            watermark = db.execute('SELECT committed_contiguous,gap_state FROM execution_event_watermarks '
                'WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?',
                (*key, proof['stream_epoch'])).fetchone()
            if ((watermark is not None and watermark['gap_state'] != 'none')
                    or (watermark['committed_contiguous'] if watermark else 0) != proof['committed_sequence']):
                raise CoreError('EVENT_GAP', 'embedded_retirement_stream')
            checkpoint = dict(version=1, **proof)
            if session['local_retirement_json'] is not None:
                previous = json.loads(session['local_retirement_json'])
                # Two retained observers may finish the same proof. Keep the
                # first certificate instead of rewriting it for our own drain
                # flag revision. Any new obligation would already have cleared it.
                if ({k: v for k, v in previous.items() if k != 'retirement_revision'} ==
                        {k: v for k, v in checkpoint.items() if k != 'retirement_revision'}):
                    return True
            db.execute('UPDATE execution_local_streams SET drained=1 '
                'WHERE server_id=? AND executor_id=? AND session_id=? AND drained=0', key)
            db.execute('UPDATE execution_local_publications SET terminal=1 '
                'WHERE server_id=? AND executor_id=? AND session_id=? AND terminal=0', key)
            db.execute('UPDATE execution_sessions SET local_retirement_json=? '
                'WHERE server_id=? AND executor_id=? AND session_id=?',
                (json.dumps(checkpoint, sort_keys=True, separators=(',', ':')), *key))
            return True
