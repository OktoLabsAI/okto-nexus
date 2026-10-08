"""Concurrent pull and approval cannot duplicate canonical native effects."""
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_canonical_consumption import pull
from test_canonical_result_publication import current_turn, emit, wait_result


@pytest.mark.parametrize('cut', ['before_reservation', 'after_reservation'])
def test_pull_waits_for_uncommitted_canonical_push_reservation(connected_local, monkeypatch, cut):
    from okto_nexus.adapters.outbound.sqlite.connection import SqliteUnitOfWork
    from okto_nexus.adapters.outbound.sqlite.write_gate import WriteGate
    from okto_nexus.adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
    from okto_nexus.adapters.inbound.mcp.tools.inbox import build_service
    setup, binding, native = connected_local
    enable(setup, binding)
    deps = setup[0]
    inbox = build_service(deps)
    held, release, pull_waiting, pull_begin = (threading.Event() for _ in range(4))
    local = threading.local()
    enqueue = SqliteRuntimeOutboxRepo.enqueue
    enter = SqliteUnitOfWork.__enter__
    acquire = WriteGate.acquire
    seen = []

    def reserve(self, uow, **kwargs):
        envelope = kwargs['envelope']
        if cut == 'after_reservation':
            enqueue(self, uow, **kwargs)
        seen.append(envelope.delivery_id)
        assert uow.connection.execute('SELECT COUNT(*) FROM message_deliveries WHERE delivery_id=?',
                                      (envelope.delivery_id,)).fetchone()[0] == 1
        held.set()
        assert release.wait(8)
        if cut == 'before_reservation':
            enqueue(self, uow, **kwargs)

    def pulling():
        local.pulling = True
        try:
            return inbox.pull(agent_id='subject')['messages']
        finally:
            local.pulling = False

    def entering(self):
        if self._write and getattr(local, 'pulling', False):
            self.connection.set_trace_callback(
                lambda sql: pull_begin.set() if sql == 'BEGIN IMMEDIATE' else None)
        return enter(self)

    def acquiring(self, *args, **kwargs):
        if getattr(local, 'pulling', False):
            pull_waiting.set()
        return acquire(self, *args, **kwargs)

    monkeypatch.setattr(SqliteRuntimeOutboxRepo, 'enqueue', reserve)
    monkeypatch.setattr(SqliteUnitOfWork, '__enter__', entering)
    monkeypatch.setattr(WriteGate, 'acquire', acquiring)
    with ThreadPoolExecutor(max_workers=2) as pool:
        producer = pool.submit(send, setup, monkeypatch)
        try:
            assert held.wait(5)
            consumer = pool.submit(pulling)
            # The current write gate serializes writers before BEGIN IMMEDIATE.
            assert pull_waiting.wait(3), 'Pull never reached writer admission'
            assert not consumer.done()
            assert not pull_begin.is_set()
            assert native.opens == 0
        finally:
            release.set()
        created = producer.result(timeout=10)
        assert created['ok'], created
        assert consumer.result(timeout=10) == []
        assert pull_begin.is_set()
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    assert len(seen) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        delivery = uow.connection.execute('SELECT consumer_kind,consumer_operation_id,attempts,lease_expires_at '
            'FROM message_deliveries WHERE delivery_id=?', (seen[0],)).fetchone()
        assert tuple(delivery) == ('push', created['data']['runtime_operations'][0], 0, None)
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox WHERE delivery_id=?',
                                     (seen[0],)).fetchone()[0] == 1
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 1
    assert pull(setup, monkeypatch) == []
    assert native.opens == 1 and len(native.native.sent) == 1
    wait_receipt(setup, admit(setup, binding, 'race-close', 'runtime.close', session_id=turn['session_id']), stages=('SUCCEEDED',))


