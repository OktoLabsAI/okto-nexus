"""Operator drain is observation until quiescence or an explicit decision."""
import asyncio
from io import BytesIO
import json
import time
import threading
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from okto_nexus.application.runtime_admission_fence import RuntimeAdmissionFence
from okto_nexus.bootstrap.server_shutdown import ServerShutdownCoordinator
from okto_nexus.errors import OktoNexusError

pytest_plugins = ['test_service_readiness']


class DrainHost:
    def __init__(self):
        self._runtime_tasks = {}
        self.quiescent = False
        self.draining = False
        self.shutdown_calls = 0

    def begin_drain(self):
        self.draining = True

    async def drain_status(self):
        return {"quiescent": self.quiescent, "resources": [] if self.quiescent else [
            {"session_id": "synthetic-session", "outcome": "unknown", "reason": "ACTIVE_TURN"}]}

    async def shutdown(self, _policy, *, close_stores=True):
        if not close_stores:
            self.shutdown_calls += 1


def coordinator():
    host = DrainHost()
    deps = SimpleNamespace(runtime_admission_fence=RuntimeAdmissionFence())
    owner = ServerShutdownCoordinator(deps, embedded=None, inventory=None, host=host)
    return owner, host, deps


@pytest.mark.asyncio
async def test_timeout_does_not_start_shutdown_or_reopen_admission():
    owner, host, deps = coordinator()
    report = await owner.request(timeout_seconds=.01)
    assert report["state"] == "DRAINING_PENDING"
    assert host.shutdown_calls == 0
    assert host.draining and deps.runtime_admission_fence.closed
    task, deadline = owner._task, owner.deadline
    await owner.request(timeout_seconds=30)
    assert owner._task is task and owner.deadline == deadline
    assert host.shutdown_calls == 0
    host.quiescent = True
    await asyncio.wait_for(owner.wait(), 1)
    assert host.shutdown_calls == 1 and owner.status()["state"] == "DRAINED"


@pytest.mark.asyncio
async def test_force_requires_an_existing_expired_drain():
    owner, host, deps = coordinator()
    with pytest.raises(OktoNexusError):
        await owner.request(timeout_seconds=0, force=True)
    assert not deps.runtime_admission_fence.closed and host.shutdown_calls == 0
    observer = asyncio.create_task(owner.request(timeout_seconds=1))
    await asyncio.sleep(0)
    with pytest.raises(OktoNexusError):
        await owner.request(timeout_seconds=0, force=True)
    host.quiescent = True
    await observer
    await owner.wait()


@pytest.mark.asyncio
async def test_force_is_one_retained_decision_not_a_new_shutdown():
    owner, host, _ = coordinator()
    await owner.request(timeout_seconds=0)
    task = owner._task
    await owner.request(timeout_seconds=0, force=True)
    await owner.request(timeout_seconds=0, force=True)
    await asyncio.wait_for(owner.wait(), 1)
    assert owner._task is task and host.shutdown_calls == 1
    assert owner.status()["force_requested"] is True


@pytest.mark.asyncio
async def test_cancelled_observer_keeps_drain_owned_and_control_available():
    owner, host, _ = coordinator()
    observer = asyncio.create_task(owner.request(timeout_seconds=1))
    await asyncio.sleep(0)
    observer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await observer
    assert owner._task is not None and not owner._task.cancelled()
    assert host.shutdown_calls == 0
    host.quiescent = True
    await asyncio.wait_for(owner.wait(), 1)


@pytest.mark.asyncio
async def test_safety_shutdown_escalates_same_owner_without_operator_force():
    owner, host, _ = coordinator()
    await owner.request(timeout_seconds=0)
    task = owner._task
    await owner.request_safety_shutdown(timeout_seconds=0)
    await asyncio.wait_for(owner.wait(), 1)
    assert owner._task is task and host.shutdown_calls == 1
    assert owner.status()["force_requested"] is False
    assert owner.status()["safety_shutdown"] is True


@pytest.mark.asyncio
async def test_supervisor_latch_failure_prevents_even_explicit_force():
    owner, host, _ = coordinator()
    async def unavailable():
        raise OSError('synthetic supervisor unavailable')
    owner.persist_stop = unavailable
    await owner.request(timeout_seconds=0)
    await owner.request(timeout_seconds=0, force=True)
    await asyncio.sleep(.03)
    assert host.shutdown_calls == 0
    assert 'DRAIN_OBSERVATION_UNAVAILABLE' in owner.status()['error_codes']
    owner.persist_stop = None
    # Restore the same selected latch; no new stop intent or native producer.
    async def restored():
        pass
    owner.persist_stop = restored
    await asyncio.wait_for(owner.wait(), 1)
    assert host.shutdown_calls == 1


