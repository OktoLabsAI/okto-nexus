"""Accept a prelease refusal only from its authenticated current control owner."""
import hashlib
import json

from nexus_connector_core import CapacityConsumption, CapacityReservation
from nexus_connector_core.protocol import canonical_json
from nexus_connector_core.startup_refusal_link import decode_startup_refusal, encode_startup_refusal

from ....errors import ErrorCode, OktoNexusError


def _conflict():
    return OktoNexusError(ErrorCode.CONFLICT,
        'The startup refusal does not match its pending opening.', {})


def verify_startup_refusal(uow, channel, report, receipt, operation, scope):
    """Verify the original dispatch and physical release in the receipt UOW."""
    report = decode_startup_refusal(encode_startup_refusal(report))
    if report['type'] != 'startup.refuse' or report['receipt'] != receipt:
        raise _conflict()
    source = report['refusal']['binding']['source']
    refusal = report['refusal']
    key = source['server_id'], source['executor_id'], source['operation_id']
    session_key = *key[:2], source['session_id']
    conn = uow.connection
    if (operation['action'] != 'runtime.open' or not scope
            or refusal['scope'] != scope
            or (channel.server_id, channel.executor_id, channel.connection_id,
                channel.connection_generation) != tuple(report[k] for k in (
                    'server_id', 'executor_id', 'connection_id', 'connection_generation'))
            or conn.execute("SELECT 1 FROM execution_executors WHERE server_id=? AND executor_id=? "
                "AND owner_instance_id=? AND generation=? AND control_state='CONTROL_READY' "
                "AND revoked_at IS NULL", (channel.server_id, channel.executor_id,
                channel.connection_id, channel.connection_generation)).fetchone() is None):
        raise _conflict()
    admissions = conn.execute('SELECT reservation_json,consumption_json FROM execution_capacity_admissions '
        'WHERE server_id=? AND executor_id=? AND session_id=?', session_key).fetchall()
    if len(admissions) > 1 or bool(admissions) != (report['capacity'] is not None):
        raise _conflict()
    if admissions:
        original = CapacityReservation.from_dict(json.loads(admissions[0]['reservation_json']))
        consumption = CapacityConsumption.from_dict(json.loads(admissions[0]['consumption_json']))
        released = CapacityReservation.from_dict(report['capacity'])
        if (released.request != original.request or released.reservation_id != original.reservation_id
                or released.consumption != consumption
                or released.capacity_revision < original.capacity_revision
                or any(getattr(released.request.scope, name) != value for name, value in scope.items())):
            raise _conflict()
    # A lost ACK may replay exactly the already committed terminal fact. It
    # must still carry the same physical release and current channel proof.
    raw_receipt = canonical_json(receipt)
    prior = conn.execute('SELECT canonical_frame,frame_digest FROM execution_receipts '
        'WHERE server_id=? AND executor_id=? AND operation_id=? AND receipt_revision=1', key).fetchone()
    if prior is not None:
        if (prior['canonical_frame'] != raw_receipt.decode()
                or prior['frame_digest'] != 'sha256:' + hashlib.sha256(raw_receipt).hexdigest()):
            raise _conflict()
        return report
    session = conn.execute('SELECT open_operation_id,owner_generation,lifecycle_state,stream_epoch '
        'FROM execution_sessions WHERE server_id=? AND executor_id=? AND session_id=?', session_key).fetchone()
    dispatch = conn.execute('SELECT dispatch_state,dispatch_phase,dispatch_grant_id,dispatch_connection_id,'
        'connection_generation,lease_id,lease_serial FROM execution_dispatch_outbox '
        'WHERE server_id=? AND executor_id=? AND operation_id=?', key).fetchone()
    if (session is None or session['open_operation_id'] != key[2]
            or session['owner_generation'] != scope['session_owner_generation']
            or session['lifecycle_state'] != 'OPEN_PENDING' or session['stream_epoch'] is not None
            or dispatch is None or dispatch['dispatch_state'] not in ('SENDING', 'DISPATCHED', 'RECONCILING')
            or dispatch['dispatch_phase'] != 'OPEN_AUTHORIZED_PENDING_LEASE'
            or dispatch['dispatch_grant_id'] != refusal['grant_id']
            or dispatch['dispatch_connection_id'] != source['connection_id']
            or dispatch['connection_generation'] != source['connection_generation']
            or dispatch['lease_id'] is not None or dispatch['lease_serial'] is not None
            or conn.execute('SELECT 1 FROM execution_leases WHERE server_id=? AND executor_id=? '
                'AND session_id=? AND applied_at IS NOT NULL LIMIT 1', session_key).fetchone()
            or conn.execute('SELECT 1 FROM execution_event_ingress WHERE server_id=? AND executor_id=? '
                'AND session_id=? LIMIT 1', session_key).fetchone()
            or conn.execute('SELECT 1 FROM execution_native_actions WHERE server_id=? AND executor_id=? '
                'AND session_id=? LIMIT 1', session_key).fetchone()):
        raise _conflict()
    return report
