"""Renew live control proofs without replacing their socket or execution leases."""
from datetime import datetime, timedelta, timezone

from ..adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from ..adapters.outbound.sqlite.execution_tickets import verify_execution_ticket
from ..errors import ErrorCode, OktoNexusError


def renew_connection(factory, *, channel, ticket):
    verified = verify_execution_ticket(factory, ticket=ticket, server_id=channel.server_id,
        executor_id=channel.executor_id, scope='link:connect')
    with factory.unit_of_work(write=False) as uow:
        lanes = uow.connection.execute('SELECT * FROM execution_control_lanes WHERE server_id=? '
            'AND executor_id=? AND connection_id=? AND connection_generation=?',
            (channel.server_id, channel.executor_id, channel.connection_id, channel.connection_generation)).fetchall()
    # Materialize current identity/policy revisions before the atomic renewal.
    for agent_id in {verified.agent_id, *(lane['agent_id'] for lane in lanes)}:
        current_agent_revisions(factory, agent_id=agent_id)
    now = datetime.now(timezone.utc)
    expires = (now + timedelta(seconds=600)).isoformat()
    with factory.unit_of_work() as uow:
        conn = uow.connection
        owner = conn.execute("SELECT 1 FROM execution_executors WHERE server_id=? AND executor_id=? "
            "AND owner_instance_id=? AND generation=? AND control_state='CONTROL_READY' AND revoked_at IS NULL",
            (channel.server_id, channel.executor_id, channel.connection_id, channel.connection_generation)).fetchone()
        rows = conn.execute('SELECT t.*,r.credential_epoch AS current_epoch,r.authorization_revision AS current_authorization '
            'FROM execution_link_tickets t JOIN execution_agent_revisions r '
            'ON r.server_id=t.server_id AND r.agent_id=t.agent_id WHERE t.ticket_id IN ('
            + ','.join('?' for _ in range(len(lanes)+1)) + ')',
            (verified.ticket_id, *(lane['ticket_id'] for lane in lanes))).fetchall()
        if (not owner or len(rows) != len(lanes)+1 or any(
                row['revoked_at'] is not None or row['bound_connection_id'] != channel.connection_id
                or datetime.fromisoformat(row['expires_at'].replace('Z', '+00:00')) <= now
                or row['credential_epoch'] != row['current_epoch']
                or row['authorization_revision'] != row['current_authorization'] for row in rows)):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Connection authority changed or expired.', {})
        for lane in lanes:
            current = conn.execute('SELECT configuration_revision FROM execution_agent_revisions WHERE server_id=? AND agent_id=?',
                (channel.server_id, lane['agent_id'])).fetchone()
            if current is None or current[0] != lane['configuration_revision']:
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Lane configuration changed.', {})
        for row in rows:
            conn.execute('UPDATE execution_link_tickets SET expires_at=? WHERE ticket_id=?', (expires, row['ticket_id']))
        conn.execute('UPDATE execution_control_lanes SET expires_at=? WHERE server_id=? AND executor_id=? '
            'AND connection_id=? AND connection_generation=?',
            (expires, channel.server_id, channel.executor_id, channel.connection_id, channel.connection_generation))
    return dict(expires_in=600, binding_ids=[lane['binding_id'] for lane in lanes])
