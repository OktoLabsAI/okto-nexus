import time

import pytest

from test_embedded_dispatch import local_setup, connected_local, qualified_contract, wait_receipt
from test_sender_sessions import Peers, configure, sender, turn_for, complete
from okto_nexus.application.one_shot_runtime import tick


def wait_until(setup, condition):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        tick(setup[0])
        if condition():
            return
        time.sleep(.05)
    assert condition()


def query(setup, sql, args=()):
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        return uow.connection.execute(sql, args).fetchall()


@pytest.mark.parametrize('local_setup', ['pi_rpc', 'codex_app_server', 'claude_stream'], indirect=True)
def test_parallel_warmup_assigns_first_ready_instance_to_oldest_caller(connected_local, monkeypatch):
    import asyncio
    import threading
    from okto_nexus.application.one_shot_settings import read, save
    release_all = threading.Event()
    entered = {}

    class HeldWarmup(Peers):
        async def open(self, prepared, session_id, context, *, stream_epoch):
            release = entered.setdefault(session_id, threading.Event())
            while not release.is_set() and not release_all.is_set():
                await asyncio.sleep(.01)
            return await super().open(prepared, session_id, context, stream_epoch=stream_epoch)

    setup, binding, _ = connected_local
    peers = HeldWarmup()
    setup[1].state.embedded_dispatch_owner.native_factory = peers
    configure(setup, binding, 'one_shot')
    with setup[0].connection_factory.unit_of_work() as uow:
        current = read(uow.connection)
        save(uow.connection, expected_revision=current['revision'],
             settings=current['settings'] | {'max_parallel': 5, 'warm_instances': 4})
    send = sender(setup, monkeypatch)
    try:
        tick(setup[0])
        assert len(query(setup, 'SELECT * FROM one_shot_slots')) == 4
        # All four native opens enter before ANY is allowed to finish.
        wait_until(setup, lambda: len(entered) == 4)
        original = list(entered)
        messages = [send('operator', f'partial warmup {i}') for i in range(4)]
        assert not query(setup, "SELECT * FROM one_shot_slots WHERE call_id IS NOT NULL")
        turns = []
        for message, session in zip(messages, reversed(original)):
            entered[session].set()
            turn = turn_for(setup, message)
            wait_receipt(setup, turn)
            assert turn['session_id'] == session
            turns.append(turn)
        assert len(query(setup, "SELECT * FROM one_shot_calls WHERE state='RUNNING'")) == 4
        for turn in turns:
            complete(setup, peers, turn, 'independent response')
        wait_until(setup, lambda: len(query(setup, "SELECT * FROM one_shot_calls WHERE state='SUCCEEDED'")) == 4)
    finally:
        release_all.set()
    wait_until(setup, lambda: len(query(setup, "SELECT * FROM one_shot_slots WHERE state='WARM'")) == 4)


