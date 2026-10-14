"""Capacity uses real ticket-authenticated Server WebSocket/lane admission.

The remote capacity adapter is a synthetic host with a real durable Core
ledger. This is an in-process integration test, not remote-host qualification.
"""
import asyncio
from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from nexus_connector_core import (
    CAPACITY_CONTRACT_REVISION, CapacityScope, CapacityRequest, SQLiteOwnedSlotLedger,
    ExecutionCapacity, encode_capacity_frame, decode_capacity_frame, execute_capacity_control,
)

from test_ns09 import setup_authority, negotiate


def changed(channel, **updates):
    return dict(contract_revision=CAPACITY_CONTRACT_REVISION, type='capacity.changed',
        **asdict(channel), binding_id='binding', boot_id='host-clock', capacity_revision=0,
        reason='STALE_OBSERVATION', valid_for_ms=30000) | updates


async def wait_for_binding(registry, channel):
    async with asyncio.timeout(3):
        while True:
            host = registry.current_host(channel.server_id, channel.executor_id)
            if host is not None and 'binding' in host.observations:
                return host
            await asyncio.sleep(.001)


def test_authenticated_capacity_reservation_lookup_release_and_disconnect(tmp_path, monkeypatch):
    deps, app, _, _, _, _, info, revisions, ticket, lane, server, executor = setup_authority(tmp_path, monkeypatch)
    registry = deps.runtime_availability
    registry.enabled = True
    ledger = SQLiteOwnedSlotLedger(tmp_path / 'remote-slots.db', max_slots=1)
    class Authority:
        async def check_capacity_scope(self, request, *, action):
            return 'AVAILABLE'
    service = ExecutionCapacity(ledger, authority=Authority(), boot_id='host-clock',
        namespace=(server, executor), runtime_lookup=lambda session: None)
    try:
        with TestClient(app, base_url='https://127.0.0.1:8202') as client:
            with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor}/link',
                    headers={'Authorization': 'Bearer ' + ticket}, subprotocols=['nxl.v1']) as ws:
                channel = negotiate(ws, info, revisions, lane, server, executor,
                                    control_capabilities=[CAPACITY_CONTRACT_REVISION])
                ws.send_text(encode_capacity_frame(changed(channel)).decode())
                host = client.portal.call(wait_for_binding, registry, channel)
                assert host.boot_id == 'host-clock'
                req = CapacityRequest(CAPACITY_CONTRACT_REVISION, 'original-attempt', CapacityScope(
                    server, executor, 'subject', 'binding', 'ws', 'wxb', 'proposed', channel.connection_generation,
                    1, revisions.authorization, revisions.configuration, 1, revisions.credential_epoch, 'host-clock'),
                    'new_session', 'sha256:' + 'a' * 64, 30000)
                def round_trip(method, *extra):
                    future = client.portal.start_task_soon(method, req, *extra)
                    frame = decode_capacity_frame(ws.receive_text().encode())
                    result = client.portal.call(execute_capacity_control, service, frame)
                    ws.send_text(encode_capacity_frame(result).decode())
                    return future.result(timeout=5)
                held = round_trip(registry.try_reserve_capacity)
                assert held.state == 'HELD'
                assert round_trip(registry.get_capacity_reservation).reservation_id == held.reservation_id
                assert round_trip(registry.release_capacity, held.reservation_id, 'LOST').state == 'RELEASED'
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    for table in ('execution_operations', 'execution_sessions'):
                        assert uow.connection.execute('SELECT count(*) FROM ' + table).fetchone()[0] == 0
            async def disconnected():
                async with asyncio.timeout(3):
                    while registry.current_host(server, executor) is not None:
                        await asyncio.sleep(.001)
            client.portal.call(disconnected)
    finally:
        asyncio.run(service.aclose())
        ledger.close()


def test_authenticated_dispatch_wait_changes_only_flow_and_rejects_conflicting_sequence(tmp_path, monkeypatch):
    from test_ns09 import admit
    from okto_nexus.application.execution_dispatch import reserve_execution_dispatch, begin_execution_send
    deps, app, access, _, _, _, info, revisions, ticket, lane, server, executor = setup_authority(tmp_path, monkeypatch)
    deps.runtime_availability.enabled = True
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor}/link',
                headers={'Authorization': 'Bearer ' + ticket}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane, server, executor,
                                control_capabilities=[CAPACITY_CONTRACT_REVISION])
            resolution = admit(deps, app)
            reservation = reserve_execution_dispatch(deps.connection_factory, server_id=server,
                executor_id=executor, remote_ready=True, channel=channel)
            source = begin_execution_send(deps.connection_factory, reservation=reservation, remote_ready=True,
                access=access, fresh_publications=app.state.inventory_fresh_publications, channel=channel).frame
            frame = {k: source[k] for k in ('server_id', 'executor_id', 'connection_id', 'connection_generation',
                'binding_id', 'agent_id', 'session_id', 'operation_id', 'intent_hash', 'action')} | dict(
                    type='capacity.dispatch_state', contract_revision=CAPACITY_CONTRACT_REVISION,
                    state='WAITING', sequence=1)
            ws.send_text(encode_capacity_frame(frame).decode())
            async def wait_flow():
                async with asyncio.timeout(3):
                    while True:
                        with deps.connection_factory.unit_of_work(write=False) as uow:
                            row = uow.connection.execute('SELECT state FROM execution_capacity_waits WHERE operation_id=?',
                                                         (resolution['operation_id'],)).fetchone()
                            if row is not None:
                                assert row['state'] == 'WAITING'
                                assert uow.connection.execute('SELECT COUNT(*) FROM execution_receipts').fetchone()[0] == 0
                                return
                        await asyncio.sleep(.01)
            client.portal.call(wait_flow)
            ws.send_text(encode_capacity_frame(dict(frame, state='RUNNING')).decode())
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_text()
            assert closed.value.code == 4403


@pytest.mark.parametrize('fault', ['disabled', 'unoffered', 'foreign_binding', 'old_connection'])
def test_capacity_notifications_require_negotiation_current_link_and_admitted_lane(tmp_path, monkeypatch, fault):
    deps, app, _, _, _, _, info, revisions, ticket, lane, server, executor = setup_authority(tmp_path, monkeypatch)
    deps.runtime_availability.enabled = fault != 'disabled'
    offered = [] if fault == 'unoffered' else [CAPACITY_CONTRACT_REVISION]
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor}/link',
                headers={'Authorization': 'Bearer ' + ticket}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane, server, executor, control_capabilities=offered)
            updates = {'binding_id': 'unattached'} if fault == 'foreign_binding' else (
                {'connection_id': 'old-owner'} if fault == 'old_connection' else {})
            ws.send_text(encode_capacity_frame(changed(channel, **updates)).decode())
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_text()
            assert closed.value.code == 4406
