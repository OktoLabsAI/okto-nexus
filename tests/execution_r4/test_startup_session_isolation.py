"""A failed opening must not stop another session of the same agent."""
# Imported fixtures are discovered by pytest from this module.
# ruff: noqa: F401, F811
import asyncio
import threading
from contextlib import contextmanager
import pytest
from starlette.testclient import TestClient
from nexus_connector_core import LocalRuntimeCore
from nexus_connector_core.native.adapter_types import NativeAdapterError, ErrorCode

from test_agent_recovery_isolation import eventually
from test_embedded_dispatch import local_setup, qualified_contract, connect_local, admit, wait_receipt
from test_sender_sessions import Peers
from test_embedded_inventory import app_for
from test_harness_canonical import qualified_bridge
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime
from test_reserved_handoff_admission import reserve
from okto_nexus.bootstrap.capacity_admission import build_capacity_admission


@pytest.mark.parametrize('capacity_enabled', [False, True])
def test_pre_authorization_open_failure_preserves_healthy_sibling(local_setup, monkeypatch, capacity_enabled):
    from okto_nexus.bootstrap import embedded_dispatch

    setup, binding, _ = connect_local(local_setup)
    owner = setup[1].state.embedded_dispatch_owner
    owner.host.capacity_enabled = capacity_enabled
    peers = Peers()
    owner.native_factory = peers
    healthy = admit(setup, binding, 'preauth-healthy-open', 'runtime.start', new_session=True)
    wait_receipt(setup, healthy)
    healthy_peer = peers.sessions[healthy['session_id']]
    original = embedded_dispatch.ApprovedLocalLaunch
    injected = []

    def fail_once(*args, **kwargs):
        if not injected:
            injected.append(True)
            raise NativeAdapterError(ErrorCode.CONFIG_ERROR, 'Local preparation refused',
                                     {'reason': 'preauthorization_fixture'})
        return original(*args, **kwargs)

    monkeypatch.setattr(embedded_dispatch, 'ApprovedLocalLaunch', fail_once)
    failed = admit(setup, binding, 'preauth-failed-open', 'runtime.start', new_session=True)
    eventually(lambda: bool(injected))
    eventually(lambda: failed['session_id'] not in owner.sessions, seconds=30)
    receipt = wait_receipt(setup, failed, stages=('FAILED',))
    assert receipt['executor_stage'] == 'FAILED'
    assert not healthy_peer.stopped, 'Pre-authorization failure stopped a healthy sibling'
    assert 'subject' not in owner.agents.blocked
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        terminal = conn.execute('SELECT stage,error_code,possible_effect,retry_safe '
            'FROM execution_receipts WHERE operation_id=?', (failed['operation_id'],)).fetchone()
        assert tuple(terminal) == ('FAILED', 'PREPARATION_FAILED', 0, 1)
        session = conn.execute('SELECT lifecycle_state,lease_state,local_retirement_json '
            'FROM execution_sessions WHERE session_id=?', (failed['session_id'],)).fetchone()
        assert session['lifecycle_state'] == session['lease_state'] == 'CLOSED'
        assert session['local_retirement_json'] is not None
        admissions = conn.execute('SELECT reservation_json FROM execution_capacity_admissions '
            'WHERE session_id=?', (failed['session_id'],)).fetchall()
        # Direct runtime messages do not reserve capacity before authorization.
        # A consumed prelease handoff needs its separate reservation test.
        assert not admissions
    turn = admit(setup, binding, 'preauth-healthy-turn', 'turn.submit',
                 session_id=healthy['session_id'], text='Still available')
    wait_receipt(setup, turn)


