"""Real discovery creates durable candidates without consuming agent inboxes."""
import asyncio
from dataclasses import replace
import sqlite3
from types import SimpleNamespace

import pytest

from okto_nexus.application.handoff_runtime_scheduler import HandoffScheduleLease
from okto_nexus.bootstrap.handoff_runtime_scheduler import (
    build_handoff_runtime_candidates, build_handoff_runtime_scheduler)
from okto_nexus.bootstrap.handoff_runtime_attempts import build_handoff_runtime_attempts
from okto_nexus.adapters.outbound.sqlite.handoff_runtime_candidates import SqliteHandoffCandidateRepository
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, assert_unclaimed, call
from test_handoff_automation_principal import prepare
from test_canonical_result_publication import workspace, current_turn
from test_runtime_policy_defaults import save


def lease(runtime, hid, cursor=''):
    return HandoffScheduleLease(hid, workspace(runtime[0]), 0, 'test-lease', 0, 0, cursor)


def enable_capacity(runtime):
    deps, app, client, *_ = runtime[0]
    owner, registry = app.state.embedded_dispatch_owner, deps.runtime_availability
    owner.host.capacity_enabled = registry.enabled = True

    async def wait():
        async with asyncio.timeout(5):
            while True:
                host = registry.current_host(owner.channel.server_id, owner.channel.executor_id)
                if host and runtime[1]['binding_id'] in host.observations:
                    return
                await asyncio.sleep(.01)
    client.portal.call(wait)


