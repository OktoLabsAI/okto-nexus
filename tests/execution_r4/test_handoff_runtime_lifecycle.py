"""Serve-owned automatic work and retained shutdown, with synthetic native peers."""
import asyncio
from contextlib import contextmanager, nullcontext
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from okto_nexus.application.handoff_runtime_scheduler import HandoffRuntimeScheduler
from okto_nexus.application.handoff_runtime_service import HandoffRuntimeService
from okto_nexus.bootstrap.handoff_runtime_scheduler import build_handoff_runtime_candidates
from okto_nexus.bootstrap.handoff_runtime_attempts import build_handoff_runtime_attempts
from okto_nexus.config import load_config
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, assert_unclaimed
from test_handoff_automation_principal import prepare
from test_handoff_runtime_candidates import enable_capacity, lease
from test_canonical_result_publication import current_turn
from test_runtime_policy_defaults import save
from test_embedded_inventory import app_for


@pytest.fixture(autouse=True)
def rollout(monkeypatch, request):
    import test_embedded_inventory
    original = test_embedded_inventory.build_app
    enabled = getattr(request, 'param', True)
    def build(deps):
        deps.config.runtime_handoff_auto_claim_enabled = enabled
        return original(deps)
    monkeypatch.setattr(test_embedded_inventory, 'build_app', build)
    return enabled


def eventually(predicate, timeout=20):
    until = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < until, 'Serve-owned handoff work did not settle'
        time.sleep(.02)


def state(deps, hid):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return uow.connection.execute('SELECT status,claimed_by,claim_epoch FROM handoffs WHERE handoff_id=?',
                                      (hid,)).fetchone()


def test_rollout_defaults_enabled_with_explicit_startup_opt_out(tmp_path):
    assert load_config({}, ['--home', str(tmp_path)]).runtime_handoff_auto_claim_enabled
    assert not load_config({'OKTO_NEXUS_RUNTIME_HANDOFF_AUTO_CLAIM_ENABLED': 'false'},
                          ['--home', str(tmp_path)]).runtime_handoff_auto_claim_enabled
    assert load_config({'OKTO_NEXUS_RUNTIME_HANDOFF_AUTO_CLAIM_ENABLED': 'true'},
                       ['--home', str(tmp_path)]).runtime_handoff_auto_claim_enabled
    assert not load_config({'OKTO_NEXUS_RUNTIME_HANDOFF_AUTO_CLAIM_ENABLED': 'true'},
        ['--home', str(tmp_path), '--runtime-handoff-auto-claim-enabled', 'false']).runtime_handoff_auto_claim_enabled
    from okto_nexus.config import FEATURE_FLAG_FIELDS
    assert 'runtime_handoff_auto_claim_enabled' not in FEATURE_FLAG_FIELDS


@pytest.mark.parametrize('rollout', [False, True], indirect=True)
def test_serve_requires_rollout_and_agent_opt_in_then_claims_without_manual_ticks(runtime, rollout):
    setup, _, native = runtime
    deps, app, _, *_ = setup
    from test_runtime_policy_defaults import read
    for agent in (None, 'subject'):
        policy = read(setup, agent)
        assert policy['handoff_auto_claim_rollout_enabled'] is rollout
        saved = save(setup, agent=agent).json()['data']
        assert saved == policy  # Idempotent saves expose the same startup gate.
    _, hid, gid = prepare(runtime, enable=False)
    service = app.state.handoff_runtime_service
    if not rollout:
        assert service is None and not app.state.embedded_core_host.capacity_enabled
        assert save(setup, agent='subject', broadcast_handoff_auto_claim=True).status_code == 200
        assert_unclaimed(runtime, hid, gid)
        assert native.opens == 0
        return
    assert service is not None and app.state.embedded_core_host.capacity_enabled
    def checked():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute('SELECT reason FROM handoff_runtime_schedule WHERE handoff_id=?', (hid,)).fetchone()
            return row is not None and row[0] == 'NOT_AUTHORIZED'
    eventually(checked)
    assert_unclaimed(runtime, hid, gid)
    assert native.opens == 0
    assert save(setup, agent='subject', broadcast_handoff_auto_claim=True).status_code == 200
    eventually(lambda: state(deps, hid)[0] == 'CLAIMED')
    wait_receipt(setup, current_turn(setup))
    assert native.opens == len(native.native.sent) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?',
                                      (gid,)).fetchone()[0] == 1
        assert uow.connection.execute('SELECT count(*) FROM runtime_handoff_bindings WHERE handoff_id=?',
                                      (hid,)).fetchone()[0] == 1


def test_slow_scheduler_does_not_delay_native_stop_or_release_store_early(runtime, monkeypatch):
    setup, _, native = runtime
    deps, app, client, headers, *_ = setup
    _, hid, _ = prepare(runtime)
    eventually(lambda: state(deps, hid)[0] == 'CLAIMED')
    wait_receipt(setup, current_turn(setup))
    service = app.state.handoff_runtime_service
    entered, release = threading.Event(), threading.Event()
    original = service.scheduler._reserve_page
    def held(*args):
        entered.set()
        assert release.wait(20)
        return original(*args)
    monkeypatch.setattr(service.scheduler, '_reserve_page', held)
    try:
        assert entered.wait(5)
        response = client.post('/v1/runtime/shutdown', headers=headers['operator'], json={'timeout_seconds': .1})
        assert response.status_code == 202, response.text
        assert any(r['owner'] == 'handoff-runtime' for r in response.json()['resources'])
        eventually(lambda: native.native.stopped)
        assert not service.drained and not deps.runtime_dispatcher._shutdown_finished.is_set()
        assert client.get('/healthz').status_code == 200
    finally:
        release.set()
        eventually(lambda: app.state.runtime_shutdown.status()['state'] == 'DRAINED')
    assert service.drained and deps.runtime_dispatcher._shutdown_finished.is_set()
    assert native.opens == 1


