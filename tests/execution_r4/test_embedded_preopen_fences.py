"""Interrupted local openings recover through a durable Core admission fence."""
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from nexus_connector_core import CoreError, LocalRuntimeCore

from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_embedded_inventory import app_for


@pytest.mark.parametrize('adapter,cut', [
    ('pi_rpc', None), ('codex_app_server', None), ('claude_stream', None),
    ('codex_app_server', 'prepare'), ('codex_app_server', 'core'), ('codex_app_server', 'commit'),
    ('codex_app_server', 'tools'), ('codex_app_server', 'checkpoint'),
])
def test_bound_open_without_core_admission_recovers_and_new_work_runs(tmp_path, monkeypatch, adapter, cut):
    from okto_nexus.bootstrap import embedded_preopen_recovery as recovery
    with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, SimpleNamespace(param=adapter)) as setup:
        setup, binding, native = connected_local.__wrapped__(setup)
        deps, app, client, headers, *_ = setup
        async def interrupted(*args, **kwargs):
            raise CoreError('SESSION_CONFLICT', 'open')
        with monkeypatch.context() as patch:
            patch.setattr(LocalRuntimeCore, 'open', interrupted)
            opened = admit(setup, binding, 'interrupted-open', 'runtime.start', new_session=True, text='Never sent')
            until = time.monotonic() + 10
            while not app.state.embedded_dispatch_owner.sessions.get(opened['session_id'], {}).get('recovering'):
                assert time.monotonic() < until
                time.sleep(.02)
        assert native.opens == 0
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT count(*) FROM execution_local_publications').fetchone()[0] == 1
            assert uow.connection.execute('SELECT count(*) FROM execution_receipts').fetchone()[0] == 0

    cuts = []
    if cut in ('prepare', 'commit', 'checkpoint'):
        name = '_' + cut
        original = getattr(recovery.EmbeddedPreopenRecovery, name)
        def interrupted_commit(*args):
            result = original(*args)
            if not cuts:
                cuts.append(cut)
                raise OSError('Synthetic lost reply after durable recovery boundary')
            return result
        monkeypatch.setattr(recovery.EmbeddedPreopenRecovery, name, interrupted_commit)
    elif cut == 'core':
        original = recovery.persist_r4_preopen_refusal
        async def interrupted_core(*args):
            result = await original(*args)
            if not cuts:
                cuts.append(cut)
                raise OSError('Synthetic lost reply after Core admission fence')
            return result
        monkeypatch.setattr(recovery, 'persist_r4_preopen_refusal', interrupted_core)
    elif cut == 'tools':
        from okto_nexus.bootstrap.embedded_tools import EmbeddedToolsOwner
        original = EmbeddedToolsOwner.release_session
        async def interrupted_tools(self, session_id):
            if session_id == opened['session_id'] and not cuts:
                with self.owner.factory.unit_of_work(write=False) as uow:
                    assert uow.connection.execute('SELECT local_retirement_json FROM execution_sessions '
                        'WHERE session_id=?', (session_id,)).fetchone()[0] is None
                cuts.append(cut)
                raise OSError('Synthetic cleanup failure before retirement')
            return await original(self, session_id)
        monkeypatch.setattr(EmbeddedToolsOwner, 'release_session', interrupted_tools)
    for boot in range(2):
        deps, app = app_for(tmp_path / 'home')
        with TestClient(app) as client:
            owner = app.state.embedded_dispatch_owner
            until = time.monotonic() + 20
            while 'subject' in owner.agents.blocked:
                assert time.monotonic() < until, owner.agents.errors
                time.sleep(.05)
            assert native.opens == boot
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT count(*) FROM execution_preopen_refusals').fetchone()[0] == 1
                assert tuple(uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions WHERE session_id=?',
                    (opened['session_id'],)).fetchone()) == ('CLOSED', 'CLOSED')
                assert tuple(uow.connection.execute('SELECT stage,possible_effect,retry_safe,error_code FROM execution_receipts WHERE operation_id=?',
                    (opened['operation_id'],)).fetchone()) == ('FAILED', 0, 1, 'PRE_EXECUTION_FENCED')
                assert uow.connection.execute('SELECT admission_state FROM execution_operations WHERE parent_operation_id=?',
                    (opened['operation_id'],)).fetchone()[0] == 'RESOLVED_TERMINAL'
            owner.native_factory = native
            current = (deps, app, client, headers, *setup[4:])
            fresh = admit(current, binding, 'after-recovery-' + str(boot), 'runtime.start', new_session=True, text='New request')
            wait_receipt(current, fresh)
            with deps.connection_factory.unit_of_work(write=False) as uow:
                child = dict(uow.connection.execute('SELECT operation_id FROM execution_operations WHERE parent_operation_id=?',
                    (fresh['operation_id'],)).fetchone())
            wait_receipt(current, child)
            assert native.opens == boot + 1
            assert [verb for verb, _ in native.native.sent] == ['send_turn']
            wait_receipt(current, admit(current, binding, 'close-' + str(boot), 'runtime.close', session_id=fresh['session_id']), stages=('SUCCEEDED',))
    assert bool(cuts) == bool(cut)