def test_pre_authorization_refusal_recovers_after_restart_before_server_receipt(tmp_path, monkeypatch):
    from okto_nexus.bootstrap import embedded_dispatch, embedded_startup_refusal

    with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, None) as setup:
        setup, binding, _ = connect_local(setup)
        owner = setup[1].state.embedded_dispatch_owner
        original = embedded_dispatch.ApprovedLocalLaunch
        failed_once = []

        def fail_once(*args, **kwargs):
            if not failed_once:
                failed_once.append(True)
                raise NativeAdapterError(ErrorCode.CONFIG_ERROR, 'Local preparation refused',
                                         {'reason': 'preauthorization_restart_fixture'})
            return original(*args, **kwargs)

        def hold_receipt(*args, **kwargs):
            raise OSError('Synthetic Server receipt interruption')

        with monkeypatch.context() as patch:
            patch.setattr(embedded_dispatch, 'ApprovedLocalLaunch', fail_once)
            patch.setattr(embedded_startup_refusal, 'append_execution_receipt', hold_receipt)
            failed = admit(setup, binding, 'preauth-restart-failed', 'runtime.start', new_session=True)
            def retained():
                with setup[0].connection_factory.unit_of_work(write=False) as uow:
                    return uow.connection.execute('SELECT 1 FROM execution_local_startup_refusals '
                        'WHERE operation_id=? AND accepted_at IS NULL AND report_json IS NULL',
                        (failed['operation_id'],)).fetchone()
            eventually(retained)
            assert owner.failure is None

    deps, app = app_for(tmp_path / 'home')
    with TestClient(app) as client:
        owner = app.state.embedded_dispatch_owner
        restored = (deps, app, client, setup[3], *setup[4:])
        eventually(lambda: not owner.agents.blocked, seconds=30)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            conn = uow.connection
            assert tuple(conn.execute('SELECT stage,error_code,possible_effect FROM execution_receipts '
                'WHERE operation_id=?', (failed['operation_id'],)).fetchone()) == (
                    'FAILED', 'PREPARATION_FAILED', 0)
            assert conn.execute('SELECT local_retirement_json FROM execution_sessions '
                'WHERE session_id=?', (failed['session_id'],)).fetchone()[0] is not None
        owner.native_factory = Peers()
        fresh = admit(restored, binding, 'preauth-restart-fresh', 'runtime.start', new_session=True)
        wait_receipt(restored, fresh)
        assert owner.failure is None


def test_pre_authorization_refusal_storage_failure_retains_only_failed_session(local_setup, monkeypatch):
    from okto_nexus.bootstrap import embedded_dispatch, embedded_startup_refusal

    setup, binding, _ = connect_local(local_setup)
    owner = setup[1].state.embedded_dispatch_owner
    owner.native_factory = Peers()
    healthy = admit(setup, binding, 'preauth-storage-healthy', 'runtime.start', new_session=True)
    wait_receipt(setup, healthy)
    healthy_peer = owner.native_factory.sessions[healthy['session_id']]
    original_launch = embedded_dispatch.ApprovedLocalLaunch
    original_persist = embedded_startup_refusal.persist_r4_startup_refusal
    failed_once = []
    storage_restored = threading.Event()

    def fail_launch_once(*args, **kwargs):
        if not failed_once:
            failed_once.append(True)
            raise NativeAdapterError(ErrorCode.CONFIG_ERROR, 'Local preparation refused',
                                     {'reason': 'preauthorization_storage_fixture'})
        return original_launch(*args, **kwargs)

    async def fail_storage_until_restored(*args, **kwargs):
        if not storage_restored.is_set():
            raise OSError('Synthetic Core startup refusal storage failure')
        return await original_persist(*args, **kwargs)

    monkeypatch.setattr(embedded_dispatch, 'ApprovedLocalLaunch', fail_launch_once)
    monkeypatch.setattr(embedded_startup_refusal, 'persist_r4_startup_refusal', fail_storage_until_restored)
    failed = admit(setup, binding, 'preauth-storage-failed', 'runtime.start', new_session=True)
    try:
        def pending():
            with setup[0].connection_factory.unit_of_work(write=False) as uow:
                return uow.connection.execute("SELECT 1 FROM runtime_recovery_events "
                    "WHERE code='RECOVERY_SESSION_PENDING' AND agent_id='subject' "
                    "AND message LIKE '%OSError%' LIMIT 1").fetchone()
        eventually(pending, seconds=20)
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            conn = uow.connection
            assert conn.execute('SELECT 1 FROM execution_receipts WHERE operation_id=?',
                (failed['operation_id'],)).fetchone() is None
            assert conn.execute('SELECT lifecycle_state FROM execution_sessions WHERE session_id=?',
                (failed['session_id'],)).fetchone()[0] == 'OPEN_PENDING'
        assert not healthy_peer.stopped
        assert 'subject' not in owner.agents.blocked
        wait_receipt(setup, admit(setup, binding, 'preauth-storage-healthy-turn', 'turn.submit',
            session_id=healthy['session_id'], text='Still available'))
    finally:
        storage_restored.set()
    wait_receipt(setup, failed, stages=('FAILED',))
    eventually(lambda: failed['session_id'] not in owner.sessions, seconds=30)
    assert not healthy_peer.stopped


