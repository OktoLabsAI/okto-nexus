"""Conversion never races native dispatch or outlives its serve/store owner."""
import asyncio
from contextlib import contextmanager, nullcontext
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_agent_recovery_isolation import eventually
from test_handoff_notice_retirement import backlog, create_notice, mark_old_broadcast
from test_embedded_inventory import app_for
from okto_nexus.application.handoff_notice_maintenance import HandoffNoticeMaintenance
from okto_nexus.bootstrap.handoff_runtime_scheduler import build_handoff_notice_retirement


@pytest.mark.asyncio
async def test_cancelled_close_observer_retains_one_writer_until_it_returns():
    entered, release = threading.Event(), threading.Event()
    calls = []
    class Notices:
        def retire_page(self, uow, **kw):
            calls.append(kw)
            entered.set()
            assert release.wait(10)
    owner = HandoffNoticeMaintenance(factory=SimpleNamespace(unit_of_work=lambda: nullcontext(None)),
        notices=Notices(), interval=.01)
    owner.start()
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        retained = owner._task
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(owner.aclose(), .01)
        assert not owner.drained and owner._task is retained and not retained.cancelled()
        with pytest.raises(RuntimeError):
            owner.start()
        assert len(calls) == 1
    finally:
        release.set()
        await owner.aclose()
    assert owner.drained and len(calls) == 1


@pytest.mark.asyncio
async def test_failed_conversion_rolls_back_and_retries_original_cursor(backlog):
    real = build_handoff_notice_retirement()
    attempts = []
    class Notices:
        def retire_page(self, uow, **kw):
            result = real.retire_page(uow, **kw)
            attempts.append(result)
            if len(attempts) == 1:
                raise RuntimeError('Injected writer failure after retirement')
            return result
    owner = HandoffNoticeMaintenance(factory=backlog, notices=Notices(), interval=.01)
    owner.start()
    try:
        async with asyncio.timeout(5):
            while len(attempts) < 2:
                await asyncio.sleep(.01)
    finally:
        await owner.aclose()
    assert attempts[:2] == [1, 1] and owner.last_error is None
    with backlog.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM runtime_handoff_notice_retirements').fetchone()[0] == 1


def test_startup_converts_backlog_even_with_runtime_admission_disabled(backlog):
    deps, app = app_for(backlog.config.home_dir)
    deps.config.feature_harness_integrations = False
    with TestClient(app):
        def retired():
            with deps.connection_factory.unit_of_work(write=False) as uow:
                return uow.connection.execute('SELECT count(*) FROM runtime_handoff_notice_retirements').fetchone()[0] == 1
        eventually(retired)
        owner = app.state.handoff_notice_maintenance
        assert not owner.drained
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT status FROM delivery_outbox WHERE operation_id='b-safe'").fetchone()[0] == 'CANCELLED'
            assert not uow.connection.execute('SELECT * FROM execution_operations').fetchall()
    assert owner.drained


def test_partial_startup_failure_drains_notice_writer_without_coordinator(tmp_path, monkeypatch):
    from okto_nexus.adapters.inbound.mcp.tools import harness
    deps, app = app_for(tmp_path / 'partial-startup')
    deps.config.feature_harness_integrations = True
    def fail_boot(*args):
        raise RuntimeError('Injected boot failure before coordinator creation')
    monkeypatch.setattr(harness, 'run_runtime_boot', fail_boot)
    with pytest.raises(RuntimeError, match='Injected boot failure'):
        with TestClient(app):
            pass
    assert app.state.handoff_notice_maintenance.drained
    assert deps.runtime_dispatcher._shutdown_finished.is_set()


