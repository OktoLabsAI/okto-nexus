"""Productive worker ownership survives native receipts until the call returns."""
import asyncio
import threading

import pytest
from nexus_connector_core import RuntimeEvent
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, connect_local, admit, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_identity_lifecycle import second_binding
from test_agent_recovery_isolation import create_agent, eventually
from test_sender_sessions import Peers


@pytest.mark.parametrize('cut', ['before_write', 'after_receipt'])
def test_retained_worker_does_not_donate_agent_capacity_or_block_healthy_agent(connected_local, monkeypatch, cut):
    setup, first_binding, _ = connected_local
    healthy_setup, healthy_binding, _ = connect_local(create_agent(setup, 'healthy'), agent_id='healthy')
    extra = second_binding(setup, monkeypatch)
    owner = setup[1].state.embedded_dispatch_owner
    peers = Peers()
    owner.native_factory = peers
    opened = []
    for current, binding in ((setup, first_binding), (setup, extra), (healthy_setup, healthy_binding)):
        operation = admit(current, binding, 'capacity-open-' + binding['binding_id'], 'runtime.start', new_session=True)
        wait_receipt(current, operation)
        opened.append(operation)
    original = owner._execute
    entered, release = threading.Event(), asyncio.Event()
    async def held(frame):
        targeted = frame['action'] == 'turn.submit' and frame['session_id'] == opened[0]['session_id']
        if targeted and cut == 'before_write':
            entered.set()
            await release.wait()
        await original(frame)
        if targeted and cut == 'after_receipt':
            entered.set()
            await release.wait()
    monkeypatch.setattr(owner, '_execute', held)
    try:
        first = admit(setup, first_binding, 'capacity-first', 'turn.submit',
                      session_id=opened[0]['session_id'], text='Retain this native worker')
        assert entered.wait(10)
        assert first['operation_id'] in owner.active_operations
        if cut == 'after_receipt':
            wait_receipt(setup, first)
            with setup[0].connection_factory.unit_of_work(write=False) as uow:
                stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams WHERE session_id=?',
                    (first['session_id'],)).fetchone())
            setup[2].portal.call(peers.sessions[first['session_id']].queue.put, RuntimeEvent(
                stream['server_id'], stream['executor_id'], stream['session_id'], stream['stream_epoch'], 0,
                'turn_state', 'fixture.capacity.complete',
                dict(delivery_phase='terminal', delivery_outcome='success', output_text='Captured while worker retained'),
                operation_id=first['operation_id']))
            def captured():
                with setup[0].connection_factory.unit_of_work(write=False) as uow:
                    return uow.connection.execute("SELECT 1 FROM execution_event_ingress WHERE session_id=? "
                        "AND payload_json LIKE '%fixture.capacity.complete%'", (first['session_id'],)).fetchone()
            eventually(captured)
        sibling = admit(setup, extra, 'capacity-sibling', 'turn.submit',
                        session_id=opened[1]['session_id'], text='Wait for this agent worker')
        healthy = admit(healthy_setup, healthy_binding, 'capacity-healthy', 'turn.submit',
                        session_id=opened[2]['session_id'], text='Independent healthy work')
        wait_receipt(healthy_setup, healthy)
        assert not release.is_set()
        assert first['operation_id'] in owner.active_operations
        assert peers.sessions[opened[1]['session_id']].sent == []
        assert len(peers.sessions[opened[2]['session_id']].sent) == 1
    finally:
        setup[2].portal.call(release.set)
    wait_receipt(setup, first)
    wait_receipt(setup, sibling)
    assert len(peers.sessions[opened[0]['session_id']].sent) == 1
    assert len(peers.sessions[opened[1]['session_id']].sent) == 1