@pytest.mark.parametrize('local_setup', ['pi_rpc', 'codex_app_server', 'claude_stream'], indirect=True)
def test_slow_refill_cannot_block_ready_sessions(connected_local, monkeypatch):
    import asyncio
    import threading
    from okto_nexus.application.one_shot_settings import read, save
    release = threading.Event()
    blocked = []

    class SlowRefill(Peers):
        hold = False

        async def open(self, prepared, session_id, context, *, stream_epoch):
            if self.hold:
                blocked.append(session_id)
                while not release.is_set():
                    await asyncio.sleep(.02)
            return await super().open(prepared, session_id, context, stream_epoch=stream_epoch)

    setup, binding, _ = connected_local
    peers = SlowRefill()
    setup[1].state.embedded_dispatch_owner.native_factory = peers
    configure(setup, binding, 'one_shot')
    with setup[0].connection_factory.unit_of_work() as uow:
        current = read(uow.connection)
        save(uow.connection, expected_revision=current['revision'],
             settings=current['settings'] | {'max_parallel': 6, 'warm_instances': 4})
    send = sender(setup, monkeypatch)
    wait_until(setup, lambda: query(setup, "SELECT count(*) FROM one_shot_slots WHERE state='WARM'")[0][0] == 4)
    original = {r[0] for r in query(setup, "SELECT session_id FROM one_shot_slots WHERE state='WARM'")}
    peers.hold = True
    try:
        turns = []
        for index in range(4):
            turns.append(turn_for(setup, send('operator', f'independent {index}')))
            if index < 2:
                wait_until(setup, lambda: len(blocked) >= index + 1)
        assert len(blocked) == 2, 'Exercise both occupied opening workers'
        for turn in turns:
            wait_receipt(setup, turn)
        assert {turn['session_id'] for turn in turns} == original
        assert not release.is_set()
        assert query(setup, "SELECT count(*) FROM one_shot_calls WHERE state='RUNNING'")[0][0] == 4
        for index, turn in enumerate(turns):
            complete(setup, peers, turn, f'response {index}')
        wait_until(setup, lambda: query(setup, "SELECT count(*) FROM one_shot_calls WHERE state='SUCCEEDED'")[0][0] == 4)
        assert not query(setup, "SELECT * FROM execution_agent_recovery WHERE state<>'READY'")
    finally:
        release.set()
    peers.hold = False
    wait_until(setup, lambda: query(setup, "SELECT count(*) FROM one_shot_slots WHERE state='WARM'")[0][0] == 4)


@pytest.mark.parametrize('local_setup', ['pi_rpc'], indirect=True)
@pytest.mark.parametrize('defer_release', [False, True])
def test_warm_parallel_stream_failure_preserves_siblings_and_replenishes(connected_local, monkeypatch, defer_release):
    from test_vertical_inventory import _Native
    from okto_nexus.application.one_shot_settings import read, save
    from nexus_connector_core.native.event_buffers import NativeEventOverflow

    class Faultable(_Native):
        async def events(self):
            async for event in super().events():
                if isinstance(event, Exception):
                    raise event
                yield event

    class Factory(Peers):
        async def open(self, prepared, session_id, context, *, stream_epoch):
            peer = Faultable()
            self.sessions[session_id] = peer
            return peer

    setup, binding, _ = connected_local
    owner = setup[1].state.embedded_dispatch_owner
    peers = Factory()
    owner.native_factory = peers
    configure(setup, binding, 'one_shot')
    with setup[0].connection_factory.unit_of_work() as uow:
        current = read(uow.connection)
        save(uow.connection, expected_revision=current['revision'],
             settings=current['settings'] | {'max_parallel': 5, 'warm_instances': 4})
    send = sender(setup, monkeypatch)
    wait_until(setup, lambda: query(setup, "SELECT count(*) FROM one_shot_slots WHERE state='WARM'")[0][0] == 4)
    original = {r[0] for r in query(setup, "SELECT session_id FROM one_shot_slots WHERE state='WARM'")}
    turns = [turn_for(setup, send('operator', f'parallel {i}')) for i in range(4)]
    for turn in turns:
        wait_receipt(setup, turn)
    assert {turn['session_id'] for turn in turns} == original
    failed = turns[0]
    from okto_nexus.bootstrap.embedded_reconciliation import EmbeddedReconciliation
    from nexus_connector_core import CoreError
    original_release = EmbeddedReconciliation.release_session
    release_attempts = []
    async def release(reconciliation, session_id, **kwargs):
        if session_id == failed['session_id'] and defer_release:
            release_attempts.append(session_id)
            raise CoreError('RECONCILIATION_REQUIRED', 'test_release')
        return await original_release(reconciliation, session_id, **kwargs)
    monkeypatch.setattr(EmbeddedReconciliation, 'release_session', release)
    setup[2].portal.call(peers.sessions[failed['session_id']].queue.put, NativeEventOverflow())
    if defer_release:
        wait_until(setup, lambda: release_attempts)
    else:
        wait_until(setup, lambda: query(setup, "SELECT count(*) FROM one_shot_calls WHERE state='FAILED'")[0][0] == 1)
    assert 'subject' not in owner.agents.blocked
    for turn in turns[1:]:
        assert not peers.sessions[turn['session_id']].stopped
        complete(setup, peers, turn, 'sibling finished')
    wait_until(setup, lambda: query(setup, "SELECT count(*) FROM one_shot_calls WHERE state='SUCCEEDED'")[0][0] == 3)
    defer_release = False
    wait_until(setup, lambda: query(setup, "SELECT count(*) FROM one_shot_calls WHERE state='FAILED'")[0][0] == 1)
    wait_until(setup, lambda: query(setup, "SELECT count(*) FROM one_shot_slots WHERE state='WARM'")[0][0] == 4)
    assert owner.failure is None
    assert len(peers.sessions[failed['session_id']].sent) == 1, 'Uncertain turn must never replay'
    # The same agent accepts another call after its failed session is contained.
    again = turn_for(setup, send('operator', 'after fault'))
    wait_receipt(setup, again)
    complete(setup, peers, again, 'restored')


