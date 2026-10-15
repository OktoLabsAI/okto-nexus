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


@pytest.mark.parametrize('phase', ['admitted', 'accepted', 'terminal', 'closed'])
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
        if phase == 'terminal':
            from test_canonical_result_publication import emit, wait_result
            emit(setup, native, turn, 'One completed answer')
            result = wait_result(setup, 'PUBLISHED')
            assert result['canonical_operation_id'] == turn['operation_id']
            # Publication and processing receipts are independent projections.
            # Wait for the background consumer, without acknowledging manually.
            import time
            deadline = time.monotonic() + 10
            while True:
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    status = uow.connection.execute('SELECT status FROM message_deliveries WHERE message_id=?',
                        (created['data']['message_id'],)).fetchone()[0]
                if status == 'read':
                    break
                assert time.monotonic() < deadline, status
                time.sleep(.02)
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


def test_lost_confirmation_and_expired_lease_preserve_push_claim(connected_local, monkeypatch):
    from test_vertical_inventory import _Native
    from test_canonical_delivery_retry import wait_delivery
    setup, binding, native = connected_local
    enable(setup, binding)
    original = _Native.send
    async def uncertain(peer, verb, payload, operation_id, **kwargs):
        await original(peer, verb, payload, operation_id, **kwargs)
        raise OSError('Confirmation lost after native effect')
    monkeypatch.setattr(_Native, 'send', uncertain)
    assert send(setup, monkeypatch)['ok']
    unknown = wait_delivery(setup, lambda row: row['status'] == 'OUTCOME_UNKNOWN')
    deps = setup[0]
    with deps.connection_factory.unit_of_work() as uow:
        before = tuple(uow.connection.execute('SELECT consumer_kind,consumer_operation_id,attempts '
            'FROM message_deliveries WHERE delivery_id=?', (unknown['delivery_id'],)).fetchone())
        uow.connection.execute("UPDATE delivery_outbox SET lease_expires_at='2000-01-01T00:00:00Z' WHERE operation_id=?",
            (unknown['operation_id'],))
    assert before[:2] == ('push', unknown['operation_id'])
    for _ in range(3):
        deps.runtime_dispatcher.scan_once()
        assert pull(setup, monkeypatch) == []
    with deps.connection_factory.unit_of_work(write=False) as uow:
        after = uow.connection.execute('SELECT status,attempt_id,attempt_count FROM delivery_outbox').fetchone()
        assert tuple(after) == ('OUTCOME_UNKNOWN', unknown['attempt_id'], 1)
        assert tuple(uow.connection.execute('SELECT consumer_kind,consumer_operation_id,attempts '
            'FROM message_deliveries WHERE delivery_id=?', (unknown['delivery_id'],)).fetchone()) == before
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 1
    assert native.opens == 1 and len(native.native.sent) == 1


@pytest.mark.parametrize('local_setup', ['pi_rpc', 'codex_app_server', 'claude_stream'], indirect=True)
@pytest.mark.parametrize('surface', ['rest', 'mcp'])
@pytest.mark.parametrize('action', ['create', 'update'])
def test_unsafe_mirror_configuration_is_atomic_and_does_not_disable_delivery(connected_local, monkeypatch, surface, action):
    from test_runtime_contract_migration import mcp
    setup, binding, native = connected_local
    deps, _, client, headers, *_, root = setup
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = dict(uow.connection.execute('SELECT * FROM agent_endpoints WHERE endpoint_id=?',
            (binding['endpoint_id'],)).fetchone())
    endpoint = 'unsafe-mirror' if action == 'create' else binding['endpoint_id']
    body = dict(consumption='mirror_only')
    if action == 'create':
        body.update(endpoint_id=endpoint, agent_id='subject', adapter_id=before['adapter_id'],
                    project_root=str(root), enabled=True, response_policy='conversation')
    else:
        body['expected_revision'] = before['revision']
    if surface == 'rest':
        response = (client.post('/api/v1/harness/endpoints', headers=headers['operator'], json=body)
            if action == 'create' else client.patch('/api/v1/harness/endpoints/' + endpoint,
                                                   headers=headers['operator'], json=body))
        assert response.status_code == 422, response.text
        refused = response.json()
    else:
        refused = mcp(setup, monkeypatch, headers['operator']['Authorization'].removeprefix('Bearer '),
            'harness_list', dict(view='endpoints', maintenance=dict(**body, action=action,
                **({} if action == 'create' else {'endpoint_id': endpoint}))))
    assert not refused['ok'] and refused['error']['code'] == 'VALIDATION_ERROR', refused
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert dict(uow.connection.execute('SELECT * FROM agent_endpoints WHERE endpoint_id=?',
            (binding['endpoint_id'],)).fetchone()) == before
        assert not uow.connection.execute("SELECT 1 FROM agent_endpoints WHERE endpoint_id='unsafe-mirror'").fetchone()
    assert native.opens == 0
    assert send(setup, monkeypatch)['ok']
    from test_canonical_result_publication import current_turn
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    assert native.opens == 1 and len(native.native.sent) == 1
    wait_receipt(setup, admit(setup, binding, 'mirror-denial-close', 'runtime.close',
        session_id=turn['session_id']), stages=('SUCCEEDED',))


