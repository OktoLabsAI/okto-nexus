"""Real SQLite/embedded capacity, with cuts at the reserve and claim boundaries."""
import asyncio
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest

from okto_nexus.application.execution_domain_delivery import delivery_session_context
from okto_nexus.bootstrap.handoff_runtime_attempts import build_handoff_runtime_attempts
from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from okto_nexus.errors import OktoNexusError
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, call, assert_unclaimed
from test_handoff_automation_principal import prepare, candidate
from test_canonical_result_publication import current_turn
from test_capacity_authority import request


def prepared(runtime):
    setup, binding, _ = runtime
    deps, app, client, *_ = setup
    handoffs, hid, gid = prepare(runtime)
    context = candidate(runtime, handoffs, hid, gid)
    with deps.connection_factory.unit_of_work() as uow:
        _, affinity = delivery_session_context(uow, binding['endpoint_id'], sender_agent_id='caller')
    owner = app.state.embedded_dispatch_owner
    owner.host.capacity_enabled = True
    req = replace(request(setup, binding), attempt_id=context.request_id,
                  affinity_key=affinity.opaque_key, ttl_ms=60000)
    port = client.portal.call(owner.execution_capacity)
    service = build_handoff_runtime_attempts(deps, capacity=port)
    attempt = service.prepare(principal=context.handoff_automation, request=req, claim_generation=0)
    assert attempt.state == 'WAITING' and attempt.reservation is None
    return service, port, attempt, hid, gid


class ObservedPort:
    def __init__(self, runtime, port):
        self.runtime, self.port, self.reserves = runtime, port, 0

    def __getattr__(self, name):
        return getattr(self.port, name)

    async def try_reserve_capacity(self, req):
        # A new writer on the Server can see the intent before the host call.
        with self.runtime[0][0].connection_factory.unit_of_work() as uow:
            row = uow.connection.execute('SELECT state,request_json FROM handoff_runtime_attempts WHERE attempt_id=?',
                                         (req.attempt_id,)).fetchone()
            assert row['state'] == 'RESERVING'
            assert req.scope.session_id in row['request_json']
        self.reserves += 1
        return await self.port.try_reserve_capacity(req)