def test_shutdown_fence_prevents_warm_replenishment(connected_local):
    from okto_nexus.application.one_shot_settings import read, save
    setup, binding, _ = connected_local
    configure(setup, binding, 'one_shot')
    with setup[0].connection_factory.unit_of_work() as uow:
        current = read(uow.connection)
        save(uow.connection, expected_revision=current['revision'],
             settings=current['settings'] | {'max_parallel': 2, 'warm_instances': 1})
    setup[0].runtime_admission_fence.close()
    try:
        tick(setup[0])
        assert not query(setup, 'SELECT * FROM one_shot_slots')
        assert not query(setup, 'SELECT * FROM one_shot_warm_backoff')
    finally:
        setup[0].runtime_admission_fence.reopen_after_reset()


def test_failed_preopen_without_receipt_releases_warm_slot_and_refills(connected_local, monkeypatch):
    from nexus_connector_core import LocalRuntimeCore, CoreError
    from okto_nexus.application.one_shot_settings import read, save
    from test_agent_recovery_isolation import eventually
    setup, binding, _ = connected_local
    owner = setup[1].state.embedded_dispatch_owner
    peers = Peers()
    owner.native_factory = peers
    original = LocalRuntimeCore.prepare
    failures = []
    async def fail_once(runtime, *args, **kwargs):
        if not failures:
            failures.append(True)
            raise CoreError('BINDING_NOT_AUTHORIZED', 'prepare')
        return await original(runtime, *args, **kwargs)
    monkeypatch.setattr(LocalRuntimeCore, 'prepare', fail_once)
    configure(setup, binding, 'one_shot')
    with setup[0].connection_factory.unit_of_work() as uow:
        current = read(uow.connection)
        save(uow.connection, expected_revision=current['revision'],
             settings=current['settings'] | {'max_parallel':2,'warm_instances':1})
    def replenished():
        tick(setup[0])
        return query(setup, "SELECT count(*) FROM one_shot_slots WHERE state='WARM'")[0][0] == 1
    eventually(replenished, seconds=45)
    failed = query(setup, "SELECT session_id,open_operation_id,lease_state FROM execution_sessions WHERE lifecycle_state='FAILED'")
    assert len(failed) == 1 and failed[0]['lease_state'] == 'CLOSED'
    assert not query(setup, 'SELECT * FROM execution_receipts WHERE operation_id=?', (failed[0]['open_operation_id'],))
    assert not query(setup, 'SELECT * FROM one_shot_slots WHERE session_id=?', (failed[0]['session_id'],))
    assert len(peers.sessions) == 1 and not owner.agents.blocked


