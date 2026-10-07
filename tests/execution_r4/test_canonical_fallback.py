"""Retained legacy endpoints cannot regain execution authority or claim messages."""
import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_delivery_selection import legacy
from test_canonical_consumption import pull


@pytest.mark.parametrize('priority', [1, 10, 99])
def test_retained_legacy_endpoint_never_bypasses_canonical_delivery(
        connected_local, monkeypatch, priority):
    setup, binding, native = connected_local
    deps = setup[0]
    enable(setup, binding)
    legacy(setup, binding, priority=priority, group='reviewed-equivalence')
    calls = []
    def forbidden(operation):
        calls.append(operation['endpoint_id'])
        raise AssertionError('Retired transport must not receive native work')
    monkeypatch.setattr(deps.runtime_dispatcher, 'dispatch', forbidden)
    assert send(setup, monkeypatch)['ok']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        delivery = uow.connection.execute(
            'SELECT endpoint_id,operation_id FROM delivery_outbox').fetchone()
        assert delivery[0] == binding['endpoint_id']
        assert uow.connection.execute(
            'SELECT consumer_kind,consumer_operation_id FROM message_deliveries').fetchone()[:] == ('push', delivery[1])
        turn = dict(uow.connection.execute(
            "SELECT operation_id,session_id FROM execution_operations WHERE action='turn.submit'").fetchone())
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1
        assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []
    wait_receipt(setup, turn)
    assert calls == []
    assert native.opens == 1 and len(native.native.sent) == 1
    assert pull(setup, monkeypatch) == []
    wait_receipt(setup, admit(setup, binding, 'canonical-close', 'runtime.close',
        session_id=turn['session_id']), stages=('SUCCEEDED',))