def test_lost_reserve_response_restores_original_attempt_and_claim_after_restart(runtime):
    service, port, attempt, hid, gid = prepared(runtime)
    aid = attempt.request.attempt_id

    class Lost(ObservedPort):
        async def try_reserve_capacity(self, req):
            self.held = await super().try_reserve_capacity(req)
            raise TimeoutError('Reserve committed but its reply was lost')

    lost = Lost(runtime, port)
    service.capacity = lost
    with pytest.raises(TimeoutError):
        runtime[0][2].portal.call(service.reserve, aid)
    assert service.get(aid).state == 'NEEDS_RECONCILIATION'
    assert_unclaimed(runtime, hid, gid)
    resumed = build_handoff_runtime_attempts(runtime[0][0], capacity=lost)
    restored = runtime[0][2].portal.call(resumed.reserve, aid)
    assert restored.state == 'RESERVED'
    assert restored.reservation.reservation_id == lost.held.reservation_id
    assert lost.reserves == 1
    factory = resumed.factory
    cut_once = True

    @contextmanager
    def lost_commit_reply(**kwargs):
        nonlocal cut_once
        with factory.unit_of_work(**kwargs) as uow:
            yield uow
            committed = not kwargs.get('write') is False and uow.connection.execute(
                "SELECT 1 FROM handoff_runtime_attempts WHERE state='CLAIM_COMMITTED'").fetchone()
        if cut_once and committed:
            cut_once = False
            raise OSError('Claim committed but its response was lost')

    resumed.factory = SimpleNamespace(unit_of_work=lost_commit_reply)
    with pytest.raises(OSError):
        resumed.claim(aid)
    claimed = resumed.get(aid)
    assert claimed.state == 'CLAIM_COMMITTED'
    # A caller that lost the claim response finds the same persisted operation.
    restarted = build_handoff_runtime_attempts(runtime[0][0], capacity=port)
    assert restarted.claim(aid) == claimed
    assert runtime[0][2].portal.call(restarted.release, aid) == claimed
    transfer = build_capacity_admission(runtime[0][0], capacity=port)
    runtime[0][2].portal.call(transfer.consume, claimed.operation_id)
    wait_receipt(runtime[0], current_turn(runtime[0]))
    assert runtime[2].opens == len(runtime[2].native.sent) == 1
    with runtime[0][0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (gid,)).fetchone()[0] == 1
        assert uow.connection.execute('SELECT claim_epoch FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[0] == 1


def test_mcp_winner_leaves_only_durable_cleanup_for_runtime_candidate(runtime):
    service, port, attempt, hid, gid = prepared(runtime)
    aid = attempt.request.attempt_id
    assert runtime[0][2].portal.call(service.reserve, aid).state == 'RESERVED'
    response = call(runtime, 'handoff_claim', actor='subject', agent_id='subject', handoff_id=hid)
    assert response['ok'], response
    with pytest.raises(OktoNexusError):
        service.claim(aid)
    assert service.get(aid).disposition == 'RELEASE'
    restarted = build_handoff_runtime_attempts(runtime[0][0], capacity=port)
    done = runtime[0][2].portal.call(restarted.release, aid)
    assert done.state == 'CANCELLED_NO_EFFECT' and not done.active
    assert done.reservation.state == 'RELEASED'
    assert runtime[2].opens == 0
    with runtime[0][0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM execution_operations').fetchone()[0] == 0
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (gid,)).fetchone()[0] == 0
        assert uow.connection.execute('SELECT claimed_by,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == ('subject', 1)


def test_attempt_claim_commit_cut_rolls_back_and_lost_release_reply_is_recovered(runtime, monkeypatch):
    service, port, attempt, hid, gid = prepared(runtime)
    aid = attempt.request.attempt_id
    runtime[0][2].portal.call(service.reserve, aid)
    original = service.repository.claimed

    def cut(*args):
        original(*args)
        raise OSError('Cut after journal/claim linkage, before the shared commit')

    monkeypatch.setattr(service.repository, 'claimed', cut)
    with pytest.raises(OSError):
        service.claim(aid)
    assert_unclaimed(runtime, hid, gid)
    assert service.get(aid).state == 'RELEASE_PENDING'

    class LostRelease(ObservedPort):
        async def release_capacity(self, *args):
            self.released = await self.port.release_capacity(*args)
            raise TimeoutError('Release committed but its reply was lost')

    lost = LostRelease(runtime, port)
    service.capacity = lost
    with pytest.raises(TimeoutError):
        runtime[0][2].portal.call(service.release, aid)
    assert lost.released.state == 'RELEASED'
    assert service.get(aid).active and service.get(aid).disposition == 'RELEASE'
    restarted = build_handoff_runtime_attempts(runtime[0][0], capacity=port)
    assert not runtime[0][2].portal.call(restarted.release, aid).active
    assert_unclaimed(runtime, hid, gid)


@pytest.mark.parametrize('supports_cancellation', [False, True])
def test_absent_lookup_needs_a_durable_cancellation_to_retire_a_delayed_reserve(runtime, supports_cancellation):
    service, port, attempt, hid, gid = prepared(runtime)
    aid = attempt.request.attempt_id

    async def scenario():
        entered, proceed = asyncio.Event(), asyncio.Event()

        class Delayed(ObservedPort):
            async def try_reserve_capacity(self, req):
                entered.set()
                await proceed.wait()
                return await self.port.try_reserve_capacity(req)

            async def release_capacity(self, req, reservation_id, reason):
                if not supports_cancellation and await self.port.get_capacity_reservation(req) is None:
                    from nexus_connector_core import CoreError
                    raise CoreError('RESERVATION_CONFLICT', 'older-host-release')
                return await self.port.release_capacity(req, reservation_id, reason)

        service.capacity = Delayed(runtime, port)
        task = asyncio.create_task(service.reserve(aid))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            if supports_cancellation:
                absent = await service.release(aid)
                assert absent.state == 'CANCELLED_NO_EFFECT' and not absent.active
                assert absent.reservation.state == 'RELEASED'
                next_attempt = service.prepare(principal=replace(attempt.principal, attempt_id='second-candidate'),
                    request=replace(attempt.request, attempt_id='second-candidate'), claim_generation=0)
                # Bypass only this test's delayed network hook for the new ID.
                resumed = build_handoff_runtime_attempts(runtime[0][0], capacity=port)
                acquired = await resumed.reserve(next_attempt.request.attempt_id)
                assert acquired.state == 'RESERVED'
                assert not (await resumed.release(next_attempt.request.attempt_id)).active
            else:
                from nexus_connector_core import CoreError
                with pytest.raises(CoreError, match='RESERVATION_CONFLICT'):
                    await service.release(aid)
                absent = service.get(aid)
                assert absent.state == 'NEEDS_RECONCILIATION' and absent.active
                assert absent.disposition == 'RELEASE' and absent.reservation is None
                with pytest.raises(OktoNexusError):
                    service.prepare(principal=replace(attempt.principal, attempt_id='second-candidate'),
                        request=replace(attempt.request, attempt_id='second-candidate'), claim_generation=0)
            proceed.set()
            returned = await task
            assert returned.state == ('CANCELLED_NO_EFFECT' if supports_cancellation else 'RELEASE_PENDING')
            assert returned.reservation.state == ('RELEASED' if supports_cancellation else 'HELD')
            done = await service.release(aid)
            assert not done.active and done.reservation.state == 'RELEASED'
        finally:
            proceed.set()
            await task

    runtime[0][2].portal.call(scenario)
    assert_unclaimed(runtime, hid, gid)


def test_concurrent_retries_share_one_reservation_and_immutable_scope(runtime):
    service, port, attempt, hid, gid = prepared(runtime)
    aid = attempt.request.attempt_id

    async def scenario():
        return await asyncio.gather(*(service.reserve(aid) for _ in range(8)))

    results = runtime[0][2].portal.call(scenario)
    assert {a.state for a in results} == {'RESERVED'}
    assert len({a.reservation.reservation_id for a in results}) == 1
    for changed in (replace(attempt.request, ttl_ms=100),
                    replace(attempt.request, scope=replace(attempt.request.scope, session_id='different-session'))):
        with pytest.raises(OktoNexusError):
            service.prepare(principal=attempt.principal, request=changed, claim_generation=0)
    assert_unclaimed(runtime, hid, gid)
    assert not runtime[0][2].portal.call(service.release, aid).active


@pytest.mark.parametrize('cut', ['before_assess', 'after_assess'])
def test_capacity_refusal_before_and_after_sending_have_distinct_recovery(runtime, cut):
    service, port, attempt, hid, gid = prepared(runtime)
    aid = attempt.request.attempt_id
    competitor_request = replace(attempt.request, attempt_id='capacity-competitor',
        scope=replace(attempt.request.scope, session_id='competitor-session'))

    class Contended(ObservedPort):
        competitor = None

        async def assess_capacity(self, req):
            if cut == 'before_assess':
                self.competitor = await self.port.try_reserve_capacity(competitor_request)
            return await self.port.assess_capacity(req)

        async def try_reserve_capacity(self, req):
            if self.competitor is None:
                self.competitor = await self.port.try_reserve_capacity(competitor_request)
            return await super().try_reserve_capacity(req)

    adapter = Contended(runtime, port)
    service.capacity = adapter
    refused = runtime[0][2].portal.call(service.reserve, aid)
    assert refused.state == 'NOT_AVAILABLE' and refused.reason == 'BUSY_AFFINITY'
    assert refused.active == (cut == 'after_assess')
    assert adapter.reserves == int(cut == 'after_assess')
    assert_unclaimed(runtime, hid, gid)

    async def free():
        return await port.release_capacity(competitor_request, adapter.competitor.reservation_id, 'LOST')

    runtime[0][2].portal.call(free)
    service.capacity = port
    if cut == 'before_assess':
        newer = replace(attempt.principal, attempt_id='new-candidate')
        retry = service.prepare(principal=newer, request=replace(attempt.request, attempt_id=newer.attempt_id), claim_generation=0)
        aid = retry.request.attempt_id
    restored = runtime[0][2].portal.call(service.reserve, aid)
    assert restored.state == 'RESERVED'
    done = runtime[0][2].portal.call(service.release, aid)
    assert not done.active
    # A delayed held observation cannot resurrect a terminal reservation.
    with runtime[0][0].connection_factory.unit_of_work() as uow:
        assert service.repository.observe(uow, aid, restored.reservation) == done


def test_cancelled_reserve_keeps_original_identity_and_recovers_held_slot(runtime):
    service, port, attempt, hid, gid = prepared(runtime)
    aid = attempt.request.attempt_id

    async def scenario():
        held = asyncio.Event()

        class CancelledReply(ObservedPort):
            async def try_reserve_capacity(self, req):
                self.reservation = await super().try_reserve_capacity(req)
                held.set()
                await asyncio.Future()

        adapter = CancelledReply(runtime, port)
        service.capacity = adapter
        task = asyncio.create_task(service.reserve(aid))
        try:
            await asyncio.wait_for(held.wait(), 5)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert service.get(aid).state == 'NEEDS_RECONCILIATION'
        resumed = build_handoff_runtime_attempts(runtime[0][0], capacity=adapter)
        recovered = await resumed.reserve(aid)
        assert recovered.reservation.reservation_id == adapter.reservation.reservation_id
        assert adapter.reserves == 1
        assert not (await resumed.release(aid)).active

    runtime[0][2].portal.call(scenario)
    assert_unclaimed(runtime, hid, gid)


def test_failed_preflight_can_be_retired_without_a_reservation_rpc(runtime):
    service, port, attempt, hid, gid = prepared(runtime)
    aid = attempt.request.attempt_id

    class Unreachable:
        async def assess_capacity(self, req):
            raise TimeoutError('Disconnected during read-only assessment')

        def __getattr__(self, name):
            raise AssertionError('No reserve/get/release was needed for an unsent attempt')

    service.capacity = Unreachable()
    with pytest.raises(TimeoutError):
        runtime[0][2].portal.call(service.reserve, aid)
    failed = service.get(aid)
    assert failed.active and not failed.reserve_started
    retired = runtime[0][2].portal.call(service.release, aid)
    assert not retired.active and retired.state == 'CANCELLED_NO_EFFECT'
    assert_unclaimed(runtime, hid, gid)
    service.capacity = port
    next_principal = replace(attempt.principal, attempt_id='after-preflight-failure')
    new = service.prepare(principal=next_principal,
        request=replace(attempt.request, attempt_id=next_principal.attempt_id), claim_generation=0)
    assert runtime[0][2].portal.call(service.reserve, new.request.attempt_id).state == 'RESERVED'
    assert not runtime[0][2].portal.call(service.release, new.request.attempt_id).active


def test_absent_sent_attempt_is_retired_after_automation_authority_is_revoked(runtime):
    from test_runtime_policy_defaults import save
    service, port, attempt, hid, gid = prepared(runtime)
    aid = attempt.request.attempt_id

    class Disconnected(ObservedPort):
        async def try_reserve_capacity(self, req):
            raise TimeoutError('The reserve request may still be in transit')

    service.capacity = Disconnected(runtime, port)
    with pytest.raises(TimeoutError):
        runtime[0][2].portal.call(service.reserve, aid)
    assert service.get(aid).reserve_started
    assert save(runtime[0], agent='subject', broadcast_handoff_auto_claim=False).status_code == 200
    service.capacity = port
    done = runtime[0][2].portal.call(service.release, aid)
    assert done.state == 'CANCELLED_NO_EFFECT' and not done.active
    assert done.reservation.state == 'RELEASED' and done.reservation.consumption is None
    assert_unclaimed(runtime, hid, gid)


def test_disappearing_known_reservation_is_not_replaced_with_a_no_effect_record(runtime):
    service, port, attempt, hid, gid = prepared(runtime)
    aid = attempt.request.attempt_id
    held = runtime[0][2].portal.call(service.reserve, aid)

    class LostHistory:
        async def get_capacity_reservation(self, req):
            return None

        async def release_capacity(self, *args):
            raise AssertionError('Missing known history must not be overwritten by a terminal record')

    service.capacity = LostHistory()
    uncertain = runtime[0][2].portal.call(service.release, aid)
    assert uncertain.active and uncertain.state == 'NEEDS_RECONCILIATION'
    assert uncertain.reservation == held.reservation
    assert_unclaimed(runtime, hid, gid)
    service.capacity = port
    assert not runtime[0][2].portal.call(service.release, aid).active