def test_real_discovery_journals_once_and_scheduler_executes_without_conversation_permission(runtime):
    handoffs, hid, gid = prepare(runtime)
    enable_capacity(runtime)
    deps, app, client, *_ = runtime[0]
    discovery = build_handoff_runtime_candidates(deps)
    first = discovery.prepare_page(lease(runtime, hid), limit=4)
    assert len(first.attempt_ids) == 1
    assert discovery.prepare_page(lease(runtime, hid, first.cursor), limit=4).attempt_ids == first.attempt_ids
    attempts = build_handoff_runtime_attempts(deps)
    attempt = attempts.get(first.attempt_ids[0])
    assert attempt.request.unit == 'new_session'
    assert attempt.request.scope.agent_id == 'subject'
    assert attempt.principal.agent_id == 'subject'
    assert_unclaimed(runtime, hid, gid)
    assert runtime[2].opens == 0

    def state():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return uow.connection.execute('SELECT state FROM handoff_runtime_schedule WHERE handoff_id=?', (hid,)).fetchone()

    async def run():
        import time
        clock = [time.time()]
        scheduler = build_handoff_runtime_scheduler(deps, now=lambda: clock[0], monotonic=lambda: clock[0])
        try:
            async with asyncio.timeout(15):
                while not (state() and state()[0] == 'IDLE'):
                    scheduler.tick()
                    await asyncio.sleep(.05)
                    clock[0] += 1
        finally:
            assert await scheduler.aclose(timeout=5) == 0
    client.portal.call(run)
    wait_receipt(runtime[0], current_turn(runtime[0]))
    assert runtime[2].opens == len(runtime[2].native.sent) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM handoff_runtime_attempts').fetchone()[0] == 1
        assert uow.connection.execute('SELECT claim_epoch,status FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == (1, 'CLAIMED')
        assert uow.connection.execute('SELECT response_policy FROM agent_endpoints WHERE endpoint_id=?',
                                      (runtime[1]['endpoint_id'],)).fetchone()[0] == 'none'


def test_revoked_candidate_recovers_original_reservation_without_replacement(runtime):
    _, hid, gid = prepare(runtime)
    enable_capacity(runtime)
    deps, _, client, *_ = runtime[0]
    discovery = build_handoff_runtime_candidates(deps)
    first = discovery.prepare_page(lease(runtime, hid), limit=4)
    attempts = build_handoff_runtime_attempts(deps)
    aid = first.attempt_ids[0]
    assert client.portal.call(attempts.reserve, aid).state == 'RESERVED'
    assert save(runtime[0], agent='subject', broadcast_handoff_auto_claim=False).status_code == 200
    after = discovery.prepare_page(lease(runtime, hid, first.cursor), limit=4)
    assert after.attempt_ids == (aid,)
    assert attempts.get(aid).disposition == 'RELEASE'
    assert not client.portal.call(attempts.release, aid).active
    assert discovery.prepare_page(lease(runtime, hid), limit=4).attempt_ids == ()
    assert_unclaimed(runtime, hid, gid)
    assert runtime[2].opens == 0


@pytest.mark.parametrize('mode', ['disabled', 'direct', 'unsupported'])
def test_discovery_preserves_scope_opt_in_and_protocol_gates(runtime, mode):
    _, hid, gid = prepare(runtime, strategy='direct' if mode == 'direct' else 'broadcast', enable=mode != 'disabled')
    if mode != 'unsupported':
        enable_capacity(runtime)
    page = build_handoff_runtime_candidates(runtime[0][0]).prepare_page(lease(runtime, hid), limit=4)
    assert page.attempt_ids == ()
    assert page.settled == (mode == 'direct')
    if mode == 'unsupported':
        assert page.reason == 'CAPACITY_PROTOCOL_UNSUPPORTED'
    assert_unclaimed(runtime, hid, gid)
    assert runtime[2].opens == 0


def test_sqlite_pages_rotate_logical_agents_and_resume_cursor_without_materializing_endpoints():
    conn = sqlite3.connect(':memory:')
    try:
        conn.executescript('''
            CREATE TABLE handoff_runtime_attempts(agent_id,workspace_id,handoff_id,active,operation_id);
            CREATE TABLE execution_capacity_admissions(domain_operation_id,state);
            CREATE TABLE agent_endpoints(agent_id,workspace_id,protocol,enabled,activation_state);
        ''')
        for n in range(100):
            for _ in range(20 if n == 0 else 1):
                conn.execute('INSERT INTO agent_endpoints VALUES(?,?,?,?,?)',
                             (f'agent-{n:03}', 'workspace', 'nxl-r4', 1, 'approved'))
        conn.execute('INSERT INTO agent_endpoints VALUES(?,?,?,?,?)', ('other', 'other-workspace', 'nxl-r4', 1, 'approved'))
        conn.execute('INSERT INTO handoff_runtime_attempts VALUES(?,?,?,?,?)', ('revoked', 'workspace', 'handoff', 1, None))
        repo = SqliteHandoffCandidateRepository(attempts=None, availability=None, pool_factory=None)
        current = HandoffScheduleLease('handoff', 'workspace', 0, 'token', 0, 0, '')
        seen = []
        while True:
            ids, cursor, more = repo.agents_page(SimpleNamespace(connection=conn), current, allow_new=True, limit=4)
            assert len(ids) <= 4
            seen.extend(ids)
            current = replace(current, candidate_cursor=cursor)
            if not more:
                break
            repo = SqliteHandoffCandidateRepository(attempts=None, availability=None, pool_factory=None)
        assert len(seen) == len(set(seen)) == 101
        assert 'revoked' in seen and 'other' not in seen
        next_ids, _, _ = repo.agents_page(SimpleNamespace(connection=conn), current, allow_new=True, limit=4)
        assert next_ids[0] != seen[0]
        recovery, _, more = repo.agents_page(SimpleNamespace(connection=conn), replace(current, candidate_cursor=''),
                                             allow_new=False, limit=4)
        assert recovery == ('revoked',) and not more
        import json
        suffix = replace(current, candidate_cursor=json.dumps({'anchor': 'revoked', 'after': 'revoked'}))
        ids, cursor, more = repo.agents_page(SimpleNamespace(connection=conn), suffix, allow_new=False, limit=4)
        assert ids == () and more
        ids, _, _ = repo.agents_page(SimpleNamespace(connection=conn), replace(current, candidate_cursor=cursor),
                                     allow_new=False, limit=4)
        assert ids == ('revoked',)
    finally:
        conn.close()


def test_distinct_warm_instances_reserve_and_execute_independently(runtime, monkeypatch):
    from test_sender_sessions import Peers, configure
    from test_one_shot_runtime import query, wait_until
    from okto_nexus.application import one_shot_capacity
    from okto_nexus.application.one_shot_settings import read, save as save_pool
    from okto_nexus.bootstrap.capacity_admission import build_capacity_admission

    setup, binding, _ = runtime
    deps, app, client, *_ = setup
    peers = Peers()
    app.state.embedded_dispatch_owner.native_factory = peers
    configure(setup, binding, 'one_shot')
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='none' WHERE endpoint_id=?", (binding['endpoint_id'],))
    _, first_hid, _ = prepare(runtime)
    second = call(runtime, 'handoff_create', from_agent_id='caller', visibility='eligible',
                  target=dict(strategy='broadcast'), payload='Second independent task')
    assert second['ok'], second
    enable_capacity(runtime)
    with deps.connection_factory.unit_of_work() as uow:
        settings = read(uow.connection)
        save_pool(uow.connection, expected_revision=settings['revision'],
                  settings=settings['settings'] | dict(max_parallel=3, warm_instances=2))
    wait_until(setup, lambda: len(query(setup, "SELECT slot_id FROM one_shot_slots WHERE state='WARM'")) == 2)
    monkeypatch.setattr(one_shot_capacity, 'reserve_warm', lambda *args, **kwargs: None)
    discovery, attempts = build_handoff_runtime_candidates(deps), build_handoff_runtime_attempts(deps)
    ids = [discovery.prepare_page(lease(runtime, hid), limit=4).attempt_ids[0]
           for hid in (first_hid, second['data']['handoff_id'])]
    before = [attempts.get(identity) for identity in ids]
    assert all(a.request.unit == 'next_turn' for a in before)
    assert len({a.request.scope.session_id for a in before}) == 2
    assert len({a.request.affinity_key for a in before}) == 2
    assert len(peers.sessions) == 2 and all(not p.sent for p in peers.sessions.values())

    async def reserve_both():
        return await asyncio.gather(*(attempts.reserve(identity) for identity in ids))
    held = client.portal.call(reserve_both)
    assert all(a.state == 'RESERVED' for a in held)
    committed = [attempts.claim(identity) for identity in ids]
    admissions = build_capacity_admission(deps)
    for attempt in committed:
        transferred = client.portal.call(admissions.consume, attempt.operation_id)
        assert transferred.consumption.opening_operation_id is None
        wait_receipt(setup, {'operation_id': transferred.consumption.turn_operation_id,
                             'session_id': attempt.request.scope.session_id})
    assert len(peers.sessions) == 2
    assert all(len(peer.sent) == 1 for peer in peers.sessions.values())


@pytest.mark.parametrize('mode', ['shared', 'per_sender', 'per_sender_session'])
def test_busy_creator_affinity_is_preserved_and_other_context_only_opens_when_policy_allows(runtime, mode):
    from test_sender_sessions import Peers, configure
    from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
    from okto_nexus.application.execution_domain_delivery import delivery_session_context
    from okto_nexus.adapters.outbound.sqlite.handoff_origins import SqliteHandoffOriginRepo

    setup, binding, _ = runtime
    deps, app, client, *_ = setup
    peers = Peers()
    app.state.embedded_dispatch_owner.native_factory = peers
    configure(setup, binding, mode)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='none' WHERE endpoint_id=?", (binding['endpoint_id'],))
    _, hid, _ = prepare(runtime)
    enable_capacity(runtime)
    discovery, attempts = build_handoff_runtime_candidates(deps), build_handoff_runtime_attempts(deps)
    aid = discovery.prepare_page(lease(runtime, hid), limit=4).attempt_ids[0]
    assert client.portal.call(attempts.reserve, aid).state == 'RESERVED'
    first = attempts.claim(aid)
    transfer = build_capacity_admission(deps)
    admitted = client.portal.call(transfer.consume, first.operation_id)
    wait_receipt(setup, dict(operation_id=admitted.consumption.turn_operation_id, session_id=first.request.scope.session_id))

    def create(actor='caller', **origin):
        result = call(runtime, 'handoff_create', actor=actor, from_agent_id=actor, visibility='eligible',
                      target=dict(strategy='broadcast'), payload='Preserve original affinity', **origin)
        assert result['ok'], result
        return result['data']['handoff_id']

    same_hid = create()
    same_id = discovery.prepare_page(lease(runtime, same_hid), limit=4).attempt_ids[0]
    same = attempts.get(same_id)
    assert same.request.unit == 'next_turn'
    assert same.request.scope.session_id == first.request.scope.session_id
    assert same.request.affinity_key == first.request.affinity_key
    refused = client.portal.call(attempts.reserve, same_id)
    assert refused.state == 'NOT_AVAILABLE' and not refused.active
    assert refused.reason in ('BUSY_AFFINITY', 'EARLIER_WORK_PENDING')
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status FROM handoffs WHERE handoff_id=?', (same_hid,)).fetchone()[0] == 'OPEN'

    if mode == 'per_sender_session':
        source = call(runtime, 'session_open', agent_id='caller')
        assert source['ok'], source
        other_hid = create(session_id=source['data']['session_id'], session_secret=source['data']['session_secret'])
    else:
        other_hid = create(actor='operator')
    other_id = discovery.prepare_page(lease(runtime, other_hid), limit=4).attempt_ids[0]
    other = attempts.get(other_id)
    if mode == 'shared':
        assert other.request.scope.session_id == first.request.scope.session_id
        assert client.portal.call(attempts.reserve, other_id).state == 'NOT_AVAILABLE'
        assert len(peers.sessions) == 1
    else:
        assert other.request.unit == 'new_session'
        assert other.request.scope.session_id != first.request.scope.session_id
        with deps.connection_factory.unit_of_work() as uow:
            origin = SqliteHandoffOriginRepo().get(uow, workspace_id=workspace(setup), handoff_id=other_hid)
            _, affinity = delivery_session_context(uow, binding['endpoint_id'],
                sender_agent_id='caller' if mode == 'per_sender_session' else 'operator',
                source_session_key=origin.source_session_key)
            assert other.request.affinity_key == affinity.opaque_key
        assert client.portal.call(attempts.reserve, other_id).state == 'RESERVED'
        other = attempts.claim(other_id)
        admitted = client.portal.call(transfer.consume, other.operation_id)
        wait_receipt(setup, dict(operation_id=admitted.consumption.turn_operation_id, session_id=other.request.scope.session_id))
        assert len(peers.sessions) == 2 and all(len(p.sent) == 1 for p in peers.sessions.values())


@pytest.mark.parametrize('barrier', ['dependency', 'audience'])
def test_discovery_rechecks_shared_eligibility_before_preparing_a_candidate(runtime, barrier):
    handoffs, hid, gid = prepare(runtime)
    enable_capacity(runtime)
    deps = runtime[0][0]
    if barrier == 'dependency':
        dependency = call(runtime, 'handoff_create', from_agent_id='caller', visibility='eligible',
                          target=dict(strategy='direct', agent_id='subject'), payload='Dependency')
        assert dependency['ok'], dependency
        with deps.connection_factory.unit_of_work() as uow:
            handoffs._handoffs.create_dependencies(uow, handoff_id=hid, workspace_id=workspace(runtime[0]),
                depends_on=[dependency['data']['handoff_id']], created_at=deps.clock.now_iso())
    else:
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agents SET comm_scope=? WHERE agent_id='caller'",
                                  ('{"outbound":{"team":["elsewhere"]}}',))
    discovery = build_handoff_runtime_candidates(deps)
    assert discovery.prepare_page(lease(runtime, hid), limit=4).attempt_ids == ()
    assert_unclaimed(runtime, hid, gid)
    with deps.connection_factory.unit_of_work() as uow:
        if barrier == 'dependency':
            uow.connection.execute("UPDATE handoffs SET status='COMPLETED' WHERE handoff_id=?",
                                   (dependency['data']['handoff_id'],))
        else:
            uow.connection.execute("UPDATE agents SET comm_scope=NULL WHERE agent_id='caller'")
    assert len(discovery.prepare_page(lease(runtime, hid), limit=4).attempt_ids) == 1
    assert_unclaimed(runtime, hid, gid)


