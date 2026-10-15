"""Owned sender faults with actual admission, SQLite CAS, and retained barriers."""

import asyncio
import json
from pathlib import Path
import threading

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
import pytest

from okto_nexus.adapters.outbound.sqlite.execution_dispatch_ownership import recover_fenced_reservations
from okto_nexus.adapters.outbound.sqlite.execution_receipts import read_execution_operation_history
from okto_nexus.adapters.outbound.sqlite.execution_tickets import verify_execution_ticket
from okto_nexus.application import execution_dispatch_pump as pumps
from okto_nexus.application.execution_dispatch import begin_execution_send, reserve_execution_dispatch, release_unsent_dispatch
from okto_nexus.application.execution_leases import ExecutionChannel
from okto_nexus.errors import OktoNexusError

from test_ns09 import setup_authority, negotiate, admit


@pytest.fixture
def owner(tmp_path, monkeypatch):
    state = setup_authority(tmp_path, monkeypatch)
    deps, app, access, operator, grant, candidate, info, revisions, link, lane, server, executor = state
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor}/link',
                headers={'Authorization': f'Bearer {link}'}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane, server, executor)
            resolution = admit(deps, app)
            yield deps, app, access, operator, grant, channel, resolution, link


def view(state):
    deps, _, _, _, _, channel, resolution, _ = state
    return read_execution_operation_history(deps.connection_factory,
        server_id=channel.server_id, executor_id=channel.executor_id,
        operation_id=resolution['operation_id'], subject_agent_id='subject').public_view()


def make_pump(state, send, lock, closed, **options):
    deps, app, access, _, _, channel, _, link = state
    def verify():
        return verify_execution_ticket(deps.connection_factory, ticket=link,
            server_id=channel.server_id, executor_id=channel.executor_id, scope='link:connect')
    async def close():
        closed.set()
    return pumps.ExecutionDispatchPump(factory=deps.connection_factory, channel=channel,
        access=access, fresh_publications=app.state.inventory_fresh_publications,
        send=send, send_lock=lock, verify_link=verify, close_link=close, poll_interval=0.01, **options)


async def wait_for_state(state, expected):
    async def wait():
        while True:
            with state[0].connection_factory.unit_of_work(write=False) as uow:
                row = uow.connection.execute('SELECT * FROM execution_dispatch_outbox').fetchone()
                if row['dispatch_state'] == expected:
                    return dict(row)
            await asyncio.sleep(0.01)
    return await asyncio.wait_for(wait(), 3)


def test_dispatch_revalidates_after_writer_wait_and_exposes_terminal_rejection(owner):
    async def run():
        deps, app, access, operator, grant, channel, resolution, _ = owner
        lock, closed, sent = asyncio.Lock(), asyncio.Event(), []
        notified = asyncio.Event()
        def wake_deliveries():
            assert view(owner)['admission_state'] == 'RESOLVED_TERMINAL'
            notified.set()
        async def send(frame):
            sent.append(frame)
        await lock.acquire()
        pump = make_pump(owner, send, lock, closed, wake_deliveries=wake_deliveries)
        pump.start()
        try:
            row = await wait_for_state(owner, 'RESERVED')
            assert row['reserved_bytes'] > 0 and row['reservation_owner'] == channel.connection_id
            access.revoke(operator, grant_id=grant['grant_id'])
            assert not sent and not pump.task.done()  # The lock barrier is still retained.
            lock.release()
            rejected = await wait_for_state(owner, 'RESOLVED_TERMINAL')
            await asyncio.wait_for(notified.wait(), 3)
            assert rejected['reserved_bytes'] == 0 and rejected['reservation_class'] is None
            observed = view(owner)
            assert observed['admission_state'] == 'RESOLVED_TERMINAL'
            assert observed['executor_stage'] is None and observed['receipt_revision'] == 0
            assert not observed['possible_effect'] and not observed['retry_safe']
            assert observed['error']['code'] == 'PERMISSION_DENIED'
            schema = json.loads((Path(__file__).resolve().parents[2] / 'plans/contratos/http-target.schema.json').read_text())
            Draft202012Validator({'$defs': schema['$defs'], **schema['$defs']['OperationView']}).validate(observed)
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions').fetchone()[0] == 'FAILED'
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_receipts').fetchone()[0] == 0
            assert not sent and not closed.is_set()
        finally:
            if lock.locked():
                lock.release()
            await pump.stop()
    asyncio.run(run())