def test_service_force_checks_authority_generation_and_prior_drain(running_service, monkeypatch):
    client, app, lock, deps = running_service
    host = app.state.embedded_core_host
    async def active():
        return {'quiescent': False, 'resources': [{'owner': 'synthetic-peer', 'outcome': 'pending'}]}
    monkeypatch.setattr(host, 'drain_status', active)
    view = client.get('/api/v1/service').json()['data']
    body = {key: view[key] for key in ('instance_id', 'generation')}
    body.update(timeout_seconds=0.0, force=True)
    assert client.post('/api/v1/service/stop', json=body).status_code == 409
    assert not deps.runtime_admission_fence.closed
    assert client.post('/api/v1/service/stop', json={**body, 'force': 1}).status_code == 422
    client.post('/api/v1/service/stop', json={**body, 'force': False})
    task = app.state.runtime_shutdown._task
    participant = client.post('/api/v1/agents', json={'agent_id': 'drain-reader'}).json()['data']['api_key']
    assert client.post('/api/v1/service/stop', json=body,
        headers={'Authorization': 'Bearer ' + participant}).status_code == 403
    assert client.post('/api/v1/service/stop', json={**body, 'generation': 'previous'}).status_code == 409
    assert not app.state.runtime_shutdown.status()['force_requested']
    assert client.get('/healthz').status_code == 200 and lock.owned
    response = client.post('/api/v1/service/stop', json=body)
    assert response.status_code in {200, 202}
    assert response.json()['data']['shutdown']['force_requested'] is True
    until = time.monotonic() + 3
    while app.state.runtime_shutdown.status()['state'] != 'DRAINED':
        assert time.monotonic() < until
        time.sleep(.01)
    assert app.state.runtime_shutdown._task is task
    assert deps.runtime_admission_fence.closed


@pytest.mark.parametrize('arguments', [
    ['stop', '--force'], ['restart', '--force', '--expected-generation', 'g'],
    ['stop', '--expected-generation', 'g'],
])
def test_force_cli_requires_explicit_stop_and_generation(arguments, monkeypatch):
    from okto_nexus.adapters.inbound.cli.service import run_service
    resolve = Mock(side_effect=AssertionError('Invalid force must not resolve or mutate service state'))
    monkeypatch.setattr('okto_nexus.adapters.inbound.cli.service.resolve_local_service', resolve)
    with pytest.raises(SystemExit) as error:
        run_service(arguments)
    assert error.value.code == 2
    resolve.assert_not_called()


def test_cli_orchestration_refuses_changed_generation_before_sending_force():
    from okto_nexus.application.service_lifecycle import ServiceLifecycle
    adapter = Mock()
    adapter.inspect.return_value = {'state': 'ready', 'generation': 'replacement'}
    service = ServiceLifecycle(adapter, monotonic=time.monotonic, sleep=time.sleep)
    report = service.stop(force=True, expected_generation='reviewed', timeout=.01)
    assert report['reason'] == 'INSTANCE_CHANGED'
    adapter.request_stop.assert_not_called()


@pytest.mark.asyncio
async def test_missing_core_drain_contract_remains_unknown(tmp_path):
    from okto_nexus.bootstrap.runtime_host import EmbeddedRuntimeHost
    host = EmbeddedRuntimeHost(tmp_path)
    async def old_runtime():
        return SimpleNamespace(), SimpleNamespace()
    task = asyncio.create_task(old_runtime())
    await task
    host._runtime_tasks[('executor', 'session')] = task
    host.begin_drain()
    report = await host.drain_status()
    assert report['quiescent'] is False
    assert any(row['reason'] == 'DRAIN_PROTOCOL_UNAVAILABLE' for row in report['resources'])


@pytest.mark.asyncio
async def test_authorized_reset_waits_for_unknown_resource_without_service_stop_latch(monkeypatch):
    from okto_nexus.bootstrap import database_reset, server_runtime
    owner, host, deps = coordinator()
    deps.runtime_dispatcher = None
    persist = Mock(side_effect=AssertionError('Runtime reset must not request a service stop'))
    owner.persist_stop = persist
    host._runtime_tasks[('executor', 'session')] = object()
    release = asyncio.Event()
    entered = asyncio.Event()
    async def uncertain_shutdown(_policy, **_kwargs):
        entered.set()
        if release.is_set():
            host._runtime_tasks.clear()
    host.shutdown = uncertain_shutdown
    async def no_remote(*_args):
        pass
    async def restart_runtime(_app, **_kwargs):
        assert not host._runtime_tasks
    monkeypatch.setattr(database_reset, '_close_remote_sessions', no_remote)
    monkeypatch.setattr(server_runtime, 'start_runtime_services', restart_runtime)
    app = SimpleNamespace(state=SimpleNamespace(deps=deps, runtime_shutdown=owner, auth=Mock()))
    erase = Mock(return_value=({'synthetic': 1}, False))
    task = asyncio.create_task(database_reset._run(app, keep_agents=False, reset=erase, context=None))
    await asyncio.wait_for(entered.wait(), 1)
    assert deps.runtime_admission_fence.closed
    erase.assert_not_called()
    persist.assert_not_called()
    release.set()
    result = await asyncio.wait_for(task, 2)
    assert result['pending'] is False
    erase.assert_called_once()
    assert not deps.runtime_admission_fence.closed


