"""An old Server socket cannot block a Connector's receipt recovery."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from test_ns09 import setup_authority

from okto_nexus.adapters.outbound.sqlite.execution_tickets import issue_execution_ticket
from okto_nexus.bootstrap.remote_connection_recovery import fence_remote_connections_after_restart


def test_restart_fences_only_remote_socket_authority_and_allows_ticket_replacement(
        tmp_path, monkeypatch):
    deps, app, _, _, _, _, _, revisions, _, _, server, executor = setup_authority(
        tmp_path, monkeypatch)
    factory = deps.connection_factory
    now = datetime.now(timezone.utc)
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "UPDATE execution_link_tickets SET revoked_at=? WHERE binding_id='binding'",
            (now.isoformat(),),
        )
    ticket = issue_execution_ticket(
        factory, server_id=server, executor_id=executor, agent_id='subject',
        binding_id='binding',
        scopes=frozenset({'lane:attach', 'lease:request', 'receipt:publish'}),
        client_intent_id='retained-lane', credential_request_id='first',
    )
    old_connection = 'conn_prior_server_process'
    expiry = (now + timedelta(minutes=5)).isoformat()
    with factory.unit_of_work() as uow:
        conn = uow.connection
        conn.execute(
            "UPDATE execution_executors SET owner_instance_id=?,generation=7,"
            "control_state='CONTROL_READY' WHERE server_id=? AND executor_id=?",
            (old_connection, server, executor),
        )
        conn.execute(
            'UPDATE execution_link_tickets SET bound_connection_id=? WHERE ticket_id=?',
            (old_connection, ticket.ticket_id),
        )
        conn.execute(
            'INSERT INTO execution_control_lanes(server_id,executor_id,binding_id,'
            'agent_id,ticket_id,attach_request_id,connection_id,connection_generation,'
            'credential_epoch,authorization_revision,configuration_revision,expires_at,state) '
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'ADMITTED')",
            (server, executor, 'binding', 'subject', ticket.ticket_id, 'attach-old',
             old_connection, 7, revisions.credential_epoch,
             revisions.authorization, revisions.configuration, expiry),
        )
        conn.execute(
            'INSERT INTO execution_connection_resumes(server_id,executor_id,'
            'connection_id,connection_generation,ticket_id,expires_at) '
            'VALUES (?,?,?,?,?,?)',
            (server, executor, old_connection, 7, ticket.ticket_id, expiry),
        )

    # Entering a fresh Server lifespan is the actual crash-recovery boundary.
    with TestClient(app) as client:
        assert client.get('/v1/connections/protocol').status_code == 200
    assert fence_remote_connections_after_restart(factory) == 1
    with factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        owner = conn.execute(
            'SELECT owner_instance_id,generation,control_state FROM execution_executors '
            'WHERE server_id=? AND executor_id=?', (server, executor),
        ).fetchone()
        assert tuple(owner) == (None, 7, 'DISCONNECTED')
        lane = conn.execute(
            'SELECT connection_id,connection_generation,state FROM execution_control_lanes '
            'WHERE server_id=? AND executor_id=?', (server, executor),
        ).fetchone()
        assert tuple(lane) == (old_connection, 7, 'DISCONNECTED')
        assert conn.execute(
            'SELECT bound_connection_id FROM execution_link_tickets WHERE ticket_id=?',
            (ticket.ticket_id,),
        ).fetchone()[0] is None
        assert conn.execute(
            'SELECT COUNT(*) FROM execution_connection_resumes WHERE server_id=? '
            'AND executor_id=?', (server, executor),
        ).fetchone()[0] == 0

    successor = issue_execution_ticket(
        factory, server_id=server, executor_id=executor, agent_id='subject',
        binding_id='binding',
        scopes=frozenset({'lane:attach', 'lease:request', 'receipt:publish'}),
        client_intent_id='retained-lane', credential_request_id='second',
        replaces_ticket_id=ticket.ticket_id,
    )
    assert successor.ticket_id != ticket.ticket_id
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute(
            'SELECT revoked_at FROM execution_link_tickets WHERE ticket_id=?',
            (ticket.ticket_id,),
        ).fetchone()[0] is not None