@pytest.mark.parametrize('adapter', ['pi_rpc', 'codex_app_server', 'claude_stream'])
def test_durable_refusal_before_slot_reservation_recovers(tmp_path, monkeypatch, adapter):
    from nexus_connector_core import Operation
    from nexus_connector_core.models import EffectNotSent
    with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, SimpleNamespace(param=adapter)) as setup:
        setup, binding, native = connected_local.__wrapped__(setup)
        deps, app, client, headers, *_ = setup
        async def refuse_before_reserving(runtime, operation, context):
            prepared = operation.prepared
            semantic = Operation(operation.operation_id, operation.session_id, 'runtime.open', dict(
                adapter_id=prepared.intent.adapter_id, profile_fingerprint=prepared.profile_fingerprint,
                root_fingerprint=prepared.root_fingerprint, stream_epoch=operation.stream_epoch))
            async def refuse():
                raise EffectNotSent('Shutdown before native reservation', code='RUNTIME_DRAINING')
            return await runtime._kernel.execute(semantic, context, refuse)
        with monkeypatch.context() as patch:
            patch.setattr(LocalRuntimeCore, 'open', refuse_before_reserving)
            rejected = admit(setup, binding, 'refused-without-slot', 'runtime.start', new_session=True)
            wait_receipt(setup, rejected, stages=('FAILED',))
            until = time.monotonic() + 15
            while rejected['session_id'] in app.state.embedded_dispatch_owner.sessions:
                assert time.monotonic() < until, app.state.embedded_dispatch_owner.agents.errors
                time.sleep(.02)
        assert native.opens == 0
        assert not app.state.embedded_dispatch_owner.agents.blocked
    deps, app = app_for(tmp_path / 'home')
    with TestClient(app) as client:
        owner = app.state.embedded_dispatch_owner
        until = time.monotonic() + 15
        while owner.agents.blocked:
            assert time.monotonic() < until, owner.agents.errors
            time.sleep(.05)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert tuple(uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions WHERE session_id=?',
                (rejected['session_id'],)).fetchone()) == ('FAILED', 'CLOSED')
            assert uow.connection.execute('SELECT count(*) FROM execution_local_preopen_fences').fetchone()[0] == 0
        owner.native_factory = native
        current = (deps, app, client, headers, *setup[4:])
        fresh = admit(current, binding, 'after-safe-refusal', 'runtime.start', new_session=True)
        wait_receipt(current, fresh)
        assert native.opens == 1
        wait_receipt(current, admit(current, binding, 'close-after-safe-refusal', 'runtime.close',
            session_id=fresh['session_id']), stages=('SUCCEEDED',))