def test_conversion_wait_does_not_hold_native_containment_or_release_store(connected_local, monkeypatch):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    opened = admit(setup, binding, 'notice-shutdown-order', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    owner = app.state.handoff_notice_maintenance
    entered, release = threading.Event(), threading.Event()
    page = owner._page
    def held_page():
        entered.set()
        assert release.wait(15)
        return page()
    monkeypatch.setattr(owner, '_page', held_page)
    try:
        assert entered.wait(5)
        result = client.post('/v1/runtime/shutdown', headers=headers['operator'], json={'timeout_seconds': .1})
        assert result.status_code == 202 and result.json()['state'] == 'DRAINING_PENDING'
        assert any(r['owner'] == 'handoff-notices' for r in result.json()['resources'])
        eventually(lambda: native.native.stopped)
        assert not owner.drained and not deps.runtime_dispatcher._shutdown_finished.is_set()
        assert client.get('/healthz').status_code == 200
    finally:
        release.set()
        eventually(lambda: app.state.runtime_shutdown.status()['state'] == 'DRAINED')
    assert owner.drained and deps.runtime_dispatcher._shutdown_finished.is_set()


def test_pending_legacy_turn_cannot_dispatch_while_conversion_is_delayed(connected_local, monkeypatch):
    from okto_nexus.application import execution_initial_turns
    setup, binding, native = connected_local
    deps, app, client, *_ = setup
    enable(setup, binding)
    release_turns = execution_initial_turns.release_ready_initial_turns
    monkeypatch.setattr(execution_initial_turns, 'release_ready_initial_turns', lambda *a, **k: None)
    # Stop only migration's observer; the real dispatch lane remains running.
    owner = app.state.handoff_notice_maintenance
    client.portal.call(owner.aclose)
    handoff_id = create_notice(setup, monkeypatch)
    def ready():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return uow.connection.execute("SELECT count(*) FROM execution_sessions WHERE lifecycle_state='READY'").fetchone()[0] == 1
    eventually(ready)
    with deps.connection_factory.unit_of_work() as uow:
        mark_old_broadcast(uow, handoff_id)
        release_turns(uow.connection, server_id=binding['server_id'], executor_id=binding['executor_id'])
    monkeypatch.setattr(execution_initial_turns, 'release_ready_initial_turns', release_turns)
    old_native = native.native
    # A separate session can still pass the live sender, proving it is not
    # merely paused and providing a completion barrier after the old notice.
    fresh = admit(setup, binding, 'healthy-during-conversion', 'runtime.start', new_session=True)
    wait_receipt(setup, fresh)
    with deps.connection_factory.unit_of_work() as uow:
        assert uow.connection.execute("SELECT dispatch_state FROM execution_dispatch_outbox x JOIN execution_operations p "
            "USING(server_id,executor_id,operation_id) WHERE p.action='turn.submit'").fetchone()[0] == 'PENDING'
        assert build_handoff_notice_retirement().retire_page(uow, now=10, limit=32) == 1
    assert not old_native.sent and not native.native.sent and native.opens == 2


def test_restart_retires_old_initial_notice_without_replaying_native_work(tmp_path, monkeypatch):
    from okto_nexus.application import execution_initial_turns
    release_turns = execution_initial_turns.release_ready_initial_turns
    monkeypatch.setattr(execution_initial_turns, 'release_ready_initial_turns', lambda *a, **k: None)
    with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, None) as initial:
        setup, binding, native = connected_local.__wrapped__(initial)
        deps, app, client, *_ = setup
        enable(setup, binding)
        client.portal.call(app.state.handoff_notice_maintenance.aclose)
        handoff_id = create_notice(setup, monkeypatch)
        def ready():
            with deps.connection_factory.unit_of_work(write=False) as uow:
                return uow.connection.execute("SELECT count(*) FROM execution_sessions WHERE lifecycle_state='READY'").fetchone()[0] == 1
        eventually(ready)
        with deps.connection_factory.unit_of_work() as uow:
            mark_old_broadcast(uow, handoff_id)
        home = deps.config.home_dir
    assert native.opens == 1 and not native.native.sent and native.native.stopped
    monkeypatch.setattr(execution_initial_turns, 'release_ready_initial_turns', release_turns)
    for _ in range(2):
        deps, app = app_for(home)
        deps.config.feature_harness_integrations = False
        with TestClient(app):
            def retired():
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    return uow.connection.execute('SELECT count(*) FROM runtime_handoff_notice_retirements').fetchone()[0] == 1
            eventually(retired)
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT status,claimed_by FROM handoffs WHERE handoff_id=?', (handoff_id,)).fetchone()[:] == ('OPEN', None)
                assert uow.connection.execute('SELECT status,consumer_kind,read_at FROM message_deliveries').fetchone()[:] == ('unread', None, None)
                assert not uow.connection.execute('SELECT * FROM runtime_results').fetchall()
        assert app.state.handoff_notice_maintenance.drained
    assert native.opens == 1 and not native.native.sent
