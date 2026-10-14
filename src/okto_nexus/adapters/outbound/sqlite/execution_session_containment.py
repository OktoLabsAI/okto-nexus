"""SQLite adapter for exact, durable session containment obligations."""
import json

from nexus_connector_core.protocol import canonical_json

from ....application.execution_session_containment import ContainmentTarget, matches_initial_refusal


class SqliteSessionContainmentRepository:
    def initial_refusal_records(self, uow, channel, *, agent_id=None, session_id=None, pending_only=True):
        return [dict(row) for row in uow.connection.execute(
            'SELECT c.request_json,c.state,o.operation_id,o.intent_hash,o.semantic_payload,'
            'o.expected_revisions_json,o.subject_agent_id,c.session_id,p.binding_json,a.reservation_json '
            'FROM execution_session_containment c JOIN execution_operations o '
            'ON o.server_id=c.server_id AND o.executor_id=c.executor_id AND o.operation_id=c.opening_operation_id '
            'LEFT JOIN execution_local_publications p ON p.server_id=o.server_id AND p.executor_id=o.executor_id '
            'AND p.operation_id=o.operation_id '
            'LEFT JOIN execution_capacity_admissions a ON a.server_id=c.server_id AND a.executor_id=c.executor_id '
            'AND a.session_id=c.session_id '
            "WHERE c.server_id=? AND c.executor_id=? AND json_extract(c.request_json,'$.purpose')='initial' "
            "AND o.action='runtime.open' AND (? IS NULL OR o.subject_agent_id=?) "
            "AND (? IS NULL OR c.session_id=?) AND (?=0 OR c.state='REQUESTED' OR p.terminal=0) "
            'ORDER BY c.recorded_at LIMIT 128',
            (channel.server_id, channel.executor_id, agent_id, agent_id,
             session_id, session_id, int(pending_only)))]

    def bind_initial_refusal(self, uow, channel, *, operation_id, session_id, binding):
        raw = canonical_json(binding).decode()
        old = uow.connection.execute('SELECT binding_json FROM execution_local_publications '
            'WHERE server_id=? AND executor_id=? AND operation_id=?',
            (channel.server_id, channel.executor_id, operation_id)).fetchone()
        if old is not None and old[0] != raw:
            return False
        uow.connection.execute('INSERT OR IGNORE INTO execution_local_publications '
            '(server_id,executor_id,operation_id,session_id,binding_json) VALUES(?,?,?,?,?)',
            (channel.server_id, channel.executor_id, operation_id, session_id, raw))
        return True

    def initial_target(self, uow, request, channel):
        scope = request['scope']
        if request['expected_lease_serial'] != 0:
            return None
        row = uow.connection.execute(
            "SELECT p.operation_id,p.intent_hash,p.expected_revisions_json,o.dispatch_grant_id "
            "FROM execution_sessions s JOIN execution_operations p ON p.server_id=s.server_id "
            "AND p.executor_id=s.executor_id AND p.operation_id=s.open_operation_id "
            "JOIN execution_dispatch_outbox o ON o.server_id=p.server_id AND o.executor_id=p.executor_id "
            "AND o.operation_id=p.operation_id JOIN execution_executors e ON e.server_id=s.server_id "
            "AND e.executor_id=s.executor_id WHERE s.server_id=? AND s.executor_id=? AND s.session_id=? "
            "AND s.owner_generation=? AND s.lifecycle_state='OPEN_PENDING' AND p.action='runtime.open' AND p.session_id=s.session_id "
            "AND o.dispatch_state IN ('SENDING','DISPATCHED','RECONCILING') "
            "AND o.dispatch_phase IN ('OPEN_AUTHORIZED_PENDING_LEASE','LEASE_AUTHORIZED') "
            "AND o.dispatch_connection_id=? AND o.connection_generation=? "
            "AND e.owner_instance_id=? AND e.generation=? AND e.revoked_at IS NULL AND e.control_state='CONTROL_READY'",
            (scope['server_id'],scope['executor_id'],scope['session_id'],scope['session_owner_generation'],
             channel.connection_id,channel.connection_generation,channel.connection_id,channel.connection_generation)).fetchone()
        if row is None or row['dispatch_grant_id'] != request['grant_id'] or json.loads(row['expected_revisions_json']) != scope:
            return None
        return ContainmentTarget(row['operation_id'], row['intent_hash'])

    def initial_refusal(self, uow, frame, scope):
        row = uow.connection.execute(
            'SELECT c.* FROM execution_session_containment c JOIN execution_dispatch_outbox o '
            'ON o.server_id=c.server_id AND o.executor_id=c.executor_id AND o.operation_id=c.opening_operation_id '
            'WHERE c.server_id=? AND c.executor_id=? AND c.session_id=? AND c.owner_generation=? '
            "AND o.dispatch_state IN ('SENDING','DISPATCHED','RECONCILING','RESOLVED_TERMINAL') "
            'AND o.dispatch_connection_id=? AND o.connection_generation=? '
            "AND o.dispatch_grant_id=json_extract(c.request_json,'$.grant_id')",
            (scope['server_id'],scope['executor_id'],scope['session_id'],scope['session_owner_generation'],
             frame['connection_id'],frame['connection_generation'])).fetchone()
        if row is None:
            return None
        request = json.loads(row['request_json'])
        return request if matches_initial_refusal(frame, scope, request,
            ContainmentTarget(row['opening_operation_id'],row['opening_intent_hash'])) else None

    def renewal_target(self, uow, request, channel):
        scope = request['scope']
        key = scope['server_id'], scope['executor_id'], scope['session_id']
        session = uow.connection.execute(
            "SELECT s.owner_generation,s.open_operation_id,p.intent_hash,p.expected_revisions_json "
            "FROM execution_sessions s JOIN execution_operations p ON p.server_id=s.server_id "
            "AND p.executor_id=s.executor_id AND p.operation_id=s.open_operation_id "
            "JOIN execution_executors e ON e.server_id=s.server_id AND e.executor_id=s.executor_id "
            "WHERE s.server_id=? AND s.executor_id=? AND s.session_id=? "
            "AND p.action='runtime.open' AND p.session_id=s.session_id "
            "AND s.lifecycle_state NOT IN ('CLOSED','FAILED') "
            "AND e.owner_instance_id=? AND e.generation=? AND e.revoked_at IS NULL "
            "AND e.control_state='CONTROL_READY'",
            (*key, channel.connection_id, channel.connection_generation)).fetchone()
        if (session is None or session['owner_generation'] != scope['session_owner_generation']
                or json.loads(session['expected_revisions_json']) != scope):
            return None
        latest = uow.connection.execute(
            'SELECT * FROM execution_leases WHERE server_id=? AND executor_id=? AND session_id=? '
            'ORDER BY lease_serial DESC LIMIT 1', key).fetchone()
        if latest is None:
            return None
        previous = latest
        if latest['lease_serial'] == request['expected_lease_serial'] + 1:
            # A renewal can be refused at the applied-confirmation barrier.
            # The issued record must be this exact request, not another writer.
            if not latest['request_json'] or json.loads(latest['request_json']) != request:
                return None
            previous = uow.connection.execute(
                'SELECT * FROM execution_leases WHERE server_id=? AND executor_id=? AND session_id=? '
                'AND lease_serial=?', (*key, request['expected_lease_serial'])).fetchone()
        elif latest['lease_serial'] != request['expected_lease_serial']:
            return None
        if (previous is None or previous['applied_at'] is None
                or any(previous[k] != request[k] for k in ('grant_id','connection_id','connection_generation'))
                or not previous['scope_json'] or json.loads(previous['scope_json']) != scope):
            return None
        return ContainmentTarget(session['open_operation_id'], session['intent_hash'])

    def record(self, uow, request, target, now):
        scope = request['scope']
        uow.connection.execute(
            'INSERT INTO execution_session_containment(server_id,executor_id,session_id,owner_generation,'
            'opening_operation_id,opening_intent_hash,request_json,recorded_at) VALUES (?,?,?,?,?,?,?,?) '
            'ON CONFLICT(server_id,executor_id,session_id,owner_generation) DO NOTHING',
            (scope['server_id'], scope['executor_id'], scope['session_id'], scope['session_owner_generation'],
             target.opening_operation_id, target.opening_intent_hash, canonical_json(request).decode(), now))

    def pending(self, uow, scope):
        return uow.connection.execute(
            "SELECT 1 FROM execution_session_containment WHERE server_id=? AND executor_id=? "
            "AND session_id=? AND owner_generation=? AND state='REQUESTED'",
            (scope['server_id'], scope['executor_id'], scope['session_id'],
             scope['session_owner_generation'])).fetchone() is not None

    def complete_verified(self, uow, channel, session_id, owner_generation, proof, now):
        key = channel.server_id, channel.executor_id, session_id, owner_generation
        obligation = uow.connection.execute(
            "SELECT * FROM execution_session_containment WHERE server_id=? AND executor_id=? "
            "AND session_id=? AND owner_generation=? AND state='REQUESTED'", key).fetchone()
        if obligation is None:
            return
        # Reconciliation already validated the release and drained stream. Bind
        # that result to the original obligation, not just a reused session ID.
        matched = uow.connection.execute(
            "SELECT 1 FROM execution_sessions s JOIN execution_operations p "
            "ON p.server_id=s.server_id AND p.executor_id=s.executor_id AND p.operation_id=s.open_operation_id "
            "WHERE s.server_id=? AND s.executor_id=? AND s.session_id=? AND s.owner_generation=? "
            "AND s.lifecycle_state='CLOSED' AND s.lease_state='CLOSED' "
            "AND p.operation_id=? AND p.intent_hash=? AND p.session_id=s.session_id AND p.action='runtime.open'",
            (*key, obligation['opening_operation_id'], obligation['opening_intent_hash'])).fetchone()
        if matched is None:
            raise ValueError('The released session does not match its original containment obligation.')
        uow.connection.execute(
            "UPDATE execution_session_containment SET state='RELEASED',release_proof_json=?,released_at=? "
            "WHERE server_id=? AND executor_id=? AND session_id=? AND owner_generation=? AND state='REQUESTED'",
            (canonical_json(proof).decode(), now, *key))
