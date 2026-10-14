"""Correlate a Core preopening fence and release with immutable admission."""
import hashlib
import json

from nexus_connector_core import CapacityReservation, CapacityConsumption
from nexus_connector_core.preopen_refusal_r4 import validate_r4_preopen_report
from nexus_connector_core.protocol import canonical_json

from ....errors import ErrorCode, OktoNexusError


def conflict():
    return OktoNexusError(ErrorCode.CONFLICT, 'The preopening recovery proof does not match its original admission.', {})


def verify_preopen_recovery(uow, channel, report, frame, operation):
    report = validate_r4_preopen_report(report)
    refusal, conn = report['refusal'], uow.connection
    source, recovery = refusal['source'], refusal['recovery']
    key = source['server_id'], source['executor_id'], source['operation_id']
    scope = json.loads(operation['expected_revisions_json'])
    if (report['receipt'] != frame or operation['action'] != 'runtime.open' or not scope
            or scope['session_owner_generation'] != refusal['session_owner_generation']
            or (channel.server_id, channel.executor_id) != key[:2]
            or not source['connection_generation'] < recovery['connection_generation'] <= channel.connection_generation
            or recovery['connection_generation'] == channel.connection_generation and recovery['connection_id'] != channel.connection_id
            or conn.execute("SELECT 1 FROM execution_executors WHERE server_id=? AND executor_id=? "
                "AND owner_instance_id=? AND generation=? AND control_state='RECOVERING' AND revoked_at IS NULL",
                (*key[:2], channel.connection_id, channel.connection_generation)).fetchone() is None):
        raise conflict()
    raw = canonical_json(report).decode()
    digest = 'sha256:' + hashlib.sha256(raw.encode()).hexdigest()
    previous = conn.execute('SELECT report_json,report_digest FROM execution_preopen_refusals '
        'WHERE server_id=? AND executor_id=? AND operation_id=?', key).fetchone()
    if previous is not None:
        if previous['report_json'] != raw or previous['report_digest'] != digest:
            raise conflict()
        return report
    session_key = *key[:2], source['session_id']
    session = conn.execute('SELECT * FROM execution_sessions WHERE server_id=? AND executor_id=? AND session_id=?', session_key).fetchone()
    dispatch = conn.execute('SELECT * FROM execution_dispatch_outbox WHERE server_id=? AND executor_id=? AND operation_id=?', key).fetchone()
    if (session is None or session['open_operation_id'] != key[2]
            or session['owner_generation'] != refusal['session_owner_generation']
            or session['lifecycle_state'] not in ('OPEN_PENDING', 'FAILED') or session['stream_epoch'] is not None
            or dispatch is None or dispatch['dispatch_connection_id'] != source['connection_id']
            or dispatch['connection_generation'] != source['connection_generation']
            or dispatch['dispatch_state'] not in ('SENDING', 'DISPATCHED', 'RECONCILING')
            or conn.execute('SELECT 1 FROM execution_receipts r JOIN execution_operations o USING(server_id,executor_id,operation_id) '
                'WHERE o.server_id=? AND o.executor_id=? AND o.session_id=? LIMIT 1', session_key).fetchone()
            or conn.execute('SELECT 1 FROM execution_event_ingress WHERE server_id=? AND executor_id=? AND session_id=? LIMIT 1', session_key).fetchone()):
        raise conflict()
    admissions = conn.execute('SELECT reservation_json,consumption_json FROM execution_capacity_admissions '
        'WHERE server_id=? AND executor_id=? AND session_id=?', session_key).fetchall()
    if len(admissions) > 1 or bool(admissions) != (report['capacity'] is not None):
        raise conflict()
    if admissions:
        original = CapacityReservation.from_dict(json.loads(admissions[0]['reservation_json']))
        consumption = CapacityConsumption.from_dict(json.loads(admissions[0]['consumption_json']))
        released = CapacityReservation.from_dict(report['capacity'])
        if (released.request != original.request or released.reservation_id != original.reservation_id
                or released.consumption != consumption or released.capacity_revision < original.capacity_revision
                or any(getattr(released.request.scope, k) != value for k, value in scope.items())):
            raise conflict()
    conn.execute('INSERT INTO execution_preopen_refusals VALUES(?,?,?,?,?,?,?,strftime(\'%Y-%m-%dT%H:%M:%fZ\',\'now\'))',
                 (*key, raw, digest, channel.connection_id, channel.connection_generation))
    return report


def finish_preopen_recovery(uow, channel, report):
    source = report['refusal']['source']
    conn, generation = uow.connection, report['refusal']['session_owner_generation']
    conn.execute("UPDATE execution_sessions SET lifecycle_state='CLOSED',lease_state='CLOSED' "
        'WHERE server_id=? AND executor_id=? AND session_id=? AND owner_generation=? AND open_operation_id=?',
        (source['server_id'], source['executor_id'], source['session_id'], generation, source['operation_id']))
    from .execution_session_containment import SqliteSessionContainmentRepository
    SqliteSessionContainmentRepository().complete_verified(uow, channel, source['session_id'], generation,
        dict(kind='preopen_refusal', report=report), conn.execute("SELECT strftime('%Y-%m-%dT%H:%M:%fZ','now')").fetchone()[0])
    from ....application.execution_initial_turns import settle_failed_initial_turns, settle_unsent_closed_session_operations
    settle_failed_initial_turns(conn, server_id=source['server_id'], executor_id=source['executor_id'])
    settle_unsent_closed_session_operations(conn, server_id=source['server_id'], executor_id=source['executor_id'])


class SqlitePreopenRecoveryRepository:
    def receipt_high(self, uow, channel, *, agent_id=None):
        return uow.connection.execute('SELECT coalesce(max(rowid),0) FROM execution_receipts '
            'WHERE server_id=? AND executor_id=? AND (? IS NULL OR operation_id IN '
            '(SELECT operation_id FROM execution_operations WHERE server_id=? AND executor_id=? AND subject_agent_id=?))',
            (channel.server_id, channel.executor_id, agent_id, channel.server_id, channel.executor_id, agent_id)).fetchone()[0]

    def accept(self, uow, channel, report):
        from .execution_receipts import append_execution_receipt
        append_execution_receipt(None, uow=uow, recovery_owner=channel, preopen=report, frame=report['receipt'])
        source = report['refusal']['source']
        rows = uow.connection.execute('SELECT o.operation_id FROM execution_operations o '
            'JOIN execution_unsent_dispatch_proofs p USING(server_id,executor_id,operation_id) '
            "WHERE o.server_id=? AND o.executor_id=? AND o.session_id=? AND o.admission_state='RESOLVED_TERMINAL'",
            (source['server_id'], source['executor_id'], source['session_id'])).fetchall()
        return {row['operation_id'] for row in rows}
