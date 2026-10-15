"""SQLite attempt history; all transitions use the caller's short writer UoW."""
from dataclasses import asdict
import json

from nexus_connector_core import CapacityRequest, CapacityReservation
from nexus_connector_core.protocol import canonical_json

from ....application.handoff_runtime_attempts import HandoffRuntimeAttempt
from ....domain.handoff_automation import HandoffAutomationPrincipal
from ....errors import ErrorCode, OktoNexusError


def conflict():
    return OktoNexusError(ErrorCode.CONFLICT, 'Runtime handoff attempt conflicts with durable state.', {})


def encoded(value):
    return canonical_json(value).decode()


class SqliteHandoffRuntimeAttemptRepository:
    def create(self, uow, *, principal, request, claim_generation):
        p, r, conn = principal, request, uow.connection
        if (type(p) is not HandoffAutomationPrincipal or type(r) is not CapacityRequest
                or type(claim_generation) is not int or claim_generation < 0
                or (p.attempt_id, p.agent_id, p.workspace_id)
                != (r.attempt_id, r.scope.agent_id, r.scope.workspace_id)):
            raise conflict()
        existing = conn.execute('SELECT 1 FROM handoff_runtime_attempts WHERE attempt_id=?', (p.attempt_id,)).fetchone()
        if existing:
            attempt = self.get(uow, p.attempt_id)
            if (attempt.principal, attempt.request, attempt.claim_generation) != (p, r, claim_generation):
                raise conflict()
            return attempt
        handoff = conn.execute('SELECT workspace_id,status,claim_epoch,target FROM handoffs WHERE handoff_id=?',
                               (p.handoff_id,)).fetchone()
        if (handoff is None or tuple(handoff[:3]) != (p.workspace_id, 'OPEN', claim_generation)
                or json.loads(handoff['target']).get('strategy') != 'broadcast'
                or conn.execute('SELECT 1 FROM handoff_runtime_attempts WHERE workspace_id=? AND handoff_id=? '
                                'AND agent_id=? AND active=1', (p.workspace_id, p.handoff_id, p.agent_id)).fetchone()):
            raise conflict()
        conn.execute('INSERT INTO handoff_runtime_attempts(attempt_id,workspace_id,handoff_id,agent_id,claim_generation,'
            'principal_json,request_json,state,disposition,active,created_at,updated_at) '
            "VALUES(?,?,?,?,?,?,?,'WAITING','ACQUIRE',1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
            (p.attempt_id, p.workspace_id, p.handoff_id, p.agent_id, claim_generation, encoded(asdict(p)), encoded(r.to_dict())))
        return self.get(uow, p.attempt_id)

    def get(self, uow, attempt_id):
        row = uow.connection.execute('SELECT * FROM handoff_runtime_attempts WHERE attempt_id=?', (attempt_id,)).fetchone()
        if row is None:
            raise conflict()
        return HandoffRuntimeAttempt(HandoffAutomationPrincipal(**json.loads(row['principal_json'])),
            CapacityRequest.from_dict(json.loads(row['request_json'])), row['claim_generation'],
            CapacityReservation.from_dict(json.loads(row['reservation_json'])) if row['reservation_json'] else None,
            row['operation_id'], row['state'], row['disposition'], bool(row['reserve_started']), bool(row['active']), row['reason'])

    def _update(self, uow, attempt_id, *, state, reason=None, **values):
        fields = dict(state=state, reason=reason, **values)
        uow.connection.execute('UPDATE handoff_runtime_attempts SET '
            + ','.join(k + '=?' for k in fields) + ",updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE attempt_id=?",
            (*fields.values(), attempt_id))
        return self.get(uow, attempt_id)

    def reserving(self, uow, attempt_id):
        a = self.get(uow, attempt_id)
        if a.active and not a.operation_id and a.disposition == 'ACQUIRE' and a.reservation is None:
            return self._update(uow, attempt_id, state='RESERVING', reserve_started=1)
        return a

    def unavailable(self, uow, attempt_id, reason):
        a = self.get(uow, attempt_id)
        if not a.active or a.operation_id or a.disposition == 'RELEASE' or a.reservation is not None:
            return a
        return self._update(uow, attempt_id, state='NOT_AVAILABLE', reason=reason,
                            active=int(a.reserve_started))

    def observe(self, uow, attempt_id, reservation):
        a = self.get(uow, attempt_id)
        r = reservation
        if (type(r) is not CapacityReservation or r.request != a.request
                or a.reservation is not None and a.reservation.reservation_id != r.reservation_id):
            raise conflict()
        if (not a.active or a.operation_id
                or a.reservation is not None and a.reservation.capacity_revision > r.capacity_revision):
            return a
        if r.state in ('RELEASED', 'EXPIRED_UNCONSUMED') and r.consumption is None:
            return self._update(uow, attempt_id, state='CANCELLED_NO_EFFECT', active=0,
                                reservation_json=encoded(r.to_dict()))
        if r.state == 'HELD' and r.consumption is None:
            state = 'RESERVED' if a.disposition == 'ACQUIRE' else 'RELEASE_PENDING'
            return self._update(uow, attempt_id, state=state, reservation_json=encoded(r.to_dict()))
        return self._update(uow, attempt_id, state='NEEDS_RECONCILIATION', reason='NEEDS_RECONCILIATION',
                            reservation_json=encoded(r.to_dict()))

    def release_pending(self, uow, attempt_id):
        a = self.get(uow, attempt_id)
        if not a.active or a.operation_id:
            return a
        if not a.reserve_started:
            return self._update(uow, attempt_id, state='CANCELLED_NO_EFFECT', active=0, disposition='RELEASE')
        return self._update(uow, attempt_id, state='RELEASE_PENDING', disposition='RELEASE')

    def uncertain(self, uow, attempt_id):
        a = self.get(uow, attempt_id)
        if not a.active or a.operation_id:
            return a
        return self._update(uow, attempt_id, state='NEEDS_RECONCILIATION', reason='NEEDS_RECONCILIATION')

    def claimed(self, uow, attempt_id, operation_id):
        a = self.get(uow, attempt_id)
        if a.operation_id:
            if a.operation_id != operation_id:
                raise conflict()
            return a
        row = uow.connection.execute('SELECT ca.reservation_json,h.claim_epoch,h.claimed_by FROM execution_capacity_admissions ca '
            'JOIN runtime_handoff_bindings hb ON hb.operation_id=ca.domain_operation_id '
            'JOIN handoffs h ON h.handoff_id=hb.handoff_id '
            'WHERE ca.domain_operation_id=? AND ca.attempt_id=? AND h.handoff_id=? AND h.workspace_id=?',
            (operation_id, attempt_id, a.principal.handoff_id, a.principal.workspace_id)).fetchone()
        if (not a.active or a.disposition != 'ACQUIRE' or a.state != 'RESERVED' or row is None
                or row['claim_epoch'] != a.claim_generation + 1 or row['claimed_by'] != a.principal.agent_id
                or CapacityReservation.from_dict(json.loads(row['reservation_json'])) != a.reservation):
            raise conflict()
        return self._update(uow, attempt_id, state='CLAIM_COMMITTED', operation_id=operation_id)