def test_host_budget_retains_failed_resources_without_disposal_proof():
    import sqlite3
    from okto_nexus.application.one_shot_runtime import host_limit
    conn = sqlite3.connect(':memory:')
    try:
        conn.executescript('CREATE TABLE one_shot_host_limits(executor_id,max_instances); '
            'CREATE TABLE execution_sessions(executor_id,session_id,lifecycle_state,lease_state); '
            'CREATE TABLE one_shot_slots(executor_id,session_id); '
            "INSERT INTO one_shot_host_limits VALUES('host',4); "
            "INSERT INTO execution_sessions VALUES('host','uncertain','FAILED','ACTIVE'),"
            "('host','disposed','FAILED','CLOSED'),('host','tracked','READY','ACTIVE'); "
            "INSERT INTO one_shot_slots VALUES('host','tracked');")
        assert host_limit(conn, 'host') == 3
    finally:
        conn.close()


def test_broadcast_capacity_refusal_preserves_other_recipient(connected_local, monkeypatch):
    from test_agent_recovery_isolation import create_agent
    from test_embedded_dispatch import connect_local
    from test_canonical_delivery import enable
    from pathlib import Path
    from okto_nexus.application.one_shot_settings import read, save
    setup, binding, _ = connected_local
    other_setup = create_agent(setup, 'other')
    other_setup[4]['workspace_id'] = query(setup, 'SELECT workspace_id FROM agent_endpoints WHERE endpoint_id=?',
                                         (binding['endpoint_id'],))[0][0]
    other_setup, other_binding, _ = connect_local(other_setup, agent_id='other')
    peers = Peers()
    setup[1].state.embedded_dispatch_owner.native_factory = peers
    configure(setup, binding, 'one_shot')
    enable(other_setup, other_binding)
    with setup[0].connection_factory.unit_of_work() as uow:
        current = read(uow.connection)
        save(uow.connection, expected_revision=current['revision'],
            settings=current['settings'] | {'overflow': 'reject'})
        workspace = uow.connection.execute('SELECT workspace_id FROM agent_endpoints WHERE endpoint_id=?',
            (binding['endpoint_id'],)).fetchone()[0]
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    setup[2].headers['host'] = '127.0.0.1:8000'
    def send(setup, monkeypatch, target=None):
        return tool(setup[2], setup[3]['operator']['Authorization'].removeprefix('Bearer '), 'message_create',
            dict(workspace_id=workspace, from_agent_id='operator', subject='Capacity', body='Handle this call',
                 target=target or dict(strategy='direct', agent_id='subject')))
    initial = send(setup, monkeypatch)
    assert initial['ok'], initial
    wait_receipt(setup, turn_for(setup, initial['data']['message_id']))
    direct = send(setup, monkeypatch)
    assert not direct['ok'] and direct['error']['details']['code'] == 'ONE_SHOT_CAPACITY_EXCEEDED'
    broadcast = send(setup, monkeypatch, target={'strategy': 'broadcast'})
    assert broadcast['ok'], broadcast
    assert broadcast['data']['recipients'] == ['other']
    assert broadcast['data']['delivered_count'] == 1
    rejected = broadcast['data']['runtime_rejections']
    assert len(rejected) == 1 and rejected[0]['recipient_agent_id'] == 'subject'
    assert rejected[0]['retry_safe'] and not rejected[0]['execution_started']
    assert len(broadcast['data']['runtime_operations']) == 1
    assert not query(setup, "SELECT * FROM message_deliveries WHERE message_id=? AND recipient_agent_id='subject'",
                     (broadcast['data']['message_id'],))
    wait_receipt(other_setup, turn_for(setup, broadcast['data']['message_id']))
    assert len(peers.sessions) == 2