@pytest.mark.parametrize('max_parallel', [1, 0])
def test_cold_one_shot_discovery_obeys_pool_or_host_limit_without_queueing_a_loser(runtime, max_parallel):
    from test_sender_sessions import configure
    from okto_nexus.application.one_shot_settings import read, save as save_pool
    from okto_nexus.bootstrap.capacity_admission import build_capacity_admission

    setup, binding, native = runtime
    deps, _, client, *_ = setup
    configure(setup, binding, 'one_shot')
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='none' WHERE endpoint_id=?", (binding['endpoint_id'],))
        settings = read(uow.connection)
        save_pool(uow.connection, expected_revision=settings['revision'],
                  settings=settings['settings'] | dict(max_parallel=max_parallel, warm_instances=0))
        if max_parallel == 0:
            uow.connection.execute('INSERT INTO one_shot_host_limits VALUES(?,1)', (binding['executor_id'],))
    _, hid, _ = prepare(runtime)
    enable_capacity(runtime)
    discovery, attempts = build_handoff_runtime_candidates(deps), build_handoff_runtime_attempts(deps)
    aid = discovery.prepare_page(lease(runtime, hid), limit=4).attempt_ids[0]
    proposed = attempts.get(aid)
    assert proposed.request.unit == 'new_session'
    assert client.portal.call(attempts.reserve, aid).state == 'RESERVED'
    assert native.opens == 0
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM one_shot_calls').fetchone()[0] == 0
    first = attempts.claim(aid)
    admitted = client.portal.call(build_capacity_admission(deps).consume, first.operation_id)
    assert admitted.consumption.opening_operation_id is not None
    wait_receipt(setup, dict(operation_id=admitted.consumption.turn_operation_id, session_id=first.request.scope.session_id))
    second = call(runtime, 'handoff_create', from_agent_id='caller', visibility='eligible',
                  target=dict(strategy='broadcast'), payload='May not win a queue position')
    assert second['ok'], second
    page = discovery.prepare_page(lease(runtime, second['data']['handoff_id']), limit=4)
    assert page.attempt_ids == ()
    assert page.reason == ('POOL_FULL' if max_parallel else 'HOST_FULL')
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM one_shot_calls').fetchone()[0] == 1
        assert uow.connection.execute('SELECT count(*) FROM one_shot_slots').fetchone()[0] == 1
        assert uow.connection.execute('SELECT count(*) FROM handoff_runtime_attempts').fetchone()[0] == 1
        assert uow.connection.execute('SELECT status FROM handoffs WHERE handoff_id=?',
                                      (second['data']['handoff_id'],)).fetchone()[0] == 'OPEN'
    assert native.opens == len(native.native.sent) == 1


