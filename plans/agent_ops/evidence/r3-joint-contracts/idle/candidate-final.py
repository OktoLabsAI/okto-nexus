"""RG-03: real SQLite/Core scheduling with an explicitly synthetic native peer.

External idle is published through the existing authenticated HTTP fixture.
No personal credential, installed provider, or native service is exercised.
"""
import asyncio
from dataclasses import replace
import time

import pytest

from okto_nexus.bootstrap.handoff_runtime_scheduler import (
    build_handoff_runtime_candidates, build_handoff_runtime_scheduler,
)
from test_external_observation_isolation import (
    local_setup as local_setup,
    qualified_bridge as qualified_bridge,
    qualified_contract as qualified_contract,
    observed_runtime as observed_runtime_fixture,
)
from test_embedded_dispatch import connect_local, admit, wait_receipt
from test_canonical_delivery import enable, send
from test_canonical_result_publication import current_turn
from test_canonical_identity_lifecycle import second_binding
from test_canonical_handoff_regressions import runtime as runtime_fixture, call, assert_unclaimed
from test_handoff_automation_principal import prepare
from test_handoff_runtime_candidates import enable_capacity, lease
from test_handoff_runtime_attempts import prepared
from test_runtime_policy_defaults import save
from test_agent_recovery_isolation import create_agent, eventually
from test_one_shot_runtime import query
from test_sender_sessions import Peers, configure, turn_for


observed_runtime = observed_runtime_fixture
runtime = runtime_fixture


@pytest.fixture
def connected_local(observed_runtime):
    return observed_runtime[:3]


def publish_current_idle(observed_runtime):
    response = observed_runtime[3]('idle')
    assert response.status_code == 200
    setup = observed_runtime[0]
    response = setup[2].get('/api/v1/observations/summary', headers=setup[3]['operator'])
    assert response.status_code == 200
    data = response.json()['data']
    assert data['freshness']['current'] == data['activity']['idle'] == 1


def test_external_idle_preserves_endpoint_priority_and_existing_affinity(observed_runtime, monkeypatch):
    setup, first, native, publish = observed_runtime
    deps = setup[0]
    second = second_binding(setup, monkeypatch)
    enable(setup, second)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE agent_endpoints SET priority=10 WHERE endpoint_id=?',
                               (second['endpoint_id'],))
    priorities = [tuple(row) for row in query(setup,
        'SELECT endpoint_id,priority,revision FROM agent_endpoints ORDER BY endpoint_id')]
    assert publish('working').status_code == 200
    before = send(setup, monkeypatch)
    assert before['ok']
    wait_receipt(setup, current_turn(setup))
    publish_current_idle(observed_runtime)
    after = send(setup, monkeypatch)
    assert after['ok']
    operations = [item['data']['runtime_operations'][0] for item in (before, after)]
    for operation in operations:
        assert query(setup, 'SELECT endpoint_id FROM delivery_outbox WHERE operation_id=?',
                     (operation,))[0][0] == second['endpoint_id']
    assert [tuple(row) for row in query(setup,
        'SELECT endpoint_id,priority,revision FROM agent_endpoints ORDER BY endpoint_id')] == priorities
    assert native.opens == len(native.native.sent) == 1


