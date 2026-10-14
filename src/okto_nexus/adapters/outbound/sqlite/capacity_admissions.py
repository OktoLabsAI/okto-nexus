"""Durable claim/operation capacity linkage in the caller's SQLite UoW."""
import json

from nexus_connector_core import CapacityReservation, CapacityConsumption
from nexus_connector_core.protocol import canonical_json

from ....application.capacity_admission import CapacityAdmission
from ....application.execution_domain_delivery import delivery_session_context, select_delivery_session
from ....errors import ErrorCode, OktoNexusError
from .handoff_origins import SqliteHandoffOriginRepo
from .execution_agent_revisions import current_agent_revisions


def conflict(reason):
    return OktoNexusError(ErrorCode.CONFLICT, reason, {'reason': reason})


class SqliteCapacityAdmissionRepository:
    def require_available(self, uow, *, handoff, endpoint_id, reservation):
        if (type(reservation) is not CapacityReservation or reservation.state != 'HELD'
                or reservation.consumption is not None or reservation.remaining_ms <= 0):
            raise conflict('RESERVATION_CONFLICT')
        req, conn = reservation.request, uow.connection
        scope = req.scope
        origin = SqliteHandoffOriginRepo().get(uow, workspace_id=handoff.workspace_id, handoff_id=handoff.handoff_id)
        binding, affinity = delivery_session_context(uow, endpoint_id,
            sender_agent_id=handoff.from_agent_id, source_session_key=origin.source_session_key)
        if (scope.agent_id != conn.execute('SELECT agent_id FROM agent_endpoints WHERE endpoint_id=?', (endpoint_id,)).fetchone()[0]
                or scope.workspace_id != handoff.workspace_id or req.affinity_key != affinity.capacity_key(scope.session_id)
                or any(getattr(scope, k) != binding[k] for k in ('server_id', 'executor_id', 'binding_id',
                                                              'workspace_binding_id', 'binding_revision'))):
            raise conflict('RESERVATION_CONFLICT')
        server, revisions, _ = current_agent_revisions(None, agent_id=scope.agent_id, uow=uow)
        if (server != scope.server_id or (revisions.authorization, revisions.configuration, revisions.credential_epoch)
                != (scope.authorization_revision, scope.configuration_revision, scope.credential_epoch)):
            raise conflict('STALE_OBSERVATION')
        if not conn.execute("SELECT 1 FROM execution_executors WHERE server_id=? AND executor_id=? "
                "AND generation=? AND control_state='CONTROL_READY' AND revoked_at IS NULL",
                (scope.server_id, scope.executor_id, scope.connection_generation)).fetchone():
            raise conflict('RECOVERING')
        if affinity.policy != 'one_shot':
            _, selected = select_delivery_session(uow, endpoint_id, sender_agent_id=handoff.from_agent_id,
                                                 source_session_key=origin.source_session_key)
            if (req.unit == 'next_turn' and selected != scope.session_id
                    or req.unit == 'new_session' and selected is not None):
                raise conflict('BUSY_AFFINITY')
        if req.unit == 'new_session' and conn.execute('SELECT 1 FROM execution_sessions '
                'WHERE server_id=? AND executor_id=? AND session_id=?',
                (scope.server_id, scope.executor_id, scope.session_id)).fetchone():
            raise conflict('BUSY_AFFINITY')
        if conn.execute("SELECT 1 FROM execution_operations WHERE server_id=? AND executor_id=? AND session_id=? "
                "AND action IN ('turn.submit','runtime.close') AND admission_state<>'RESOLVED_TERMINAL' LIMIT 1",
                (scope.server_id, scope.executor_id, scope.session_id)).fetchone():
            raise conflict('EARLIER_WORK_PENDING')
        if affinity.policy == 'one_shot':
            return  # The shared pool enforces earlier callers and physical counts atomically.
        # Existing logical work may not have a canonical turn yet (e.g. a
        # recovery deferral). Match exactly the same verified sender affinity.
        predicate = '' if affinity.policy == 'shared' else ' AND m.from_agent_id=?'
        args = () if affinity.policy == 'shared' else (handoff.from_agent_id,)
        if affinity.policy == 'per_sender_session':
            predicate += " AND COALESCE(origin.source_session_key,'')=?"
            args += (origin.source_session_key,)
        if conn.execute("SELECT 1 FROM delivery_outbox d JOIN messages m USING(message_id) "
                "LEFT JOIN execution_message_origins origin USING(message_id) "
                "LEFT JOIN runtime_handoff_bindings hb ON hb.operation_id=d.operation_id "
                "LEFT JOIN handoffs h ON h.handoff_id=hb.handoff_id AND h.claim_epoch=hb.claim_epoch "
                "WHERE d.endpoint_id=? AND d.workspace_id=? AND (h.status IN ('CLAIMED','VERIFYING') OR "
                "(d.reconciliation_id IS NULL AND d.external_completed_at IS NULL AND d.terminal_event_id IS NULL "
                "AND (d.canonical_terminal_operation_id IS NULL OR d.status='RETRY_WAIT') "
                "AND d.status NOT IN ('REJECTED','CANCELLED','FAILED_FINAL') "
                "AND NOT EXISTS (SELECT 1 FROM execution_delivery_releases r WHERE r.domain_operation_id=d.operation_id)))"
                + predicate + ' LIMIT 1', (endpoint_id, handoff.workspace_id, *args)).fetchone():
            raise conflict('EARLIER_WORK_PENDING')
        if conn.execute("SELECT 1 FROM runtime_pending_deliveries p JOIN message_deliveries d USING(delivery_id) "
                "JOIN messages m USING(message_id) LEFT JOIN execution_message_origins origin USING(message_id) "
                "WHERE d.recipient_agent_id=? AND m.workspace_id=? AND p.status='waiting'" + predicate + ' LIMIT 1',
                (scope.agent_id, scope.workspace_id, *args)).fetchone():
            raise conflict('EARLIER_WORK_PENDING')

    def attach(self, uow, *, operation_id, reservation):
        conn, req = uow.connection, reservation.request
        rows = conn.execute('SELECT o.* FROM execution_domain_deliveries d JOIN execution_operations o '
            'USING(server_id,executor_id,operation_id) WHERE d.domain_operation_id=?', (operation_id,)).fetchall()
        turns = [r for r in rows if r['action'] == 'turn.submit']
        opens = [r for r in rows if r['action'] == 'runtime.open']
        if len(turns) != 1 or len(opens) != int(req.unit == 'new_session') or len(rows) != len(turns) + len(opens):
            raise conflict('RESERVATION_CONFLICT')
        for row in rows:
            if any(value != getattr(req.scope, key) for key, value in json.loads(row['expected_revisions_json']).items()):
                raise conflict('RESERVATION_CONFLICT')
        consumption = CapacityConsumption(turns[0]['operation_id'], turns[0]['intent_hash'],
            opens[0]['operation_id'] if opens else None, opens[0]['intent_hash'] if opens else None)
        conn.execute("INSERT INTO execution_capacity_admissions VALUES(?,?,?,?,?,?,?,'WAITING_CONSUMPTION',NULL,"
                     "strftime('%Y-%m-%dT%H:%M:%fZ','now'))", (operation_id, req.attempt_id,
            req.scope.server_id, req.scope.executor_id, req.scope.session_id,
            canonical_json(reservation.to_dict()).decode(), canonical_json(consumption.to_dict()).decode()))
        return self.get(uow, operation_id)

    def get(self, uow, operation_id):
        row = uow.connection.execute('SELECT * FROM execution_capacity_admissions WHERE domain_operation_id=?',
                                     (operation_id,)).fetchone()
        if row is None:
            raise conflict('RESERVATION_CONFLICT')
        return CapacityAdmission(operation_id, CapacityReservation.from_dict(json.loads(row['reservation_json'])),
            CapacityConsumption.from_dict(json.loads(row['consumption_json'])), row['state'])

    def consumed(self, uow, admission, observed):
        current = self.get(uow, admission.operation_id)
        if (current.reservation.request != admission.reservation.request
                or current.reservation.reservation_id != admission.reservation.reservation_id
                or current.consumption != admission.consumption
                or type(observed) is not CapacityReservation or observed.state != 'CONSUMED'
                or observed.request != current.reservation.request
                or observed.reservation_id != current.reservation.reservation_id
                or observed.consumption != current.consumption):
            raise conflict('RESERVATION_CONFLICT')
        uow.connection.execute("UPDATE execution_capacity_admissions SET state='CONSUMED',reservation_json=?,reason=NULL,"
            "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE domain_operation_id=?",
            (canonical_json(observed.to_dict()).decode(), admission.operation_id))

    def uncertain(self, uow, admission):
        # Never downgrade another worker's confirmed consumption.
        uow.connection.execute("UPDATE execution_capacity_admissions SET state='NEEDS_RECONCILIATION',"
            "reason='NEEDS_RECONCILIATION',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') "
            "WHERE domain_operation_id=? AND state<>'CONSUMED'", (admission.operation_id,))
