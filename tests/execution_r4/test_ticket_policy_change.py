from datetime import datetime, timedelta, timezone

import pytest
from test_ns09 import setup_authority
from okto_nexus.adapters.outbound.sqlite.execution_tickets import issue_execution_ticket, TicketRequestConflict


@pytest.mark.parametrize('changed', [False, True])
def test_only_invalidated_ticket_stops_blocking_fresh_authority(tmp_path, monkeypatch, changed):
    setup = setup_authority(tmp_path, monkeypatch)
    deps, _, _, _, _, _, _, _, _, old_ticket, server, executor = setup
    if changed:
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agent_endpoints SET revision=revision+1 WHERE endpoint_id='ep'")
    args = dict(server_id=server, executor_id=executor, agent_id='subject', binding_id='binding',
        scopes=frozenset({'lane:attach','lease:request'}),client_intent_id='new-policy',credential_request_id='new-credential')
    if not changed:
        with pytest.raises(TicketRequestConflict) as caught:
            issue_execution_ticket(deps.connection_factory, **args)
        assert caught.value.code == 'CREDENTIAL_REPLACEMENT_REQUIRED'
        return
    fresh = issue_execution_ticket(deps.connection_factory, **args)
    assert fresh.authorization_revision > setup[7].authorization
    with deps.connection_factory.unit_of_work(write=False) as uow:
        tickets = uow.connection.execute('SELECT ticket_id,revoked_at FROM execution_link_tickets '
            "WHERE binding_id='binding'").fetchall()
        assert len(tickets) == 2
        assert all(r['revoked_at'] is not None for r in tickets if r['ticket_id'] != fresh.ticket_id)


def test_expired_bound_ticket_can_be_replaced_without_replaying_authority(tmp_path, monkeypatch):
    deps, _, _, _, _, _, _, _, _, _, server, executor = setup_authority(tmp_path, monkeypatch)
    factory = deps.connection_factory
    started = datetime.now(timezone.utc)
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "UPDATE execution_link_tickets SET revoked_at=? WHERE binding_id='binding'",
            (started.isoformat(),),
        )
    args = dict(server_id=server, executor_id=executor, agent_id='subject',
                binding_id='binding',
                scopes=frozenset({'lane:attach', 'lease:request', 'receipt:publish'}),
                client_intent_id='durable-intent', expires_in=600)
    first = issue_execution_ticket(factory, **args,
                                   credential_request_id='first', now=started)
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            'UPDATE execution_link_tickets SET bound_connection_id=? WHERE ticket_id=?',
            ('old-server-socket', first.ticket_id),
        )
    replacement = issue_execution_ticket(
        factory, **args, credential_request_id='second',
        replaces_ticket_id=first.ticket_id,
        now=started + timedelta(seconds=601),
    )
    assert replacement.ticket_id != first.ticket_id
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute(
            'SELECT revoked_at FROM execution_link_tickets WHERE ticket_id=?',
            (first.ticket_id,),
        ).fetchone()[0] is not None