def test_external_idle_cannot_overtake_existing_one_shot_fifo(runtime, observed_runtime):
    setup, binding, _ = runtime
    deps, app, client, *_ = setup
    peers = Peers()
    app.state.embedded_dispatch_owner.native_factory = peers
    configure(setup, binding, 'one_shot')

    def message(text):
        response = call(runtime, 'message_create', from_agent_id='caller',
            target={'strategy': 'direct', 'agent_id': 'subject'}, subject='RG-03 FIFO', body=text)
        assert response['ok']
        return response['data']['message_id']

    first = turn_for(setup, message('Already running'))
    wait_receipt(setup, first)
    message('Second in queue')
    message('Third in queue')
    before = [tuple(row) for row in query(setup,
        'SELECT call_id,state,enqueued_at,started_at FROM one_shot_calls ORDER BY enqueued_at,call_id')]
    assert sum(row[1] == 'QUEUED' for row in before) == 2
    _, hid, gid = prepare(runtime)
    enable_capacity(runtime)
    clock = [time.time()]
    scheduler = build_handoff_runtime_scheduler(deps, now=lambda: clock[0], monotonic=lambda: clock[0])

    async def round_once():
        clock[0] += 20
        async with asyncio.timeout(15):
            while True:
                scheduler.tick()
                await asyncio.sleep(.02)
                rows = query(setup, 'SELECT reason,due_at,lease_until FROM handoff_runtime_schedule '
                    'WHERE handoff_id=?', (hid,))
                if rows and rows[0]['lease_until'] == 0 and rows[0]['due_at'] > clock[0]:
                    return rows[0]['reason']

    try:
        assert client.portal.call(round_once) == 'EARLIER_WORK_PENDING'
        publish_current_idle(observed_runtime)
        assert client.portal.call(round_once) == 'EARLIER_WORK_PENDING'
        assert [tuple(row) for row in query(setup,
            'SELECT call_id,state,enqueued_at,started_at FROM one_shot_calls ORDER BY enqueued_at,call_id')] == before
        assert tuple(query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0]) == ('OPEN', 0)
        assert query(setup, 'SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (gid,))[0][0] == 0
        assert not query(setup, 'SELECT 1 FROM runtime_handoff_bindings WHERE handoff_id=?', (hid,))
        assert len(peers.sessions) == 1 and sum(len(peer.sent) for peer in peers.sessions.values()) == 1
    finally:
        assert client.portal.call(scheduler.aclose) == 0


def test_external_idle_preserves_shared_dispatch_fairness(observed_runtime):
    setup, binding, _, _ = observed_runtime
    healthy_setup, healthy_binding, _ = connect_local(create_agent(setup, 'healthy'), agent_id='healthy')
    release = asyncio.Event()
    started = []

    class Held(Peers):
        async def open(self, prepared, session_id, context, *, stream_epoch):
            started.append(context.agent_id)
            if context.agent_id == 'subject':
                await release.wait()
            return await super().open(prepared, session_id, context, stream_epoch=stream_epoch)

    setup[1].state.embedded_dispatch_owner.native_factory = Held()
    pending = []
    try:
        for index in range(4):
            pending.append(admit(setup, binding, 'idle-fair-'+str(index), 'runtime.start', new_session=True))
        eventually(lambda: started.count('subject') == 3)
        publish_current_idle(observed_runtime)
        healthy = admit(healthy_setup, healthy_binding, 'healthy-amid-idle', 'runtime.start', new_session=True)
        wait_receipt(healthy_setup, healthy)
        assert not release.is_set()
        assert started.count('subject') == 3 and started.count('healthy') == 1
    finally:
        setup[2].portal.call(release.set)
    for opening in pending:
        wait_receipt(setup, opening)
    assert started.count('subject') == 4


@pytest.mark.parametrize('barrier', ['auto_claim_disabled', 'creator_audience'])
def test_external_idle_cannot_make_ineligible_agent_a_candidate(runtime, observed_runtime, barrier):
    _, hid, gid = prepare(runtime, enable=barrier != 'auto_claim_disabled')
    enable_capacity(runtime)
    deps = runtime[0][0]
    if barrier == 'creator_audience':
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agents SET comm_scope=? WHERE agent_id='caller'",
                                   ('{"outbound":{"team":["elsewhere"]}}',))
    discovery = build_handoff_runtime_candidates(deps)
    assert discovery.prepare_page(lease(runtime, hid), limit=4).attempt_ids == ()
    publish_current_idle(observed_runtime)
    assert discovery.prepare_page(lease(runtime, hid), limit=4).attempt_ids == ()
    assert not query(runtime[0], 'SELECT 1 FROM handoff_runtime_attempts')
    assert_unclaimed(runtime, hid, gid)
    # Positive control removes only the existing canonical fixture barrier.
    if barrier == 'auto_claim_disabled':
        assert save(runtime[0], agent='subject', broadcast_handoff_auto_claim=True).status_code == 200
    else:
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agents SET comm_scope=NULL WHERE agent_id='caller'")
    assert len(discovery.prepare_page(lease(runtime, hid), limit=4).attempt_ids) == 1
    assert_unclaimed(runtime, hid, gid)


def test_external_idle_preserves_exact_unconsumed_claim_reservation(runtime, observed_runtime):
    service, port, attempt, hid, gid = prepared(runtime)
    client = runtime[0][2]
    aid = attempt.request.attempt_id
    held = client.portal.call(service.reserve, aid)
    assert held.state == 'RESERVED' and held.active
    assert held.reservation is not None and held.operation_id is None
    tables = ('handoffs', 'handoff_runtime_attempts', 'handoff_runtime_schedule',
              'handoff_runtime_schedule_scan', 'runtime_execution_grants', 'execution_capacity_admissions')

    def snapshot():
        with runtime[0][0].connection_factory.unit_of_work(write=False) as uow:
            return {table: [tuple(row) for row in uow.connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
                    for table in tables}

    before = snapshot()
    try:
        publish_current_idle(observed_runtime)
        assert snapshot() == before
        assert service.get(aid) == held
        observed = client.portal.call(port.get_capacity_reservation, held.request)
        assert 0 < observed.remaining_ms <= held.reservation.remaining_ms
        assert replace(observed, remaining_ms=held.reservation.remaining_ms) == held.reservation
        repeated = client.portal.call(service.reserve, aid)
        assert 0 < repeated.reservation.remaining_ms <= observed.remaining_ms
        # TTL naturally decreases; idle/retry cannot renew it. Every identity,
        # scope, capacity revision, state and consumption field stays exact.
        assert replace(repeated, reservation=replace(repeated.reservation,
            remaining_ms=held.reservation.remaining_ms)) == held
        assert_unclaimed(runtime, hid, gid)
    finally:
        assert not client.portal.call(service.release, aid).active