def test_two_refused_sockets_preserve_inbox_claim_across_three_bindings(connected_local, monkeypatch):
    import asyncio
    import socket
    from nexus_connector_core.models import EffectNotSent
    from test_vertical_inventory import _Native
    from test_canonical_identity_lifecycle import second_binding
    from test_canonical_delivery_retry import wait_delivery
    setup, first, native = connected_local
    second = second_binding(setup, monkeypatch)
    third = second_binding(setup, monkeypatch, name='third', adapter_id='claude_stream')
    deps = setup[0]
    bindings = (first, second, third)
    for index, binding in enumerate(bindings):
        enable(setup, binding)
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agent_endpoints SET selection_group='socket-equivalents',priority=? WHERE endpoint_id=?",
                (30-index, binding['endpoint_id']))
    clock = [deps.clock.now_iso()]
    monkeypatch.setattr(deps.clock, 'now_iso', lambda: clock[0])
    calls = []
    original = _Native.send
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        address = reserved.getsockname()
        def refuse():
            with socket.socket() as connection:
                connection.settimeout(5)
                try:
                    connection.connect(address)
                except ConnectionRefusedError:
                    raise EffectNotSent('Socket refused before write', code='CAPACITY_EXCEEDED') from None
            pytest.fail('Non-listening fixture socket accepted a connection')
        async def write(peer, verb, payload, operation_id, **kwargs):
            calls.append(operation_id)
            if len(calls) <= 2:
                await asyncio.to_thread(refuse)
            return await original(peer, verb, payload, operation_id, **kwargs)
        monkeypatch.setattr(_Native, 'send', write)
        assert send(setup, monkeypatch)['ok']
        pending = wait_delivery(setup, lambda row: row['status'] == 'RETRY_WAIT')
        def claim():
            with deps.connection_factory.unit_of_work(write=False) as uow:
                return tuple(uow.connection.execute('SELECT attempts,lease_expires_at,status,consumer_kind,consumer_operation_id '
                    'FROM message_deliveries WHERE delivery_id=?', (pending['delivery_id'],)).fetchone())
        before = claim()
        assert before == (0, None, 'unread', 'push', pending['operation_id'])
        for attempt in (2, 3):
            clock[0] = pending['next_attempt_at']
            deps.runtime_dispatcher.wake()
            pending = wait_delivery(setup, lambda row: row['attempt_count'] == attempt and
                row['status'] == ('RETRY_WAIT' if attempt == 2 else 'ACCEPTED'))
            after = claim()
            # Acceptance can mark delivery, but never consume a pull attempt/lease.
            assert after[:2] == before[:2] and after[3:] == before[3:]
            if attempt == 2:
                assert after == before
        assert pending['endpoint_id'] == third['endpoint_id']
        assert len(calls) == len(set(calls)) == 3
        assert native.opens == 3 and len(native.native.sent) == 1
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT COUNT(*) FROM message_deliveries').fetchone()[0] == 1
            assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1
            # Superseded attempts are archived; the current one stays in outbox.
            assert {r[0] for r in uow.connection.execute('SELECT endpoint_id FROM execution_delivery_attempt_history')} == {b['endpoint_id'] for b in bindings[:2]}
            assert {r[0] for r in uow.connection.execute('SELECT endpoint_id FROM execution_delivery_attempt_history UNION SELECT endpoint_id FROM delivery_outbox')} == {b['endpoint_id'] for b in bindings}


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
