"""Transactional persistence for Server-issued R4 leases."""

from __future__ import annotations

import json

from nexus_connector_core.protocol import canonical_json


class SqliteExecutionLeaseRepository:
    def current_channel(self, uow, channel):
        return uow.connection.execute(
            "SELECT 1 FROM execution_executors WHERE server_id=? AND executor_id=? "
            "AND owner_instance_id=? AND generation=? AND revoked_at IS NULL "
            "AND control_state IN ('RECOVERING','CONTROL_READY')",
            (channel.server_id, channel.executor_id, channel.connection_id, channel.connection_generation)).fetchone() is not None

    @staticmethod
    def key(scope):
        return scope['server_id'], scope['executor_id'], scope['session_id']

    def authority(self, uow, scope):
        return uow.connection.execute(
            "SELECT s.*,b.endpoint_id,b.binding_revision,b.candidate_ref,b.inventory_revision,"
            "b.workspace_binding_id AS binding_workspace_binding_id,r.workspace_binding_id AS realization_workspace_binding_id,"
            "b.realization_revision,ep.agent_id,ep.adapter_id,ep.protocol,ep.profile_id,"
            "ep.enabled,ep.activation_state,ep.health,"
            "w.status AS workspace_status,r.status AS realization_status,"
            "r.revision AS current_realization_revision,r.subject_agent_id,"
            "e.kind,e.control_state,e.generation,e.owner_instance_id,e.revoked_at,"
            "a.api_key_hash,a.is_active,p.semantic_payload,p.expected_revisions_json,"
            "p.admission_state,p.actor_agent_id,i.source_guard_digest,"
            "o.dispatch_phase,o.dispatch_grant_id,o.dispatch_connection_id,"
            "o.connection_generation AS dispatch_connection_generation "
            "FROM execution_sessions s "
            "JOIN execution_bindings b ON b.server_id=s.server_id AND b.executor_id=s.executor_id AND b.binding_id=s.binding_id "
            "JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id "
            "JOIN agents a ON a.agent_id=ep.agent_id "
            "JOIN execution_executors e ON e.server_id=s.server_id AND e.executor_id=s.executor_id "
            "JOIN execution_workspace_bindings w ON w.server_id=s.server_id AND w.executor_id=s.executor_id AND w.workspace_binding_id=s.workspace_binding_id "
            "JOIN execution_realizations r ON r.server_id=b.server_id AND r.executor_id=b.executor_id AND r.realization_ref=b.realization_ref "
            "JOIN execution_operations p ON p.server_id=s.server_id AND p.executor_id=s.executor_id AND p.operation_id=s.open_operation_id "
            "JOIN execution_client_intents i ON i.server_id=p.server_id AND i.actor_agent_id=p.actor_agent_id AND i.operation_id=p.operation_id AND i.intent_id GLOB 'r4intent_*' AND i.session_selection<>'reuse' "
            "LEFT JOIN execution_dispatch_outbox o ON o.server_id=p.server_id AND o.executor_id=p.executor_id AND o.operation_id=p.operation_id "
            "WHERE s.server_id=? AND s.executor_id=? AND s.session_id=?",
            self.key(scope)).fetchone()

    def lane(self, uow, scope):
        return uow.connection.execute(
            "SELECT l.*,t.revoked_at,t.expires_at AS ticket_expires_at,t.bound_connection_id,t.scopes_json "
            "FROM execution_control_lanes l JOIN execution_link_tickets t ON t.ticket_id=l.ticket_id "
            "WHERE l.server_id=? AND l.executor_id=? AND l.binding_id=?",
            (scope['server_id'], scope['executor_id'], scope['binding_id'])).fetchone()

    def source_grant(self, uow, grant_id):
        return uow.connection.execute(
            "SELECT * FROM runtime_execution_grants WHERE grant_id=?", (grant_id,)).fetchone()

    def inventory(self, uow, scope):
        return uow.connection.execute(
            "SELECT c.inventory_revision,c.publication_sequence,s.observation_age_ms,s.canonical_projection "
            "FROM execution_inventory_current c JOIN execution_inventory_snapshots s "
            "ON s.server_id=c.server_id AND s.executor_id=c.executor_id AND s.publication_sequence=c.publication_sequence "
            "WHERE c.server_id=? AND c.executor_id=?",
            (scope['server_id'], scope['executor_id'])).fetchone()

    def latest(self, uow, scope):
        return uow.connection.execute(
            "SELECT * FROM execution_leases WHERE server_id=? AND executor_id=? AND session_id=? "
            "ORDER BY lease_serial DESC LIMIT 1", self.key(scope)).fetchone()

    def effective(self, uow, scope):
        """Keep a compatible applied lease until renewal application commits."""
        latest = self.latest(uow, scope)
        if latest is None or latest['status'] != 'ISSUED':
            return latest
        request = json.loads(latest['request_json'])
        if request.get('purpose') != 'renew':
            return latest
        previous = uow.connection.execute(
            "SELECT * FROM execution_leases WHERE server_id=? AND executor_id=? AND session_id=? "
            "AND lease_serial=? AND status='ACTIVE' AND applied_at IS NOT NULL",
            (*self.key(scope), latest['lease_serial'] - 1)).fetchone()
        fields = ('scope_json','connection_id','connection_generation','grant_id',
                  'source_grant_revision','allowed_actions_json')
        if previous is not None and all(previous[k] == latest[k] for k in fields):
            return previous
        return latest

    def request(self, uow, scope, request_id):
        return uow.connection.execute(
            "SELECT * FROM execution_leases WHERE server_id=? AND executor_id=? AND session_id=? AND request_id=?",
            (*self.key(scope), request_id)).fetchone()

    def issue(self, uow, request, frame, *, digest, source_revision, now, expires):
        scope = request['scope']
        key = self.key(scope)
        conn = uow.connection
        previous = self.latest(uow, scope)
        preserve_applied = (request['purpose'] == 'renew' and previous is not None and
            previous['status'] == 'ACTIVE' and previous['applied_at'] is not None and
            previous['scope_json'] == canonical_json(scope).decode() and
            previous['connection_id'] == request['connection_id'] and
            previous['connection_generation'] == request['connection_generation'] and
            previous['grant_id'] == frame['grant_id'] and previous['source_grant_revision'] == source_revision and
            previous['allowed_actions_json'] == canonical_json(frame['allowed_actions']).decode())
        if not preserve_applied:
            conn.execute(
                "UPDATE execution_leases SET status='SUPERSEDED' WHERE server_id=? AND executor_id=? AND session_id=? AND status IN ('ISSUED','ACTIVE')", key)
        conn.execute(
            "INSERT INTO execution_leases(server_id,executor_id,session_id,lease_serial,lease_id,grant_id,"
            "allowed_actions_json,authorization_revision,configuration_revision,owner_generation,connection_generation,"
            "credential_epoch,valid_until_server,request_id,status,connection_id,binding_revision,source_grant_revision,"
            "request_digest,request_json,grant_json,scope_json,issued_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'ISSUED',?,?,?,?,?,?,?,?)",
            (*key, frame['lease_serial'], frame['lease_id'], frame['grant_id'],
             canonical_json(frame['allowed_actions']).decode(), scope['authorization_revision'],
             scope['configuration_revision'], scope['session_owner_generation'], request['connection_generation'],
             scope['credential_epoch'], expires, request['request_id'], request['connection_id'],
             scope['binding_revision'], source_revision, digest, canonical_json(request).decode(),
             canonical_json(frame).decode(), canonical_json(scope).decode(), now))
        if not preserve_applied:
            conn.execute(
                "UPDATE execution_sessions SET lease_state='LEASE_PENDING' WHERE server_id=? AND executor_id=? AND session_id=?", key)

    def applied(self, uow, scope, *, serial, now, revoked=False):
        state = 'REVOKED' if revoked else 'ACTIVE'
        uow.connection.execute(
            "UPDATE execution_leases SET status='SUPERSEDED' WHERE server_id=? AND executor_id=? AND session_id=? "
            "AND lease_serial<>? AND status IN ('ISSUED','ACTIVE')", (*self.key(scope), serial))
        uow.connection.execute(
            "UPDATE execution_leases SET status=?,applied_at=? WHERE server_id=? AND executor_id=? AND session_id=? AND lease_serial=?",
            (state, now, *self.key(scope), serial))
        uow.connection.execute(
            "UPDATE execution_sessions SET lease_state=? WHERE server_id=? AND executor_id=? AND session_id=?",
            (state, *self.key(scope)))
        # Stable per-session secrets follow the legitimately applied lease.
        # Merely issuing/sending a grant must not extend credential validity.
        lease = self.latest(uow, scope)
        if revoked:
            uow.connection.execute(
                "UPDATE execution_session_capabilities SET revoked_at=? WHERE server_id=? "
                "AND executor_id=? AND session_id=? AND revoked_at IS NULL",
                (now, *self.key(scope)))
        else:
            uow.connection.execute(
                "UPDATE execution_session_capabilities SET valid_until_server=? WHERE server_id=? "
                "AND executor_id=? AND session_id=? AND scope_json=? AND source_grant_id=? "
                "AND source_grant_revision=? AND revoked_at IS NULL",
                (lease['valid_until_server'], *self.key(scope), lease['scope_json'],
                 lease['grant_id'], lease['source_grant_revision']))

    def apply_open_bootstrap(self, uow, scope, lease):
        """Attach the first applied lease to its already fenced opening send."""
        conn = uow.connection
        key = self.key(scope)
        pending = conn.execute(
            "SELECT o.operation_id FROM execution_dispatch_outbox o "
            "JOIN execution_sessions s ON s.server_id=o.server_id AND s.executor_id=o.executor_id "
            "AND s.open_operation_id=o.operation_id WHERE s.server_id=? AND s.executor_id=? "
            "AND s.session_id=? AND o.dispatch_phase='OPEN_AUTHORIZED_PENDING_LEASE'", key).fetchone()
        if pending is None:
            return True
        return conn.execute(
            "UPDATE execution_dispatch_outbox SET dispatch_phase='LEASE_AUTHORIZED',lease_id=?,lease_serial=? "
            "WHERE server_id=? AND executor_id=? AND operation_id=? AND dispatch_state='SENDING' "
            "AND dispatch_phase='OPEN_AUTHORIZED_PENDING_LEASE' AND dispatch_grant_id=? "
            "AND dispatch_connection_id=? AND connection_generation=? AND lease_id IS NULL AND lease_serial IS NULL",
            (lease['lease_id'],lease['lease_serial'],scope['server_id'],scope['executor_id'],pending['operation_id'],
             lease['grant_id'],lease['connection_id'],lease['connection_generation'])).rowcount == 1
