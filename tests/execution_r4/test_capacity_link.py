"""Capacity wire correlation, retained sends and durable lost-result recovery."""
import asyncio
from dataclasses import replace

import pytest
from nexus_connector_core import (
    CAPACITY_CONTRACT_REVISION, CapacityAssessment, CapacityRequest, CapacityScope,
    CoreError, SQLiteOwnedSlotLedger, ExecutionCapacity, decode_capacity_frame,
    execute_capacity_control, capacity_denial_frame,
)
from okto_nexus.adapters.outbound.execution.capacity_link import CapacityLinkClient
from okto_nexus.application.execution_leases import ExecutionChannel


CHANNEL = ExecutionChannel('srv', 'exe', 'connection', 1)


def request(name='first'):
    return CapacityRequest(CAPACITY_CONTRACT_REVISION, name, CapacityScope(
        'srv', 'exe', 'agent', 'binding', 'workspace', 'wxb', name, 1, 1, 1, 1, 1, 1, 'owner'),
        'new_session', 'sha256:' + ('a' if name == 'first' else 'b') * 64, 10_000)


async def verified(request, *, action):
    return None


def client(send, **kwargs):
    return CapacityLinkClient(channel=kwargs.pop('channel', CHANNEL), send=send,
        verify=kwargs.pop('verify', verified), capabilities=(CAPACITY_CONTRACT_REVISION,), **kwargs)


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0)


def test_out_of_order_results_are_correlated_and_scope_cannot_be_substituted():
    async def run():
        sent = asyncio.Queue()
        port = client(sent.put)
        calls = [asyncio.create_task(port.assess_capacity(request(name))) for name in ('first', 'second')]
        try:
            frames = [decode_capacity_frame((await sent.get()).encode()) for _ in range(2)]
            for field, value in [('server_id', 'foreign'), ('connection_generation', 2), ('connection_id', 'old')]:
                with pytest.raises(CoreError, match='SCOPE_MISMATCH'):
                    port.accept_result(capacity_denial_frame(frames[0], 'HOST_FULL') | {field: value})
            wrong = capacity_denial_frame(frames[1], 'HOST_FULL') | {'request_id': frames[0]['request_id']}
            with pytest.raises(CoreError, match='RESERVATION_CONFLICT'):
                port.accept_result(wrong)
            assert port.accept_result(capacity_denial_frame(frames[1], 'HOST_FULL'))
            assert port.accept_result(capacity_denial_frame(frames[0], 'BUSY_AFFINITY'))
            results = await asyncio.gather(*calls)
            assert [r.reason for r in results] == ['BUSY_AFFINITY', 'HOST_FULL']
            assert not port.accept_result(capacity_denial_frame(frames[0], 'BUSY_AFFINITY'))
        finally:
            await port.aclose()
            await asyncio.gather(*calls, return_exceptions=True)
    asyncio.run(run())


def test_timeout_preserves_attempt_and_reconnect_lookup_returns_durable_reservation(tmp_path):
    async def run():
        ledger = SQLiteOwnedSlotLedger(tmp_path / 'slots.db', max_slots=1)
        class Authority:
            async def check_capacity_scope(self, request, *, action):
                return 'AVAILABLE'
        service = ExecutionCapacity(ledger, authority=Authority(), runtime_lookup=lambda _: None, boot_id='owner')
        stored = []
        async def dropped(raw):
            stored.append(await execute_capacity_control(service, decode_capacity_frame(raw.encode())))
        first = client(dropped, request_timeout=.03)
        second = None
        try:
            with pytest.raises(CoreError, match='NEEDS_RECONCILIATION'):
                await first.try_reserve_capacity(request())
            assert stored[0]['result']['state'] == 'HELD'
            await first.aclose()
            async def delivered(raw):
                response = await execute_capacity_control(service, decode_capacity_frame(raw.encode()))
                second.accept_result(response)
            second = client(delivered, channel=replace(CHANNEL, connection_generation=2, connection_id='replacement'))
            found = await second.get_capacity_reservation(request())
            assert found.reservation_id == stored[0]['result']['reservation_id']
            assert len((await ledger.owned_slot_page()).reservations) == 1
            with pytest.raises(CoreError, match='VALIDATION_ERROR'):
                await second.try_reserve_capacity(request())  # Cannot reacquire using stale generation.
            assert (await second.release_capacity(request(), found.reservation_id, 'LOST')).state == 'RELEASED'
        finally:
            await first.aclose()
            if second:
                await second.aclose()
            await service.aclose()
            ledger.close()
    asyncio.run(run())


def test_slow_sender_stays_bounded_and_recovery_has_separate_capacity():
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        port = None
        async def send(raw):
            frame = decode_capacity_frame(raw.encode())
            if frame['type'] == 'capacity.reserve':
                entered.set()
                await release.wait()
            port.accept_result(capacity_denial_frame(frame, 'NOT_AUTHORIZED'))
        port = client(send, request_timeout=.03, max_requests=1)
        call = asyncio.create_task(port.try_reserve_capacity(request()))
        try:
            await entered.wait()
            with pytest.raises(CoreError, match='NEEDS_RECONCILIATION'):
                await call
            assert len(port._producers) == 1
            with pytest.raises(CoreError, match='STALE_OBSERVATION'):
                await port.try_reserve_capacity(request('second'))
            with pytest.raises(CoreError, match='NOT_AUTHORIZED'):
                await port.get_capacity_reservation(request())
            release.set()
            await until(lambda: not port._producers)
        finally:
            release.set()
            await port.aclose()
    asyncio.run(run())


def test_cancelled_waiter_does_not_cancel_send_and_post_send_revocation_is_uncertain():
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        checks = []
        async def verify(req, *, action):
            checks.append(action)
            if len(checks) > 1:
                raise CoreError('NOT_AUTHORIZED', 'revoked')
        async def send(raw):
            entered.set()
            await release.wait()
            frame = decode_capacity_frame(raw.encode())
            port.accept_result(capacity_denial_frame(frame, 'HOST_FULL'))
        port = client(send, verify=verify)
        waiter = asyncio.create_task(port.try_reserve_capacity(request()))
        try:
            await entered.wait()
            retained = next(iter(port._producers))
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
            assert not retained.cancelled()
            release.set()
            with pytest.raises(CoreError, match='NEEDS_RECONCILIATION') as result:
                await retained
            assert result.value.possible_effect
        finally:
            release.set()
            await port.aclose()
    asyncio.run(run())


def test_missing_support_or_local_scope_refusal_never_sends():
    async def run():
        sent = []
        async def send(raw):
            sent.append(raw)
        for unsupported in ((), CAPACITY_CONTRACT_REVISION):
            with pytest.raises(CoreError, match='CAPACITY_PROTOCOL_UNSUPPORTED'):
                CapacityLinkClient(channel=CHANNEL, send=send, verify=verified, capabilities=unsupported)
        port = client(send)
        try:
            req = request()
            with pytest.raises(CoreError, match='NOT_AUTHORIZED'):
                await port.try_reserve_capacity(replace(req, scope=replace(req.scope, agent_id='x', executor_id='other')))
            assert not sent
        finally:
            await port.aclose()
    asyncio.run(run())
