"""Cold competitive startup cannot dispatch after its pool admission expires."""
import asyncio
import json
import threading
from pathlib import Path

import pytest

from okto_nexus.application import one_shot_capacity, one_shot_runtime
from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from okto_nexus.bootstrap.handoff_runtime_attempts import build_handoff_runtime_attempts
from okto_nexus.bootstrap.handoff_runtime_scheduler import build_handoff_runtime_candidates
from okto_nexus.errors import OktoNexusError
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime
from test_one_shot_runtime import query, wait_until
from test_handoff_automation_principal import prepare
from test_handoff_runtime_candidates import enable_capacity, lease
from test_sender_sessions import Peers, configure
from test_binding_operator import onboarding


@pytest.mark.parametrize('expire_before_ready', [False, True])
def test_late_cold_open_keeps_slot_until_stop_and_never_sends_work(
        runtime, monkeypatch, expire_before_ready):
    setup, binding, _ = runtime
    deps, app, client, *_ = setup
    entered, release, dispatched = threading.Event(), threading.Event(), threading.Event()
    refused = []

    class Delayed(Peers):
        async def open(self, prepared, session_id, context, *, stream_epoch):
            entered.set()
            while not release.is_set():
                await asyncio.sleep(.01)
            return await super().open(prepared, session_id, context, stream_epoch=stream_epoch)

    peers = Delayed()
    app.state.embedded_dispatch_owner.native_factory = peers
    configure(setup, binding, 'one_shot')
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='none' WHERE endpoint_id=?",
                               (binding['endpoint_id'],))
    _, hid, gid = prepare(runtime)
    enable_capacity(runtime)
    page = build_handoff_runtime_candidates(deps).prepare_page(lease(runtime, hid), limit=4)
    assert len(page.attempt_ids) == 1, page
    attempts = build_handoff_runtime_attempts(deps)
    aid = page.attempt_ids[0]
    reserved = client.portal.call(attempts.reserve, aid)
    assert reserved.state == 'RESERVED'
    held = reserved.reservation
    assert not entered.is_set() and not peers.sessions
    committed = attempts.claim(aid)
    identity = committed.operation_id
    assert attempts.claim(aid).operation_id == identity
    transfer = build_capacity_admission(deps)
    original_expire = one_shot_capacity.expire_executions
    original_send = one_shot_runtime.before_send

    def before_send(conn, operation):
        try:
            return original_send(conn, operation)
        except OktoNexusError as error:
            refused.append(error.message)
            raise
        finally:
            if operation['action'] == 'turn.submit':
                dispatched.set()

    monkeypatch.setattr(one_shot_runtime, 'before_send', before_send)
    try:
        assert client.portal.call(transfer.consume, identity).state == 'CONSUMED'
        wait_until(setup, entered.is_set)
        assert not peers.sessions
        row = query(setup, 'SELECT state,admission_deadline,enqueued_at FROM one_shot_calls')[0]
        assert row['state'] == 'ADMITTED'
        assert row['admission_deadline'] - row['enqueued_at'] == 300
        # Advance only this durable call's deadline; do not alter leases or clocks.
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('UPDATE one_shot_calls SET admission_deadline=0 WHERE call_id=?', (identity,))
        if expire_before_ready:
            one_shot_runtime.tick(deps)
            assert query(setup, 'SELECT state FROM one_shot_slots')[0][0] == 'CLOSING'
        else:
            # Force dispatch to win the scheduling race against the expiry scan.
            monkeypatch.setattr(one_shot_capacity, 'expire_executions', lambda *a, **kw: 0)
        assert len(query(setup, 'SELECT * FROM one_shot_slots')) == 1
        assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == ('CLAIMED', 1)
        release.set()
        if not expire_before_ready:
            wait_until(setup, dispatched.is_set)
            assert any('deadline' in message for message in refused), refused
            assert query(setup, 'SELECT started_at FROM one_shot_calls')[0][0] is None
            monkeypatch.setattr(one_shot_capacity, 'expire_executions', original_expire)
        wait_until(setup, lambda: len(peers.sessions) == 1 and all(p.stopped for p in peers.sessions.values()))
        wait_until(setup, lambda: not query(setup, 'SELECT * FROM one_shot_slots'))
        assert all(not p.sent for p in peers.sessions.values())
        assert set(peers.sessions) == {held.request.scope.session_id}
        call = query(setup, 'SELECT state,started_at,outcome_json FROM one_shot_calls')[0]
        assert call['state'] == 'FAILED' and call['started_at'] is None
        assert json.loads(call['outcome_json'])['error']['code'] in {'ONE_SHOT_START_TIMEOUT', 'ONE_SHOT_DISPATCH_FAILED'}
        assert query(setup, 'SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (gid,))[0][0] == 1
        assert query(setup, 'SELECT count(*) FROM runtime_handoff_bindings')[0][0] == 1
    finally:
        release.set()
        monkeypatch.setattr(one_shot_capacity, 'expire_executions', original_expire)


def test_expired_cold_open_denies_renewal_and_retains_capacity_during_containment(runtime):
    setup, binding, _ = runtime
    deps, app, client, *_ = setup
    entered, release = threading.Event(), threading.Event()

    class Delayed(Peers):
        async def open(self, prepared, session_id, context, *, stream_epoch):
            entered.set()
            while not release.is_set():
                await asyncio.sleep(.01)
            return await super().open(prepared, session_id, context, stream_epoch=stream_epoch)

    peers = Delayed()
    owner = app.state.embedded_dispatch_owner
    owner.native_factory = peers
    configure(setup, binding, 'one_shot')
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='none'")
    _, hid, _ = prepare(runtime)
    enable_capacity(runtime)
    page = build_handoff_runtime_candidates(deps).prepare_page(lease(runtime, hid), limit=4)
    assert len(page.attempt_ids) == 1
    attempts = build_handoff_runtime_attempts(deps)
    aid = page.attempt_ids[0]
    assert client.portal.call(attempts.reserve, aid).state == 'RESERVED'
    committed = attempts.claim(aid)
    sid = committed.request.scope.session_id
    try:
        client.portal.call(build_capacity_admission(deps).consume, committed.operation_id)
        wait_until(setup, entered.is_set)
        session = owner.sessions[sid]
        # A healthy renewal while opening must still succeed before the bound.
        client.portal.call(owner._renew_owned, sid, session)
        assert not session.get('recovering')
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('UPDATE one_shot_calls SET admission_deadline=0')
        # Deliberately do not run the pool expiry scan before the renewal.
        client.portal.call(owner._renew_owned, sid, session)
        assert session.get('recovering'), 'Expired startup still received renewed execution authority'
        assert not peers.sessions
        assert len(query(setup, 'SELECT * FROM one_shot_slots')) == 1
        assert sid in owner.agents.session_tasks
        observed = client.portal.call(deps.runtime_availability.get_capacity_reservation, committed.request)
        assert observed.state in {'CONSUMED', 'RELEASE_PENDING'}
        assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == ('CLAIMED', 1)
    finally:
        release.set()
    wait_until(setup, lambda: sid not in owner.sessions)
    wait_until(setup, lambda: not query(setup, 'SELECT * FROM one_shot_slots'))
    assert all(peer.stopped and not peer.sent for peer in peers.sessions.values())
    assert query(setup, 'SELECT count(*) FROM runtime_handoff_bindings')[0][0] == 1


@pytest.mark.parametrize('cut', ['before_initial_lease', 'after_turn_started'])
def test_startup_bound_applies_before_open_but_not_to_running_work(runtime, cut):
    from test_canonical_result_publication import current_turn
    from test_embedded_dispatch import wait_receipt
    from test_sender_sessions import complete
    setup, binding, _ = runtime
    deps, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    peers = Peers()
    owner.native_factory = peers
    configure(setup, binding, 'one_shot')
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='none'")
    _, hid, _ = prepare(runtime)
    enable_capacity(runtime)
    page = build_handoff_runtime_candidates(deps).prepare_page(lease(runtime, hid), limit=4)
    assert len(page.attempt_ids) == 1
    attempts = build_handoff_runtime_attempts(deps)
    aid = page.attempt_ids[0]
    assert client.portal.call(attempts.reserve, aid).state == 'RESERVED'
    committed = attempts.claim(aid)
    sid = committed.request.scope.session_id
    if cut == 'before_initial_lease':
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('UPDATE one_shot_calls SET admission_deadline=0')
    client.portal.call(build_capacity_admission(deps).consume, committed.operation_id)
    if cut == 'before_initial_lease':
        wait_until(setup, lambda: not query(setup, 'SELECT * FROM one_shot_slots'))
        assert not peers.sessions
        assert query(setup, 'SELECT started_at FROM one_shot_calls')[0][0] is None
        wait_until(setup, lambda: sid not in owner.sessions)
        assert owner.failure is None and not owner.agents.blocked
        assert query(setup, 'SELECT lifecycle_state,lease_state FROM execution_sessions')[0][:] == ('CLOSED', 'CLOSED')
        assert query(setup, 'SELECT state FROM execution_session_containment')[0][0] == 'RELEASED'
        assert query(setup, 'SELECT count(*) FROM execution_local_streams')[0][0] == 0
        assert query(setup, 'SELECT count(*) FROM execution_local_publications')[0][0] == 1
        receipt = query(setup, 'SELECT stage,error_code,possible_effect,retry_safe FROM execution_receipts')[0]
        assert receipt[:] == ('FAILED', 'LEASE_REVALIDATION_REQUIRED', 0, 1)
    else:
        turn = current_turn(setup)
        wait_receipt(setup, turn)
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('UPDATE one_shot_calls SET admission_deadline=0')
        session = owner.sessions[sid]
        client.portal.call(owner._renew_owned, sid, session)
        assert not session.get('recovering')
        assert len(peers.sessions[sid].sent) == 1 and not peers.sessions[sid].stopped
        complete(setup, peers, turn, 'Started before the admission deadline')
        wait_until(setup, lambda: not query(setup, 'SELECT * FROM one_shot_slots'))
        assert query(setup, 'SELECT state FROM one_shot_calls')[0][0] == 'SUCCEEDED'
    assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == ('CLAIMED', 1)
    assert query(setup, 'SELECT count(*) FROM runtime_handoff_bindings')[0][0] == 1


@pytest.mark.parametrize('cut', ['binding_after', 'core_before', 'core_after', 'publish_before', 'publish_after'])
def test_initial_refusal_recovers_same_operation_after_persistence_cut(runtime, monkeypatch, cut):
    from okto_nexus.bootstrap import embedded_initial_refusal as refusal
    hit = []
    owner = runtime[0][1].state.embedded_dispatch_owner
    if cut == 'binding_after':
        original = refusal.EmbeddedInitialRefusal.bind
        def fail_after(self, *args):
            result = original(self, *args)
            if not hit:
                hit.append(cut)
                raise OSError('Injected failure after refusal association commit')
            return result
        monkeypatch.setattr(refusal.EmbeddedInitialRefusal, 'bind', fail_after)
    elif cut.startswith('core'):
        original = refusal.persist_r4_lease_refusal
        async def fail_core(*args):
            first = not hit
            if first:
                hit.append(cut)
                if cut == 'core_before':
                    raise OSError('Injected failure before Core refusal fact')
            result = await original(*args)
            if first:
                raise OSError('Injected lost result after Core refusal commit')
            return result
        monkeypatch.setattr(refusal, 'persist_r4_lease_refusal', fail_core)
    else:
        original = owner._publish
        async def fail_publish(binding, receipt):
            first = receipt.error_code == 'LEASE_REVALIDATION_REQUIRED' and not hit
            if first:
                hit.append(cut)
                if cut == 'publish_before':
                    raise OSError('Injected failure before Server receipt commit')
            result = await original(binding, receipt)
            if first:
                raise OSError('Injected lost result after Server receipt commit')
            return result
        monkeypatch.setattr(owner, '_publish', fail_publish)
    test_startup_bound_applies_before_open_but_not_to_running_work(runtime, 'before_initial_lease')
    assert hit == [cut]
    assert query(runtime[0], 'SELECT count(*) FROM execution_capacity_admissions')[0][0] == 1
    assert query(runtime[0], 'SELECT count(*) FROM handoff_runtime_attempts')[0][0] == 1


@pytest.mark.parametrize('onboarding', ['connector-configured'], indirect=True)
@pytest.mark.parametrize('expiry_cut', ['dispatch', 'scan', 'renewal'])
def test_remote_cold_start_deadline_preserves_real_slot_until_confirmed_stop(
        onboarding, tmp_path, monkeypatch, expiry_cut):
    from okto_nexus.application.handoff_runtime_scheduler import HandoffScheduleLease
    from okto_nexus.domain.base import iso_plus
    from okto_nexus_connector.storage.state_store import StateStore
    from test_handoff_executor_selection import bind, running_pair
    from test_runtime_policy_defaults import save
    expire_before_ready = expiry_cut != 'dispatch'
    if expiry_cut == 'renewal':
        from functools import partial
        from okto_nexus.adapters.inbound.http import executor_link
        monkeypatch.setattr(executor_link, 'ExecutionLeaseService',
            partial(executor_link.ExecutionLeaseService, max_duration_ms=5000))
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool

    deps, client, headers, proposal = onboarding
    binding = bind(client, headers, proposal, 'startup')
    setup = (deps, client.app, client, headers)
    assert save(setup, agent='subject', session_policy='one_shot',
                broadcast_handoff_auto_claim=True).status_code == 200
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='none',consumption='exclusive'")
    for actions in (['execute_work'], ['open', 'send', 'close']):
        response = client.post('/api/v1/harness/grants', headers=headers['operator'], json=dict(
            actor_agent_id='subject', endpoint_id=binding['endpoint_id'], actions=actions,
            max_executions=10, expires_at=iso_plus(deps.clock.now_iso(), 600)))
        assert response.status_code == 200, response.text
    records = [(binding, StateStore(tmp_path / 'connector-state.json'), tmp_path / 'remote-only' / 'codex.exe',
                tmp_path / 'remote-workspace', 'connector', 'register')]
    client.headers['host'] = '127.0.0.1:8000'
    original_expire = one_shot_capacity.expire_executions
    original_send = one_shot_runtime.before_send
    refused = []

    def before_send(conn, operation):
        try:
            return original_send(conn, operation)
        except OktoNexusError as error:
            if operation['action'] == 'turn.submit':
                refused.append(error.message)
            raise
    monkeypatch.setattr(one_shot_runtime, 'before_send', before_send)

    async def run():
        async with running_pair(onboarding, records, tmp_path) as command:
            async def until(check):
                async with asyncio.timeout(25):
                    while True:
                        state = await command(0, 'status')
                        if check(state):
                            return state
                        await asyncio.to_thread(one_shot_runtime.tick, deps)
                        await asyncio.sleep(.03)

            await command(0, 'hold_open')
            try:
                made = tool(client, headers['other']['Authorization'].removeprefix('Bearer '), 'handoff_create',
                    dict(workspace_id=binding['workspace_id'], from_agent_id='other', visibility='eligible',
                         target={'strategy': 'broadcast'}, payload='Never send after startup expiry'))
                assert made['ok'], made
                hid = made['data']['handoff_id']
                page = build_handoff_runtime_candidates(deps).prepare_page(
                    HandoffScheduleLease(hid, binding['workspace_id'], 0, 'startup', 0, 0, ''), limit=4)
                assert len(page.attempt_ids) == 1, page
                attempts = build_handoff_runtime_attempts(deps)
                aid = page.attempt_ids[0]
                held = await attempts.reserve(aid)
                assert held.state == 'RESERVED'
                state = await command(0, 'status')
                assert state['opening'] == state['opens'] == 0
                committed = attempts.claim(aid)
                assert attempts.claim(aid).operation_id == committed.operation_id
                admission = await build_capacity_admission(deps).consume(committed.operation_id)
                assert admission.state == 'CONSUMED'
                await until(lambda state: state['opening'] == 1)
                row = query(setup, 'SELECT state,admission_deadline,enqueued_at FROM one_shot_calls')[0]
                assert row['state'] == 'ADMITTED'
                assert row['admission_deadline'] - row['enqueued_at'] == 300
                with deps.connection_factory.unit_of_work() as uow:
                    uow.connection.execute('UPDATE one_shot_calls SET admission_deadline=0')
                if expire_before_ready:
                    await asyncio.to_thread(one_shot_runtime.tick, deps)
                    assert query(setup, 'SELECT state FROM one_shot_slots')[0][0] == 'CLOSING'
                else:
                    monkeypatch.setattr(one_shot_capacity, 'expire_executions', lambda *a, **kw: 0)
                if expiry_cut == 'renewal':
                    await until(lambda state: bool(query(setup, 'SELECT 1 FROM execution_session_containment')))
                    state = await command(0, 'status')
                    assert state['ready'] and state['opening'] == 1 and state['opens'] == 0
                # A timed-out but unfinished producer still owns the physical slot.
                from dataclasses import replace
                from nexus_connector_core.capacity import capacity_reservation_id
                request = replace(held.request, attempt_id='blocked-second-start',
                    scope=replace(held.request.scope, session_id='second-session'), affinity_key='sha256:' + 'a' * 64)
                unavailable = await deps.runtime_availability.try_reserve_capacity(request)
                assert unavailable.reason == 'HOST_FULL', unavailable
                tombstone = await deps.runtime_availability.release_capacity(
                    request, capacity_reservation_id(request), 'CANCELLED')
                assert tombstone.state == 'RELEASED'
                await command(0, 'release_open')
                if not expire_before_ready:
                    await until(lambda state: bool(refused))
                    assert any('deadline' in message for message in refused), refused
                    monkeypatch.setattr(one_shot_capacity, 'expire_executions', original_expire)
                state = await until(lambda state: state['stopped'] == 1 and not query(setup, 'SELECT * FROM one_shot_slots'))
                assert (state['opens'], state['sends'], state['opening']) == (1, 0, 0)
                assert query(setup, 'SELECT started_at FROM one_shot_calls')[0][0] is None
                assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == ('CLAIMED', 1)
                assert query(setup, 'SELECT count(*) FROM runtime_handoff_bindings')[0][0] == 1
                if expiry_cut == 'renewal':
                    assert query(setup, 'SELECT state FROM execution_session_containment')[0][0] == 'RELEASED'
            finally:
                monkeypatch.setattr(one_shot_capacity, 'expire_executions', original_expire)
                await command(0, 'release_open')

    asyncio.run(run())