def test_authorizer_failure_after_core_composition_preserves_healthy_session(local_setup, monkeypatch):
    from okto_nexus.adapters.outbound.execution.embedded import EmbeddedExecutor

    setup, binding, _ = connect_local(local_setup)
    owner = setup[1].state.embedded_dispatch_owner
    owner.native_factory = Peers()
    healthy = admit(setup, binding, 'authorize-healthy', 'runtime.start', new_session=True)
    wait_receipt(setup, healthy)
    healthy_peer = owner.native_factory.sessions[healthy['session_id']]
    original = EmbeddedExecutor.authorize_r4
    composed = []

    async def fail_once(host, **kwargs):
        if not composed:
            scope = kwargs['scope']
            await host.acquire(server_id=scope['server_id'], executor_id=scope['executor_id'],
                session_id=scope['session_id'], candidates={kwargs['candidate'].adapter_id: kwargs['candidate']},
                workspace_roots={scope['workspace_id']: kwargs['workspace_root']},
                environment=kwargs['environment'], native_factory=kwargs['native_factory'],
                native_action_factory=kwargs['native_action_factory'],
                native_approvals_enabled=kwargs['native_approvals_enabled'])
            composed.append(scope['session_id'])
            raise OSError('Synthetic authorization interruption after Core composition')
        return await original(host, **kwargs)

    monkeypatch.setattr(EmbeddedExecutor, 'authorize_r4', staticmethod(fail_once))
    failed = admit(setup, binding, 'authorize-failed', 'runtime.start', new_session=True)
    eventually(lambda: bool(composed))
    wait_receipt(setup, failed, stages=('FAILED',))
    eventually(lambda: failed['session_id'] not in owner.sessions, seconds=30)
    assert not healthy_peer.stopped
    assert 'subject' not in owner.agents.blocked
    wait_receipt(setup, admit(setup, binding, 'authorize-healthy-turn', 'turn.submit',
        session_id=healthy['session_id'], text='Still available'))
    wait_receipt(setup, admit(setup, binding, 'authorize-fresh-open', 'runtime.start', new_session=True))


def test_consumed_handoff_preauthorization_refusal_releases_exact_reservation(runtime, monkeypatch):
    from okto_nexus.bootstrap import embedded_dispatch

    setup, binding, _ = runtime
    deps, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    owner.host.capacity_enabled = True
    service, hid, gid, port, held, claim = reserve(runtime)
    original = embedded_dispatch.ApprovedLocalLaunch
    injected = []

    def fail_once(*args, **kwargs):
        if not injected:
            injected.append(True)
            raise NativeAdapterError(ErrorCode.CONFIG_ERROR, 'Local preparation refused',
                                     {'reason': 'preauthorization_capacity_fixture'})
        return original(*args, **kwargs)

    monkeypatch.setattr(embedded_dispatch, 'ApprovedLocalLaunch', fail_once)
    claimed = claim()
    turn = claimed['runtime_operation']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        opening_id = uow.connection.execute('SELECT operation_id FROM execution_operations '
            "WHERE session_id=? AND action='runtime.open'", (held.request.scope.session_id,)).fetchone()[0]
    opening = dict(operation_id=opening_id, session_id=held.request.scope.session_id)
    assert client.portal.call(build_capacity_admission(deps, capacity=port).consume,
                              turn['operation_id']).state == 'CONSUMED'
    eventually(lambda: bool(injected))
    view = wait_receipt(setup, opening, stages=('FAILED',))
    assert view['executor_stage'] == 'FAILED'
    assert 'subject' not in owner.agents.blocked
    released = client.portal.call(port.get_capacity_reservation, held.request)
    assert released.state == 'RELEASED'
    assert released.reservation_id == held.reservation_id
    with deps.connection_factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        assert tuple(conn.execute('SELECT stage,error_code,possible_effect FROM execution_receipts '
            'WHERE operation_id=?', (opening['operation_id'],)).fetchone()) == (
            'FAILED', 'PREPARATION_FAILED', 0)
        assert conn.execute('SELECT local_retirement_json FROM execution_sessions '
            'WHERE session_id=?', (held.request.scope.session_id,)).fetchone()[0] is not None
    fresh = admit(setup, binding, 'preauth-capacity-fresh', 'runtime.start', new_session=True)
    wait_receipt(setup, fresh)


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
