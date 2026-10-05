"""Canonical push and MCP pull share the existing logical inbox claim."""
from pathlib import Path

import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_canonical_handoff import prepare


def pull(setup, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    _, _, client, headers, *_ = setup
    result = tool(client, headers['subject']['Authorization'].removeprefix('Bearer '),
                  'inbox_pull', {'agent_id': 'subject'})
    assert result['ok'], result
    return result['data']['messages']


@pytest.mark.parametrize('phase', ['admitted', 'accepted', 'closed'])
def test_canonical_push_reservation_excludes_mcp_pull(connected_local, monkeypatch, phase):
    setup, binding, native = connected_local
    enable(setup, binding)
    deps, app, client, *_ = setup
    lock = app.state.embedded_dispatch_owner.pump.send_lock
    if phase == 'admitted':
        client.portal.call(lock.acquire)
    try:
        created = send(setup, monkeypatch)
        assert created['ok'], created
        with deps.connection_factory.unit_of_work(write=False) as uow:
            turn = dict(uow.connection.execute(
                "SELECT operation_id,session_id FROM execution_operations WHERE action='turn.submit'").fetchone())
            before = tuple(uow.connection.execute(
                'SELECT consumer_kind,consumer_operation_id,attempts FROM message_deliveries').fetchone())
            assert before[0] == 'push'
        if phase != 'admitted':
            wait_receipt(setup, turn)
        if phase == 'closed':
            closed = admit(setup, binding, 'consumption-close', 'runtime.close', session_id=turn['session_id'])
            wait_receipt(setup, closed, stages=('SUCCEEDED',))
        assert pull(setup, monkeypatch) == []
        assert pull(setup, monkeypatch) == []
        with deps.connection_factory.unit_of_work(write=False) as uow:
            after = tuple(uow.connection.execute(
                'SELECT consumer_kind,consumer_operation_id,attempts FROM message_deliveries').fetchone())
            assert after == before
            assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1
            assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 1
        if phase == 'admitted':
            assert native.opens == 0
    finally:
        if phase == 'admitted':
            client.portal.call(lock.release)
    if phase != 'closed':
        wait_receipt(setup, turn)
        closed = admit(setup, binding, 'consumption-close', 'runtime.close', session_id=turn['session_id'])
        wait_receipt(setup, closed, stages=('SUCCEEDED',))
    assert native.opens == 1 and len(native.native.sent) == 1


@pytest.mark.parametrize('first', ['pull', 'runtime', 'concurrent'])
def test_handoff_pull_and_runtime_compete_for_one_claim(connected_local, monkeypatch, first):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    setup, binding, native = connected_local
    handoff, grant, runtime_claim, call = prepare(setup, binding, monkeypatch)
    def pull_claim():
        return call('handoff_claim', handoff_id=handoff, agent_id='subject', idempotency_key='pull-work')
    if first == 'concurrent':
        gate = Barrier(2)
        def race(fn):
            gate.wait(timeout=10)
            return fn()
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(race, pull_claim), pool.submit(race, runtime_claim)
            results = [a.result(), b.result()]
    else:
        calls = [pull_claim, runtime_claim] if first == 'pull' else [runtime_claim, pull_claim]
        results = [fn() for fn in calls]
    assert sum(bool(r['ok']) for r in results) == 1, results
    deps = setup[0]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status,claimed_by,claim_epoch FROM handoffs WHERE handoff_id=?',
                                      (handoff,)).fetchone()[:] == ('CLAIMED', 'subject', 1)
        turns = [dict(r) for r in uow.connection.execute(
            "SELECT operation_id,session_id FROM execution_operations WHERE action='turn.submit'")]
        count = len(turns)
        assert count <= 1
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_handoff_bindings').fetchone()[0] == count
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?',
                                      (grant,)).fetchone()[0] == count
    if turns:
        wait_receipt(setup, turns[0])
        closed = admit(setup, binding, 'race-close', 'runtime.close', session_id=turns[0]['session_id'])
        wait_receipt(setup, closed, stages=('SUCCEEDED',))
    assert native.opens == count