def test_capacity_publication_wakes_waiting_broadcast_without_new_message_or_expired_backoff(runtime):
    import time
    from nexus_connector_core import OperationKey

    _, hid, _ = prepare(runtime)
    deps, app, client, *_ = runtime[0]
    owner = app.state.embedded_dispatch_owner
    owner.host.max_owned_slots = 1
    enable_capacity(runtime)

    def scheduled():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return dict(uow.connection.execute('SELECT * FROM handoff_runtime_schedule WHERE handoff_id=?', (hid,)).fetchone())

    async def run():
        ledger = await owner.host._ledger()
        key = OperationKey(owner.channel.server_id, owner.channel.executor_id, 'occupied-opening')
        await ledger.reserve_owned_slot(key, 'occupied-session')
        clock = time.time()
        scheduler = build_handoff_runtime_scheduler(deps, now=lambda: clock, monotonic=lambda: clock)
        scheduler._next_sweep = clock + 1000
        try:
            async with asyncio.timeout(10):
                while scheduled()['reason'] != 'HOST_FULL' or scheduler.pending_count:
                    scheduler.tick()
                    await asyncio.sleep(.01)
            blocked = scheduled()
            assert blocked['due_at'] > clock
            assert runtime[2].opens == 0
            await ledger.release_owned_slot(key, 'occupied-session')
            publisher = owner.capacity_publication.publisher
            publisher._next_poll = 0
            owner.capacity_publication.tick()
            await publisher._task
            # Wall clock and fallback sweep remain frozen. Only the published
            # capacity signal can make the backoff row immediately eligible.
            async with asyncio.timeout(10):
                while scheduled()['reason'] not in ('CLAIM_COMMITTED', 'SETTLED') or scheduler.pending_count:
                    scheduler.tick()
                    await asyncio.sleep(.01)
            assert scheduled()['seen_wake_generation'] > blocked['seen_wake_generation']
        finally:
            assert await scheduler.aclose(timeout=5) == 0
            await ledger.release_owned_slot(key, 'occupied-session')
    client.portal.call(run)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT state FROM execution_capacity_admissions').fetchone()[0] == 'CONSUMED'
    wait_receipt(runtime[0], current_turn(runtime[0]))
    assert runtime[2].opens == len(runtime[2].native.sent) == 1


