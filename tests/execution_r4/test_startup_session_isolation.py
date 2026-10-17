"""A failed opening must not stop another session of the same agent."""
import asyncio
import threading
import pytest
from nexus_connector_core import LocalRuntimeCore
from nexus_connector_core.native.adapter_types import NativeAdapterError, ErrorCode

from test_agent_recovery_isolation import eventually
from test_embedded_dispatch import local_setup, connect_local, admit, wait_receipt
from test_sender_sessions import Peers


@pytest.mark.parametrize('local_setup', ['pi_rpc', 'codex_app_server', 'claude_stream'], indirect=True)
@pytest.mark.parametrize('stage', ['prepare', 'native'])
def test_startup_failure_preserves_healthy_sibling(local_setup, monkeypatch, stage):
    setup, binding, _ = connect_local(local_setup)
    owner = setup[1].state.embedded_dispatch_owner
    peers = Peers()
    owner.native_factory = peers
    healthy = admit(setup, binding, 'healthy-open', 'runtime.start', new_session=True)
    wait_receipt(setup, healthy)
    healthy_peer = peers.sessions[healthy['session_id']]
    generation = owner.channel.connection_generation
    injected = []
    prepare, native_open = LocalRuntimeCore.prepare, peers.open

    def fail():
        injected.append(True)
        raise NativeAdapterError(ErrorCode.CONFIG_ERROR, 'Version probe deadline',
                                 {'reason': 'version_probe_timeout'})

    async def fail_prepare(runtime, *args, **kwargs):
        if not injected:
            fail()
        return await prepare(runtime, *args, **kwargs)

    async def fail_native(prepared, session_id, context, *, stream_epoch, process_launch):
        if not injected:
            return await process_launch.produce(validate_authority=lambda: None, start=fail)
        return await native_open(prepared, session_id, context, stream_epoch=stream_epoch)

    if stage == 'prepare':
        monkeypatch.setattr(LocalRuntimeCore, 'prepare', fail_prepare)
    else:
        monkeypatch.setattr(peers, 'open', fail_native)
    failed = admit(setup, binding, 'failed-open', 'runtime.start', new_session=True)
    eventually(lambda: bool(injected))

    def settled():
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions '
                'WHERE session_id=?', (failed['session_id'],)).fetchone()
        return tuple(row) in (('CLOSED', 'CLOSED'), ('FAILED', 'CLOSED'))

    eventually(settled, seconds=45)
    assert not healthy_peer.stopped, 'Startup failure stopped a healthy sibling session'
    assert 'subject' not in owner.agents.blocked
    assert owner.failure is None
    assert owner.channel.connection_generation == generation
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        causes = uow.connection.execute("SELECT message FROM runtime_recovery_events "
            "WHERE code='RECOVERY_SESSION_BLOCKED' AND agent_id='subject'").fetchall()
        assert any(failed['session_id'] in row[0] and 'version_probe_timeout' in row[0] for row in causes)
    turn = admit(setup, binding, 'healthy-turn', 'turn.submit',
                 session_id=healthy['session_id'], text='Still available')
    wait_receipt(setup, turn)
    next_open = admit(setup, binding, 'next-open', 'runtime.start', new_session=True)
    wait_receipt(setup, next_open)
    assert len(peers.sessions) == 2
    for index, session in enumerate((healthy, next_open)):
        wait_receipt(setup, admit(setup, binding, f'close-{index}', 'runtime.close',
            session_id=session['session_id']), stages=('SUCCEEDED',))


def test_slow_startup_containment_keeps_sibling_and_new_open_available(local_setup, monkeypatch):
    setup, binding, _ = connect_local(local_setup)
    owner = setup[1].state.embedded_dispatch_owner
    peers = Peers()
    owner.native_factory = peers
    healthy = admit(setup, binding, 'healthy', 'runtime.start', new_session=True)
    wait_receipt(setup, healthy)
    prepare, shutdown = LocalRuntimeCore.prepare, LocalRuntimeCore.shutdown
    target = []
    entered, release = threading.Event(), threading.Event()

    async def fail_prepare(runtime, *args, **kwargs):
        if not target:
            target.append(runtime)
            raise NativeAdapterError(ErrorCode.CONFIG_ERROR, 'Unavailable', {'reason': 'version_probe_timeout'})
        return await prepare(runtime, *args, **kwargs)

    async def held_shutdown(runtime, *args, **kwargs):
        if target and runtime is target[0]:
            entered.set()
            while not release.is_set():
                await asyncio.sleep(.01)
        return await shutdown(runtime, *args, **kwargs)

    monkeypatch.setattr(LocalRuntimeCore, 'prepare', fail_prepare)
    monkeypatch.setattr(LocalRuntimeCore, 'shutdown', held_shutdown)
    try:
        failed = admit(setup, binding, 'slow-failed', 'runtime.start', new_session=True)
        assert entered.wait(15)
        worker = owner.agents.session_tasks[failed['session_id']]
        wait_receipt(setup, admit(setup, binding, 'healthy-during-stop', 'turn.submit',
            session_id=healthy['session_id'], text='Available during containment'))
        fresh = admit(setup, binding, 'new-during-stop', 'runtime.start', new_session=True)
        wait_receipt(setup, fresh)
        assert not worker.done()
        assert owner.agents.session_tasks[failed['session_id']] is worker
        assert 'subject' not in owner.agents.blocked
        assert not peers.sessions[healthy['session_id']].stopped
    finally:
        release.set()
    eventually(lambda: failed['session_id'] not in owner.sessions, seconds=30)
    for index, session in enumerate((healthy, fresh)):
        wait_receipt(setup, admit(setup, binding, f'close-slow-{index}', 'runtime.close',
            session_id=session['session_id']), stages=('SUCCEEDED',))
