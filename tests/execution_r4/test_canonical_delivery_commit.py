"""Every logical write rolls back with canonical admission; wakes are advisory."""
import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_canonical_result_publication import current_turn


@pytest.mark.parametrize('cut', ['message', 'delivery', 'outbox', 'event'])
def test_each_logical_write_rolls_back_domain_and_execution_then_recovers(connected_local, monkeypatch, cut):
    from okto_nexus.adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
    setup, binding, native = connected_local
    deps = setup[0]
    enable(setup, binding)
    tables = ('messages', 'message_deliveries', 'delivery_outbox', 'events',
        'runtime_causal_roots', 'runtime_message_causality', 'execution_operations',
        'execution_dispatch_outbox', 'execution_sessions', 'execution_domain_deliveries')
    def counts(uow):
        return {table: uow.connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in tables}
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = counts(uow)
    targets = dict(message=(deps.repos.messages, 'create', 'messages'),
        delivery=(deps.repos.deliveries, 'create', 'message_deliveries'),
        outbox=(SqliteRuntimeOutboxRepo, 'enqueue', 'delivery_outbox'),
        event=(deps.event_emitter, 'emit', 'events'))
    target, method, table = targets[cut]
    original = getattr(target, method)
    reached = []
    def fail(*args, **kwargs):
        result = original(*args, **kwargs)
        if cut == 'event' and kwargs.get('type') != 'message.created':
            return result
        uow = args[1] if cut == 'outbox' else args[0]
        assert counts(uow)[table] == before[table] + 1
        reached.append(True)
        raise OSError('Failure after committed-to-transaction logical write')
    with monkeypatch.context() as patch:
        patch.setattr(target, method, fail)
        response = send(setup, patch)
    assert not response['ok'] and reached == [True], response
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert counts(uow) == before
        assert not uow.connection.execute('PRAGMA foreign_key_check').fetchall()
    assert native.opens == 0
    assert send(setup, monkeypatch)['ok']
    wait_receipt(setup, current_turn(setup))
    assert native.opens == 1 and len(native.native.sent) == 1


def test_dropped_commit_wakes_do_not_strand_pending_message(connected_local, monkeypatch):
    from okto_nexus.adapters.inbound.mcp.tools import messages
    from okto_nexus.application.messages import MessageService
    setup, binding, native = connected_local
    enable(setup, binding)
    owner = setup[1].state.embedded_dispatch_owner
    channel = owner.channel
    wakes = []
    monkeypatch.setattr(messages, 'wake_runtime', lambda _: wakes.append('dropped'))
    monkeypatch.setattr(MessageService, '_maybe_notify_inbox_subscribers', lambda *a, **k: None)
    response = send(setup, monkeypatch)
    assert response['ok'] and wakes, response
    # No explicit pump wake/scan or server restart follows the committed write.
    wait_receipt(setup, current_turn(setup))
    assert native.opens == 1 and len(native.native.sent) == 1
    assert owner.channel == channel and owner.pump.error is None
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        for table in ('messages', 'message_deliveries', 'delivery_outbox'):
            assert uow.connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] == 1