@pytest.mark.parametrize('valid_refusal', [True, False])
def test_local_force_preserves_explicit_refusal_without_echoing_peer_text(tmp_path, monkeypatch, valid_refusal):
    from test_service_start import make_adapter
    adapter = make_adapter(tmp_path)
    current = {'state': 'stopping', 'instance_id': 'selected-instance', 'generation': 'selected-generation'}
    monkeypatch.setattr(adapter, '_inspect_process', lambda **_kwargs: current)
    body = (json.dumps({'error': {'code': 'CONFLICT', 'message': 'private-peer-text',
        'details': {'reason': 'DRAIN_DECISION_NOT_AVAILABLE'}}}).encode()
        if valid_refusal else b'<html>private-peer-text</html>')
    opener = Mock()
    opener.open.side_effect = HTTPError('http://private-peer-url', 409, 'private-peer-reason', {}, BytesIO(body))
    monkeypatch.setattr('okto_nexus.adapters.outbound.service_manager.local.build_opener', lambda *_args: opener)
    result = adapter.request_stop(current, timeout=.01, force=True)
    assert 'private-peer' not in json.dumps(result)
    if valid_refusal:
        assert result['state'] == 'failed' and result['reason'] == 'DRAIN_DECISION_NOT_AVAILABLE'
        assert 'submitted' not in result['next_action']
    else:
        assert result['shutdown']['state'] == 'UNCONFIRMED'


@pytest.mark.asyncio
async def test_force_contains_while_sql_observer_is_blocked_but_retains_owner_until_join():
    owner, host, _ = coordinator()
    host.quiescent = True
    entered, release = threading.Event(), threading.Event()
    reads = []
    def blocked(_scopes):
        reads.append('one')
        entered.set()
        assert release.wait(5)
        return []
    owner._canonical_pending = blocked
    drained = Mock()
    owner.on_drained = drained
    await owner.request(timeout_seconds=.01)
    assert await asyncio.to_thread(entered.wait, 1)
    await owner.request(timeout_seconds=0, force=True)
    try:
        until = time.monotonic() + 1
        while host.shutdown_calls == 0:
            assert time.monotonic() < until
            await asyncio.sleep(.01)
        assert owner.status()['state'] == 'DRAINING_PENDING'
        assert any(row['owner'] == 'drain-observer' for row in owner.status()['resources'])
        assert reads == ['one']
        drained.assert_not_called()
    finally:
        release.set()
    await asyncio.wait_for(owner.wait(), 1)
    assert owner.status()['state'] == 'DRAINED'
    drained.assert_called_once()


@pytest.mark.parametrize('force', [False, True])
def test_normal_stop_keeps_old_wire_shape_while_force_is_explicit(tmp_path, monkeypatch, force):
    from test_service_start import make_adapter
    adapter = make_adapter(tmp_path)
    current = {'state': 'stopping', 'instance_id': 'selected-instance', 'generation': 'selected-generation'}
    monkeypatch.setattr(adapter, '_inspect_process', lambda **_kwargs: current)
    class Reply:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def read(self, _limit):
            return json.dumps({'ok': True, 'data': {**current,
                'shutdown': {'state': 'DRAINING_PENDING'}}}).encode()
    opener = Mock()
    opener.open.return_value = Reply()
    monkeypatch.setattr('okto_nexus.adapters.outbound.service_manager.local.build_opener', lambda *_args: opener)
    adapter.request_stop(current, timeout=.01, force=force)
    body = json.loads(opener.open.call_args.args[0].data)
    expected = {'instance_id': current['instance_id'], 'generation': current['generation'], 'timeout_seconds': .01}
    if force:
        expected['force'] = True
    assert body == expected


@pytest.mark.asyncio
async def test_core_revision_change_during_sql_read_invalidates_quiescent_proof():
    owner, host, _ = coordinator()
    host.quiescent = True
    revision = ['first']
    release, second = threading.Event(), threading.Event()
    async def status():
        return {'quiescent': True, 'resources': [], 'activity_revision': revision[0]}
    host.drain_status = status
    host.drain_revision = lambda: revision[0]
    reads = []
    def read(_scopes):
        reads.append('read')
        if len(reads) == 1:
            revision[0] = 'changed'
        else:
            second.set()
            assert release.wait(3)
        return []
    owner._canonical_pending = read
    try:
        await owner.request(timeout_seconds=.01)
        assert await asyncio.to_thread(second.wait, 1)
        assert host.shutdown_calls == 0
        assert owner.status()['state'] == 'DRAINING_PENDING'
    finally:
        release.set()
    await asyncio.wait_for(owner.wait(), 1)
    assert host.shutdown_calls == 1