@pytest.mark.asyncio
async def test_cancelled_service_close_retains_planner_and_prevents_restart():
    entered, release = threading.Event(), threading.Event()
    scheduler = HandoffRuntimeScheduler(factory=SimpleNamespace(unit_of_work=lambda: nullcontext(None)),
        repository=None, processor=None)
    calls = []
    def plan(*args):
        calls.append(args)
        entered.set()
        assert release.wait(10)
        return ()
    scheduler._reserve_page = plan
    service = HandoffRuntimeService(scheduler, interval=.01)
    service.start()
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        task = service._task
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(service.aclose(), .01)
        assert not service.drained and service._task is task and not task.cancelled()
        with pytest.raises(RuntimeError):
            service.start()
        assert len(calls) == 1
    finally:
        release.set()
        await service.aclose()
    assert service.drained and scheduler.pending_count == 0 and len(calls) == 1


def test_partial_startup_after_scheduler_creation_drains_actual_owner(tmp_path, monkeypatch):
    from okto_nexus.bootstrap import server_shutdown
    deps, app = app_for(tmp_path / 'partial-startup')
    def fail(*args, **kwargs):
        raise RuntimeError('Injected failure after scheduler start')
    monkeypatch.setattr(server_shutdown, 'ServerShutdownCoordinator', fail)
    with pytest.raises(RuntimeError, match='Injected failure'):
        with TestClient(app):
            pass
    assert app.state.handoff_runtime_service.drained
    assert app.state.handoff_notice_maintenance.drained
    assert deps.runtime_dispatcher._shutdown_finished.is_set()


def test_reset_drains_scheduler_and_new_owner_can_claim_again(runtime):
    setup, _, native = runtime
    deps, app, client, headers, *_ = setup
    _, hid, _ = prepare(runtime)
    eventually(lambda: state(deps, hid)[0] == 'CLAIMED')
    wait_receipt(setup, current_turn(setup))
    previous, old_native = app.state.handoff_runtime_service, native.native
    response = client.post('/api/v1/admin/reset?keep_agents=true', headers=headers['operator'])
    assert response.status_code in (200, 202), response.text
    def reset_finished():
        result = client.get('/api/v1/admin/reset', headers=headers['operator'])
        assert result.status_code in (200, 202), result.text
        return not result.json()['data'].get('pending')
    eventually(reset_finished, timeout=30)
    assert previous.drained and old_native.stopped
    assert app.state.handoff_runtime_service is not previous
    assert not app.state.handoff_runtime_service.drained
    assert not deps.runtime_admission_fence.closed
    _, next_hid, _ = prepare(runtime)
    eventually(lambda: state(deps, next_hid)[0] == 'CLAIMED')
    wait_receipt(setup, current_turn(setup))
    assert native.opens == 2
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM handoff_runtime_attempts').fetchone()[0] == 1
        assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('rollout', [False], indirect=True)
def test_restart_with_rollout_disabled_recovers_original_hold_without_new_acquisition(tmp_path, monkeypatch):
    with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, None) as initial:
        connected = connected_local.__wrapped__(initial)
        run = runtime.__wrapped__(connected, monkeypatch)
        _, hid, gid = prepare(run)
        enable_capacity(run)
        deps, app, client, *_ = initial
        discovery = build_handoff_runtime_candidates(deps)
        identity = discovery.prepare_page(lease(run, hid), limit=4).attempt_ids[0]
        attempts = build_handoff_runtime_attempts(deps)
        assert client.portal.call(attempts.reserve, identity).state == 'RESERVED'
        assert_unclaimed(run, hid, gid)
        home, native = deps.config.home_dir, connected[2]
    assert native.opens == 0
    restored, app = app_for(home)
    with TestClient(app):
        assert app.state.handoff_runtime_service is not None
        attempts = build_handoff_runtime_attempts(restored)
        eventually(lambda: not attempts.get(identity).active)
        assert attempts.get(identity).state == 'CANCELLED_NO_EFFECT'
        def cleanup_round_finished():
            with restored.connection_factory.unit_of_work(write=False) as uow:
                return uow.connection.execute('SELECT state FROM handoff_runtime_schedule WHERE handoff_id=?',
                                              (hid,)).fetchone()[0] == 'IDLE'
        eventually(cleanup_round_finished)
        assert tuple(state(restored, hid)) == ('OPEN', None, 0)
        with restored.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT count(*) FROM handoff_runtime_attempts').fetchone()[0] == 1
            assert uow.connection.execute('SELECT count(*) FROM execution_operations').fetchone()[0] == 0
    assert app.state.handoff_runtime_service.drained