def test_cleanup_failure_cannot_erase_success_or_release_capacity(connected_local, monkeypatch):
    from okto_nexus.application import one_shot_runtime
    from okto_nexus.errors import ErrorCode, OktoNexusError
    setup, binding, _ = connected_local
    peers = Peers()
    setup[1].state.embedded_dispatch_owner.native_factory = peers
    configure(setup, binding, 'one_shot')
    send = sender(setup, monkeypatch)
    first = turn_for(setup, send('operator'))
    wait_receipt(setup, first)
    real_admit = one_shot_runtime._admit
    def fail_close(*args, **kwargs):
        if args[6] == 'runtime.close':
            raise OktoNexusError(ErrorCode.CONFLICT, 'Injected temporary cleanup refusal', {})
        return real_admit(*args, **kwargs)
    monkeypatch.setattr(one_shot_runtime, '_admit', fail_close)
    complete(setup, peers, first, 'durable successful response')
    wait_until(setup, lambda: query(setup, "SELECT * FROM one_shot_calls WHERE state='SUCCEEDED'"))
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE one_shot_calls SET execution_deadline=0')
    send('operator', 'wait for confirmed disposal')
    tick(setup[0])
    assert query(setup, "SELECT count(*) FROM one_shot_calls WHERE state='SUCCEEDED'")[0][0] == 1
    assert query(setup, "SELECT count(*) FROM one_shot_calls WHERE state='QUEUED'")[0][0] == 1
    assert len(peers.sessions) == 1
    monkeypatch.setattr(one_shot_runtime, '_admit', real_admit)
    wait_until(setup, lambda: len(peers.sessions) == 2)


@pytest.mark.parametrize('local_setup', ['codex_app_server', 'claude_stream', 'pi_rpc'], indirect=True)
def test_one_shot_closes_then_serves_queue_in_fresh_session(connected_local, monkeypatch):
    setup, binding, _ = connected_local
    peers = Peers()
    setup[1].state.embedded_dispatch_owner.native_factory = peers
    configure(setup, binding, 'one_shot')
    send = sender(setup, monkeypatch)
    first = turn_for(setup, send('operator', 'first'))
    wait_receipt(setup, first)
    second_message = send('operator', 'second')
    assert query(setup, "SELECT count(*) FROM one_shot_calls WHERE state='QUEUED'")[0][0] == 1
    complete(setup, peers, first, 'first finished')
    wait_until(setup, lambda: query(setup, "SELECT sum(state='RUNNING')=1 AND sum(state='SUCCEEDED')=1 "
                                   'FROM one_shot_calls')[0][0])
    second = turn_for(setup, second_message)
    wait_receipt(setup, second)
    assert second['session_id'] != first['session_id']
    assert query(setup, 'SELECT lifecycle_state FROM execution_sessions WHERE session_id=?', (first['session_id'],))[0][0] == 'CLOSED'
    complete(setup, peers, second, 'second finished')
    wait_until(setup, lambda: not query(setup, 'SELECT * FROM one_shot_slots'))


def test_warm_instance_is_claimed_only_once(connected_local, monkeypatch):
    setup, binding, _ = connected_local
    peers = Peers()
    setup[1].state.embedded_dispatch_owner.native_factory = peers
    configure(setup, binding, 'one_shot')
    from okto_nexus.application.one_shot_settings import read, save
    with setup[0].connection_factory.unit_of_work() as uow:
        current = read(uow.connection)
        save(uow.connection, expected_revision=current['revision'],
             settings=current['settings'] | {'max_parallel': 2, 'warm_instances': 1})
    wait_until(setup, lambda: query(setup, "SELECT session_id FROM one_shot_slots WHERE state='WARM'"))
    warm = query(setup, "SELECT session_id FROM one_shot_slots WHERE state='WARM'")[0][0]
    send = sender(setup, monkeypatch)
    first = turn_for(setup, send('operator'))
    assert first['session_id'] == warm
    wait_receipt(setup, first)
    complete(setup, peers, first, 'done')
    wait_until(setup, lambda: query(setup, 'SELECT lifecycle_state FROM execution_sessions WHERE session_id=?', (warm,))[0][0] == 'CLOSED')
    second = turn_for(setup, send('operator', 'another call'))
    assert second['session_id'] != warm