def test_mcp_only_agent_keeps_inbox_and_can_win_before_reserved_runtime(runtime):
    import time

    _, hid, _ = prepare(runtime)
    enable_capacity(runtime)
    deps, _, client, *_ = runtime[0]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute("SELECT 1 FROM agent_endpoints WHERE agent_id='operator'").fetchone()
        notice = dict(uow.connection.execute("SELECT d.* FROM runtime_handoff_notifications n "
            "JOIN message_deliveries d USING(message_id) WHERE n.handoff_id=? AND n.recipient_agent_id='operator'", (hid,)).fetchone())
        assert notice['status'] == 'unread' and notice['consumer_kind'] is None
    available = call(runtime, 'handoff_list_available', actor='operator', agent_id='operator')
    assert available['ok'] and hid in str(available['data']), available
    discovery, attempts = build_handoff_runtime_candidates(deps), build_handoff_runtime_attempts(deps)
    aid = discovery.prepare_page(lease(runtime, hid), limit=4).attempt_ids[0]
    assert client.portal.call(attempts.reserve, aid).state == 'RESERVED'
    claimed = call(runtime, 'handoff_claim', actor='operator', agent_id='operator', handoff_id=hid)
    assert claimed['ok'], claimed

    def state():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return uow.connection.execute('SELECT state FROM handoff_runtime_schedule WHERE handoff_id=?', (hid,)).fetchone()[0]

    async def run():
        clock = [time.time()]
        scheduler = build_handoff_runtime_scheduler(deps, now=lambda: clock[0], monotonic=lambda: clock[0])
        try:
            async with asyncio.timeout(10):
                while state() != 'IDLE' or scheduler.pending_count:
                    scheduler.tick()
                    await asyncio.sleep(.02)
                    clock[0] += 1
        finally:
            assert await scheduler.aclose(timeout=5) == 0
    client.portal.call(run)
    assert not attempts.get(aid).active
    assert runtime[2].opens == 0
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status,claimed_by,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == ('CLAIMED', 'operator', 1)
        assert uow.connection.execute('SELECT count(*) FROM execution_operations').fetchone()[0] == 0
        after = dict(uow.connection.execute('SELECT * FROM message_deliveries WHERE delivery_id=?', (notice['delivery_id'],)).fetchone())
        assert after == notice  # No forged MCP delivery/ack during runtime cleanup.
