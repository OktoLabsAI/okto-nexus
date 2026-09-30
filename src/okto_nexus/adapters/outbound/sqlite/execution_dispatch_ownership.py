"""Durable dispatch ownership; unsent recovery never replays a possible send."""

import json

from ....errors import ErrorCode, OktoNexusError


def _key(reservation):
    return (reservation.server_id, reservation.executor_id, reservation.operation_id,
            reservation.attempt_token, reservation.attempt_no,
            reservation.owner_connection_id, reservation.owner_connection_generation)


def _error(code, message, *, possible_effect, operation_id):
    return json.dumps(dict(code=code, stage='dispatch', message=message,
        possible_effect=possible_effect, retry_safe=False, operation_id=operation_id,
        action='Query this operation and reconcile its executor before requesting new work.'), separators=(',', ':'))


def reject_unsent_dispatch(factory, *, reservation, error):
    """Resolve a definitive authorization failure without inventing a Core receipt."""
    with factory.unit_of_work() as uow:
        conn = uow.connection
        changed = conn.execute(
            "UPDATE execution_dispatch_outbox SET dispatch_state='RESOLVED_TERMINAL',"
            "reservation_class=NULL,reserved_bytes=0,reserved_at=NULL,last_error=? "
            "WHERE server_id=? AND executor_id=? AND operation_id=? AND attempt_token=? AND attempt_no=? "
            "AND reservation_owner IS ? AND reservation_generation IS ? AND dispatch_state='RESERVED' "
            "AND reservation_class=? AND reserved_bytes=?",
            (_error(error.code, error.message, possible_effect=False, operation_id=reservation.operation_id),
             *_key(reservation), reservation.reservation_class, reservation.reserved_bytes)).rowcount
        if changed != 1:
            raise OktoNexusError(ErrorCode.CONFLICT, 'The unsent dispatch reservation changed.', {})
        conn.execute("UPDATE execution_operations SET admission_state='RESOLVED_TERMINAL' "
                     "WHERE server_id=? AND executor_id=? AND operation_id=?", _key(reservation)[:3])
        conn.execute("UPDATE execution_sessions SET lifecycle_state='FAILED' WHERE server_id=? AND executor_id=? "
                     "AND open_operation_id=? AND lifecycle_state='OPEN_PENDING' AND lease_state='NONE'",
                     _key(reservation)[:3])


def recover_fenced_reservations(factory, *, channel):
    """The current connection can recover RESERVED rows of fenced known owners.

    The old owner cannot commit SENDING after this CAS because dispatch checks
    both its exact token and current connection ownership. Legacy ownerless
    reservations and all SENDING rows remain fenced for reconciliation.
    """
    with factory.unit_of_work() as uow:
        conn = uow.connection
        owner = conn.execute(
            "SELECT 1 FROM execution_executors WHERE server_id=? AND executor_id=? "
            "AND owner_instance_id=? AND generation=? AND control_state IN ('RECOVERING','CONTROL_READY')",
            (channel.server_id, channel.executor_id, channel.connection_id, channel.connection_generation)).fetchone()
        if owner is None:
            raise OktoNexusError(ErrorCode.CONFLICT, 'The recovery connection is no longer the owner.', {})
        return conn.execute(
            "UPDATE execution_dispatch_outbox SET dispatch_state='PENDING',attempt_token=NULL,"
            "reservation_class=NULL,reserved_bytes=0,reserved_at=NULL,reservation_owner=NULL,reservation_generation=NULL "
            "WHERE server_id=? AND executor_id=? AND dispatch_state='RESERVED' AND reservation_owner IS NOT NULL "
            "AND reservation_generation IS NOT NULL AND (reservation_owner<>? OR reservation_generation<>?)",
            (channel.server_id, channel.executor_id, channel.connection_id, channel.connection_generation)).rowcount


def release_dispatch_owner(factory, *, channel):
    """Release unsent capacity, but retain and expose uncertain sent operations."""
    with factory.unit_of_work() as uow:
        conn = uow.connection
        key = (channel.server_id, channel.executor_id, channel.connection_id, channel.connection_generation)
        conn.execute(
            "UPDATE execution_dispatch_outbox SET dispatch_state='PENDING',attempt_token=NULL,"
            "reservation_class=NULL,reserved_bytes=0,reserved_at=NULL,reservation_owner=NULL,reservation_generation=NULL "
            "WHERE server_id=? AND executor_id=? AND reservation_owner=? AND reservation_generation=? "
            "AND dispatch_state='RESERVED'", key)
        rows = conn.execute(
            "SELECT operation_id FROM execution_dispatch_outbox WHERE server_id=? AND executor_id=? "
            "AND reservation_owner=? AND reservation_generation=? AND dispatch_state='SENDING'", key).fetchall()
        for row in rows:
            operation_key = (*key[:2], row['operation_id'])
            conn.execute("UPDATE execution_dispatch_outbox SET dispatch_state='RECONCILING',last_error=? "
                         "WHERE server_id=? AND executor_id=? AND operation_id=?",
                         (_error('DISPATCH_CONNECTION_LOST', 'The dispatch connection closed before a durable receipt.',
                                 possible_effect=True, operation_id=row['operation_id']), *operation_key))
            conn.execute("UPDATE execution_operations SET admission_state='RECONCILING' "
                         "WHERE server_id=? AND executor_id=? AND operation_id=?", operation_key)