def test_expired_queued_call_notifies_original_caller_once(connected_local, monkeypatch):
    from okto_nexus.application.one_shot_notifications import publish_errors
    from okto_nexus.adapters.inbound.mcp.tools.harness import build_message_service
    setup, binding, _ = connected_local
    configure(setup, binding, 'one_shot')
    send = sender(setup, monkeypatch)
    first = turn_for(setup, send('operator', 'occupy capacity'))
    wait_receipt(setup, first)
    queued_message = send('operator', 'expires while queued')
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE one_shot_calls SET queue_deadline=0 WHERE state='QUEUED'")
    tick(setup[0])
    service = build_message_service(setup[0])
    publish_errors(setup[0], service)
    assert publish_errors(setup[0], service) == 0
    rows = query(setup, 'SELECT m.body,d.recipient_agent_id FROM messages m JOIN message_deliveries d USING(message_id) '
                 'WHERE m.parent_message_id=?', (queued_message,))
    assert len(rows) == 1
    assert rows[0]['recipient_agent_id'] == 'operator'
    assert 'ONE_SHOT_QUEUE_EXPIRED' in rows[0]['body']
    assert '"retry_safe": true' in rows[0]['body']
    assert query(setup, 'SELECT count(*) FROM execution_sessions')[0][0] == 1


def test_retiring_one_binding_does_not_retire_another_bindings_pool(connected_local):
    from okto_nexus.application import one_shot_capacity as capacity
    from okto_nexus.application.one_shot_settings import read, save
    setup, binding, _ = connected_local
    with setup[0].connection_factory.unit_of_work() as uow:
        conn = uow.connection
        current = read(conn)
        save(conn, expected_revision=current['revision'], settings=current['settings'] | {'max_parallel': 3, 'warm_instances': 2})
        slots = []
        for name in ('binding-a', 'binding-b'):
            slot = capacity.reserve_warm(conn, agent_id='subject', executor_id=binding['executor_id'],
                configuration_digest=name, host_limit=10, now=time.time())
            conn.execute('UPDATE one_shot_slots SET binding_id=? WHERE slot_id=?', (name, slot))
            slots.append(slot)
        assert capacity.retire_warm(conn, agent_id='subject', executor_id=binding['executor_id'],
                                   configuration_digest='new-a', binding_id='binding-a') == 1
        assert conn.execute('SELECT state FROM one_shot_slots WHERE slot_id=?', (slots[1],)).fetchone()[0] == 'STARTING'


def test_direct_start_cannot_bypass_one_shot_capacity(connected_local):
    setup, binding, _ = connected_local
    configure(setup, binding, 'one_shot')
    response = setup[2].post('/v1/runtime/intents:resolve', headers=setup[3]['subject'], json=dict(
        client_intent_id='bypass-capacity', intent='runtime.start', binding_id=binding['binding_id'],
        workspace_binding_id=binding['workspace_binding_id'], new_session=True))
    assert response.status_code == 409, response.text
    assert not query(setup, 'SELECT * FROM execution_sessions')


def test_operator_cancellation_closes_without_reusing_session(connected_local, monkeypatch):
    setup, binding, _ = connected_local
    configure(setup, binding, 'one_shot')
    first = turn_for(setup, sender(setup, monkeypatch)('operator', 'cancel me'))
    wait_receipt(setup, first)
    call_id = query(setup, 'SELECT call_id FROM one_shot_calls')[0][0]
    path = '/api/v1/agents/subject/one-shot-calls/' + call_id + '/cancel'
    assert setup[2].post(path, headers=setup[3]['subject']).status_code == 403
    result = setup[2].post(path, headers=setup[3]['operator'])
    assert result.status_code == 200, result.text
    call = result.json()['data']['calls'][0]
    assert call['state'] == 'CANCELLED' and call['error']['possible_effect'] is True
    wait_until(setup, lambda: not query(setup, 'SELECT * FROM one_shot_slots'))