def test_concurrent_approval_decisions_execute_message_once(connected_local, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_governance import _attach, _rule
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    enable(setup, binding)
    deps.config.feature_hitl = True
    _attach(deps, 'operator', governance=[_rule('message_create', 'require_approval')])
    pending = send(setup, monkeypatch)
    assert pending['ok'] and pending['data']['status'] == 'pending_approval', pending
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ('messages', 'delivery_outbox', 'execution_operations'):
            assert uow.connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0
    assert native.opens == 0
    barrier = threading.Barrier(3)
    path = '/api/v1/approvals/' + pending['data']['approval_id'] + '/decision'

    def decide():
        barrier.wait(timeout=5)
        return client.post(path, headers=headers['operator'], json={'decision': 'approve'})

    with ThreadPoolExecutor(max_workers=3) as pool:
        replies = list(pool.map(lambda _: decide(), range(3)))
    assert sorted(r.status_code for r in replies) == [200, 409, 409], [r.text for r in replies]
    executed = next(r.json()['data']['executed_result'] for r in replies if r.status_code == 200)
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    emit(setup, native, turn, 'One governed answer')
    result = wait_result(setup, 'PUBLISHED')
    assert result['operation_id'] == executed['runtime_operations'][0]
    assert result['output_text'] == 'One governed answer'
    repeat = client.post(path, headers=headers['operator'], json={'decision': 'approve'})
    assert repeat.status_code == 409, repeat.text
    deps.runtime_dispatcher.scan_once()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1
        assert uow.connection.execute("SELECT COUNT(*) FROM messages WHERE body='Please review this message.'").fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_results WHERE operation_id=?',
                                     (executed['runtime_operations'][0],)).fetchone()[0] == 1
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 1
    assert native.opens == 1 and len(native.native.sent) == 1
    wait_receipt(setup, admit(setup, binding, 'approved-close', 'runtime.close', session_id=turn['session_id']), stages=('SUCCEEDED',))


def test_competitive_handoff_pool_has_one_executor_across_agents_and_bindings(connected_local, monkeypatch):
    from okto_nexus.domain.base import iso_plus
    from test_agent_recovery_isolation import create_agent
    from test_embedded_dispatch import connect_local
    from test_canonical_identity_lifecycle import second_binding
    from test_sender_sessions import Peers
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    setup, first, _ = connected_local
    other_setup = create_agent(setup, 'second')
    _, other, _ = connect_local(other_setup, agent_id='second')
    extra = second_binding(setup, monkeypatch)
    deps, app, client, headers, *_, root = setup
    client.headers['host'] = '127.0.0.1:8000'
    peers = Peers()
    app.state.embedded_dispatch_owner.native_factory = peers
    choices = [(setup, first, 'subject'), (other_setup, other, 'second'), (setup, extra, 'subject')]
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET role='reviewer' WHERE agent_id IN ('subject','second')")
        for _, binding, _ in choices:
            uow.connection.execute("UPDATE agent_endpoints SET consumption='exclusive',response_policy='none' WHERE endpoint_id=?",
                                   (binding['endpoint_id'],))
    grants = []
    for _, binding, actor in choices:
        response = client.post('/api/v1/harness/grants', headers=headers['operator'], json=dict(
            actor_agent_id=actor, endpoint_id=binding['endpoint_id'], actions=['execute_work'],
            max_executions=1, expires_at=iso_plus(deps.clock.now_iso(), 600)))
        assert response.status_code == 200, response.text
        grants.append(response.json()['data']['grant_id'])
    created = tool(client, headers['operator']['Authorization'].removeprefix('Bearer '), 'handoff_create', dict(
        project_root=str(root), from_agent_id='operator', visibility='eligible',
        target=dict(strategy='role', role='reviewer'), payload='One competitive review'))
    assert created['ok'], created
    hid = created['data']['handoff_id']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 0
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0
    assert peers.sessions == {}
    barrier = threading.Barrier(3)

    def compete(index):
        actor_setup, binding, actor = choices[index]
        barrier.wait(timeout=5)
        return tool(client, actor_setup[3]['subject']['Authorization'].removeprefix('Bearer '), 'handoff_claim', dict(
            project_root=str(root), handoff_id=hid, agent_id=actor, runtime_endpoint_id=binding['endpoint_id'],
            execution_grant_id=grants[index], idempotency_key=f'pool-{index}'))

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(compete, range(3)))
    winners = [index for index, result in enumerate(results) if result['ok']]
    assert len(winners) == 1, results
    winning_setup, winning_binding, _ = choices[winners[0]]
    turn = current_turn(setup)
    wait_receipt(winning_setup, turn)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_handoff_bindings WHERE handoff_id=?', (hid,)).fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1
        # Opening the winning runtime separately consumes an open grant. Only
        # the single winning work grant may be charged for this competition.
        charged = [uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?',
                                          (grant,)).fetchone()[0] for grant in grants]
        assert charged[winners[0]] == 1 and sum(charged) == 1
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 1
    assert len(peers.sessions) == 1 and sum(len(peer.sent) for peer in peers.sessions.values()) == 1
    wait_receipt(winning_setup, admit(winning_setup, winning_binding, 'pool-close', 'runtime.close',
        session_id=turn['session_id']), stages=('SUCCEEDED',))