def test_dispatch_send_loss_is_unknown_and_never_requeued(owner):
    async def run():
        deps, app, access, _, _, channel, resolution, _ = owner
        sent, closed = [], asyncio.Event()
        async def send(frame):
            sent.append(frame)
            # Emulates a transport error after bytes may have reached the peer.
            raise OSError('Injected socket failure after possible delivery')
        pump = make_pump(owner, send, asyncio.Lock(), closed)
        pump.start()
        await asyncio.wait_for(asyncio.shield(pump.task), 3)
        assert closed.is_set() and isinstance(pump.error, OSError)
        assert len(sent) == 1 and sent[0]['operation_id'] == resolution['operation_id']
        row = await wait_for_state(owner, 'RECONCILING')
        assert row['reserved_bytes'] > 0 and row['attempt_no'] == 1
        observed = view(owner)
        assert observed['admission_state'] == 'RECONCILING'
        assert observed['possible_effect'] and not observed['retry_safe']
        assert observed['executor_stage'] is None and observed['receipt_revision'] == 0
        assert observed['error']['code'] == 'DISPATCH_CONNECTION_LOST'
        assert reserve_execution_dispatch(deps.connection_factory, server_id=channel.server_id,
            executor_id=channel.executor_id, remote_ready=True, channel=channel) is None
        with pytest.raises(OktoNexusError, match='no longer unsent'):
            from okto_nexus.application.execution_dispatch import DispatchReservation
            release_unsent_dispatch(deps.connection_factory, reservation=DispatchReservation(
                channel.server_id, channel.executor_id, row['operation_id'], row['attempt_token'],
                row['attempt_no'], row['reservation_class'], row['reserved_bytes'],
                row['reservation_owner'], row['reservation_generation']))
    asyncio.run(run())


def test_cancelled_stop_waiter_keeps_database_producer_owned(owner, monkeypatch):
    async def run():
        entered, release = threading.Event(), threading.Event()
        original = pumps.reserve_execution_dispatch
        def delayed(**kwargs):
            reservation = original(**kwargs)
            entered.set()
            assert release.wait(5)
            return reservation
        monkeypatch.setattr(pumps, 'reserve_execution_dispatch', delayed)
        sent, closed = [], asyncio.Event()
        async def send(frame):
            sent.append(frame)
        pump = make_pump(owner, send, asyncio.Lock(), closed)
        pump.start()
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            row = await wait_for_state(owner, 'RESERVED')
            assert row['reservation_owner'] == owner[5].connection_id
            waiter = asyncio.create_task(pump.stop())
            await asyncio.sleep(0)
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
            assert not pump.task.done() and not release.is_set() and not sent
        finally:
            release.set()
            await asyncio.wait_for(pump.stop(), 3)
        row = await wait_for_state(owner, 'PENDING')
        assert row['reserved_bytes'] == 0 and row['attempt_token'] is None
        assert row['reservation_owner'] is None and not sent
        assert not view(owner)['possible_effect']
    asyncio.run(run())


def test_old_connection_cannot_send_after_owned_reservation_recovery(owner):
    deps, app, access, _, _, channel, _, _ = owner
    factory = deps.connection_factory
    reservation = reserve_execution_dispatch(factory, server_id=channel.server_id,
        executor_id=channel.executor_id, remote_ready=True, channel=channel)
    replacement = ExecutionChannel(channel.server_id, channel.executor_id, 'replacement', channel.connection_generation + 1)
    with factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE execution_executors SET owner_instance_id=?,generation=? WHERE executor_id=?',
            (replacement.connection_id, replacement.connection_generation, channel.executor_id))
    with pytest.raises(OktoNexusError, match='owner changed'):
        begin_execution_send(factory, reservation=reservation, remote_ready=True,
            access=access, fresh_publications=app.state.inventory_fresh_publications, channel=channel)
    with pytest.raises(OktoNexusError, match='no longer the owner'):
        recover_fenced_reservations(factory, channel=channel)
    assert recover_fenced_reservations(factory, channel=replacement) == 1
    assert recover_fenced_reservations(factory, channel=replacement) == 0
    new = reserve_execution_dispatch(factory, server_id=channel.server_id,
        executor_id=channel.executor_id, remote_ready=True, channel=replacement)
    assert new.attempt_token != reservation.attempt_token and new.attempt_no == 2
    with pytest.raises(OktoNexusError, match='reservation changed'):
        begin_execution_send(factory, reservation=reservation, remote_ready=True,
            access=access, fresh_publications=app.state.inventory_fresh_publications, channel=channel)
    with pytest.raises(OktoNexusError):
        release_unsent_dispatch(factory, reservation=reservation)
    with factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute('SELECT reservation_owner,attempt_token,reserved_bytes FROM execution_dispatch_outbox').fetchone()
        assert tuple(row) == (replacement.connection_id, new.attempt_token, new.reserved_bytes)
    release_unsent_dispatch(factory, reservation=new)
