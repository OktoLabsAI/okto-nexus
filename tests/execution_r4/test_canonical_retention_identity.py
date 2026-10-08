"""Retention and agent activation cannot discard canonical delivery claims."""
import time

import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_canonical_consumption import pull


@pytest.mark.parametrize('uncertain', [False, True])
def test_prune_and_reactivation_preserve_canonical_transport_exclusion(connected_local, monkeypatch, uncertain):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    enable(setup, binding)
    pump = app.state.embedded_dispatch_owner.pump
    if uncertain:
        from test_vertical_inventory import _Native
        original = _Native.send
        async def lost_reply(*args, **kwargs):
            await original(*args, **kwargs)
            raise OSError('Native write outcome lost')
        monkeypatch.setattr(_Native, 'send', lost_reply)
    else:
        client.portal.call(pump.send_lock.acquire)
    try:
        source = send(setup, monkeypatch)
        assert source['ok'], source
        with deps.connection_factory.unit_of_work(write=False) as uow:
            turn = dict(uow.connection.execute("SELECT operation_id,session_id FROM execution_operations WHERE action='turn.submit'").fetchone())
        if uncertain:
            wait_receipt(setup, turn, stages=('OUTCOME_UNKNOWN', 'FAILED'))
            # The receipt precedes independent resource release and its durable
            # delivery projection. Snapshot after that legitimate transition,
            # so retention is not compared against an in-flight recovery row.
            deadline = time.monotonic() + 30
            while True:
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    released = uow.connection.execute(
                        "SELECT status,reason FROM delivery_outbox").fetchone()
                if tuple(released) == ('OUTCOME_UNKNOWN', 'session_released_without_result'):
                    break
                assert time.monotonic() < deadline, tuple(released)
                time.sleep(.02)
        with deps.connection_factory.unit_of_work() as uow:
            message = uow.connection.execute('SELECT message_id,workspace_id FROM delivery_outbox').fetchone()
            uow.connection.execute("UPDATE messages SET created_at='2000-01-01T00:00:00Z' WHERE message_id=?", (message[0],))
            deps.repos.messages.create(uow, message_id='unrelated-expired', workspace_id=message[1],
                from_agent_id='operator', created_at='2000-01-01T00:00:00Z')
            tables = ('delivery_outbox', 'message_deliveries', 'execution_domain_deliveries')
            before = {t: [tuple(r) for r in uow.connection.execute('SELECT * FROM ' + t)] for t in tables}
        disabled = client.patch('/api/v1/agents/subject', headers=headers['operator'], json={'is_active': False})
        assert disabled.status_code == 200, disabled.text
        for _ in range(2):
            pruned = client.post('/api/v1/admin/prune?dry_run=false', headers=headers['operator'])
            assert pruned.status_code == 200, pruned.text
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT 1 FROM messages WHERE message_id=?', (message[0],)).fetchone()
            assert not uow.connection.execute("SELECT 1 FROM messages WHERE message_id='unrelated-expired'").fetchone()
            assert before == {t: [tuple(r) for r in uow.connection.execute('SELECT * FROM ' + t)] for t in tables}
            assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []
        assert client.patch('/api/v1/agents/subject', headers=headers['operator'], json={'is_active': True}).status_code == 200
        assert pull(setup, monkeypatch) == []
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT operation_id FROM execution_operations WHERE action='turn.submit'").fetchall()[0][0] == turn['operation_id']
            assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 1
        assert len(native.native.sent) == int(uncertain)
    finally:
        if not uncertain:
            client.portal.call(pump.send_lock.release)


def test_pruning_does_not_forget_canonical_command_idempotency(connected_local, monkeypatch):
    from test_canonical_grant_regressions import open_scoped, invoke_command
    from test_embedded_dispatch import admit
    setup, binding, native, _, sid = open_scoped(connected_local)
    deps, _, client, headers, *_ = setup
    args = dict(payload=dict(text='Retain this command'), idempotency_key='retained-command')
    first = invoke_command(setup, monkeypatch, 'rest', sid, args)
    assert first['ok'], first
    operation = first['data']['operation_id']
    wait_receipt(setup, first['data'])
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_operations SET created_at='2000-01-01T00:00:00Z' WHERE operation_id=?", (operation,))
        before = tuple(uow.connection.execute('SELECT * FROM execution_operations WHERE operation_id=?', (operation,)).fetchone())
    assert client.patch('/api/v1/agents/subject', headers=headers['operator'], json={'is_active': False}).status_code == 200
    denied = invoke_command(setup, monkeypatch, 'rest', sid, args)
    assert not denied['ok'] and denied['error']['code'] == 'AUTH_FAILED', denied
    denied_operator = client.post('/api/v1/harness/sessions/' + sid + '/send',
        headers=headers['operator'], json={**args, 'idempotency_key': 'inactive-new-command'})
    assert denied_operator.status_code == 403, denied_operator.text
    viewed = client.get('/api/v1/harness/sessions/' + sid, headers=headers['operator'])
    assert viewed.status_code == 200, viewed.text
    assert client.post('/api/v1/admin/prune?dry_run=false', headers=headers['operator']).status_code == 200
    assert client.patch('/api/v1/agents/subject', headers=headers['operator'], json={'is_active': True}).status_code == 200
    repeated = invoke_command(setup, monkeypatch, 'mcp', sid, args)
    assert repeated['ok'] and repeated['data']['operation_id'] == operation, repeated
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert tuple(uow.connection.execute('SELECT * FROM execution_operations WHERE operation_id=?', (operation,)).fetchone()) == before
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 1
    assert len(native.native.sent) == 1
    wait_receipt(setup, admit(setup, binding, 'retained-command-close', 'runtime.close', session_id=sid), stages=('SUCCEEDED',))
