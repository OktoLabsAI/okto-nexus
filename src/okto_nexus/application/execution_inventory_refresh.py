"""Durable passive-inventory requests; no discovery or execution authority."""
from datetime import datetime, timezone

from ..domain.base import new_id
from ..errors import ErrorCode, OktoNexusError


def _missing():
    return OktoNexusError(ErrorCode.NOT_FOUND, "No inventory is available for this executor.", {})


def _authorize(uow, *, context, access, server_id, executor_id):
    operator = access.authenticate(context, uow=uow, require_feature=False)
    row = uow.connection.execute(
        "SELECT kind,registered_by_agent_id,control_state FROM execution_executors "
        "WHERE server_id=? AND executor_id=? AND revoked_at IS NULL",
        (server_id, executor_id)).fetchone()
    if row is None:
        raise _missing()
    if not operator and row['kind'] == 'remote' and row['registered_by_agent_id'] != context.actor_agent_id:
        bound = uow.connection.execute(
            "SELECT 1 FROM execution_bindings b JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id "
            "WHERE b.server_id=? AND b.executor_id=? AND ep.agent_id=? AND ep.enabled=1 "
            "AND ep.activation_state='approved' AND ep.protocol='nxl-r4' LIMIT 1",
            (server_id, executor_id, context.actor_agent_id)).fetchone()
        if bound is None:
            raise _missing()
    return row


def request_inventory_refresh(factory, *, context, access, server_id, executor_id, client_intent_id):
    if not isinstance(client_intent_id, str) or not 1 <= len(client_intent_id) <= 160:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid inventory refresh request ID.", {})
    with factory.unit_of_work() as uow:
        executor = _authorize(uow, context=context, access=access,
                              server_id=server_id, executor_id=executor_id)
        conn = uow.connection
        row = conn.execute(
            "SELECT * FROM execution_inventory_refresh WHERE server_id=? AND actor_agent_id=? "
            "AND client_intent_id=?", (server_id, context.actor_agent_id, client_intent_id)).fetchone()
        if row is not None and row['executor_id'] != executor_id:
            raise OktoNexusError(ErrorCode.CONFLICT, "The refresh request ID belongs to another executor.", {})
        if row is None:
            count = conn.execute("SELECT COUNT(*) FROM execution_inventory_refresh WHERE server_id=? "
                "AND executor_id=? AND completed_sequence IS NULL", (server_id, executor_id)).fetchone()[0]
            if count >= 32:
                raise OktoNexusError('CAPACITY_EXCEEDED', "The executor inventory refresh queue is full.", {})
            refresh_id = new_id('refresh')
            conn.execute("INSERT INTO execution_inventory_refresh(server_id,actor_agent_id,client_intent_id,"
                "refresh_id,executor_id,created_at) VALUES(?,?,?,?,?,?)", (server_id, context.actor_agent_id,
                client_intent_id, refresh_id, executor_id, datetime.now(timezone.utc).isoformat()))
            row = conn.execute("SELECT * FROM execution_inventory_refresh WHERE refresh_id=?", (refresh_id,)).fetchone()
        state = ('UPDATED' if row['completed_sequence'] is not None else
                 'OFFLINE' if executor['control_state'] != 'CONTROL_READY' else
                 'REQUESTED' if row['delivery_id'] else 'PENDING')
        return dict(client_intent_id=client_intent_id, refresh_id=row['refresh_id'],
                    executor_id=executor_id, state=state)


def claim_inventory_refresh(uow, *, server_id, executor_id, producer_instance_id, connection_generation):
    """Caller must authenticate the executor before entering this transaction.

    Recheck durable channel ownership here. A claim only asks for a new passive
    observation; the host still owns discovery and the publication sequence.
    """
    conn = uow.connection
    owner = conn.execute("SELECT 1 FROM execution_executors WHERE server_id=? AND executor_id=? "
        "AND owner_instance_id=? AND generation=? AND control_state='CONTROL_READY' AND revoked_at IS NULL",
        (server_id, executor_id, producer_instance_id, connection_generation)).fetchone()
    if owner is None:
        raise OktoNexusError(ErrorCode.CONFLICT, "The inventory refresh channel is not current.", {})
    pending = conn.execute("SELECT 1 FROM execution_inventory_refresh WHERE server_id=? AND executor_id=? "
        "AND completed_sequence IS NULL LIMIT 1", (server_id, executor_id)).fetchone()
    if pending is None:
        return None
    prior = conn.execute("SELECT delivery_id FROM execution_inventory_refresh_deliveries WHERE server_id=? "
        "AND executor_id=? AND producer_instance_id=? AND connection_generation=? AND completed_sequence IS NULL",
        (server_id, executor_id, producer_instance_id, connection_generation)).fetchone()
    if prior is not None:
        return prior['delivery_id']
    baseline = conn.execute("SELECT publication_sequence FROM execution_inventory_current "
        "WHERE server_id=? AND executor_id=?", (server_id, executor_id)).fetchone()
    delivery_id = new_id('refresh_delivery')
    conn.execute("INSERT INTO execution_inventory_refresh_deliveries(delivery_id,server_id,executor_id,"
        "producer_instance_id,connection_generation,baseline_sequence) VALUES(?,?,?,?,?,?)",
        (delivery_id, server_id, executor_id, producer_instance_id, connection_generation, baseline[0] if baseline else 0))
    conn.execute("UPDATE execution_inventory_refresh SET delivery_id=? WHERE server_id=? AND executor_id=? "
        "AND completed_sequence IS NULL", (delivery_id, server_id, executor_id))
    return delivery_id


def complete_inventory_refresh(uow, *, delivery_id, server_id, executor_id, producer_instance_id, sequence):
    """Join correlation to a validated publication in the SAME transaction."""
    conn = uow.connection
    row = conn.execute("SELECT d.*,e.owner_instance_id,e.generation,e.revoked_at FROM "
        "execution_inventory_refresh_deliveries d JOIN execution_executors e "
        "ON e.server_id=d.server_id AND e.executor_id=d.executor_id WHERE d.delivery_id=?",
        (delivery_id,)).fetchone()
    if (row is None or row['server_id'] != server_id or row['executor_id'] != executor_id
            or row['producer_instance_id'] != producer_instance_id or row['owner_instance_id'] != producer_instance_id
            or row['connection_generation'] != row['generation'] or row['revoked_at'] is not None
            or sequence <= row['baseline_sequence']
            or row['completed_sequence'] not in (None, sequence)):
        raise OktoNexusError(ErrorCode.CONFLICT, "The inventory refresh publication does not match its delivery.", {})
    conn.execute("UPDATE execution_inventory_refresh_deliveries SET completed_sequence=? WHERE delivery_id=?",
                 (sequence, delivery_id))
    conn.execute("UPDATE execution_inventory_refresh SET completed_sequence=? WHERE delivery_id=?",
                 (sequence, delivery_id))
