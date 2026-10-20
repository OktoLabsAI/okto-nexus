"""HTTP readiness is independent of a retained initial inventory observation."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from okto_nexus.bootstrap import embedded_inventory
from okto_nexus.errors import OktoNexusError
from test_embedded_inventory import app_for, agent_key, wait_inventory


@pytest.mark.parametrize('previous_snapshot', [False, True])
def test_http_serves_during_initial_discovery_without_fresh_inventory(tmp_path, monkeypatch, previous_snapshot):
    from okto_nexus.adapters.inbound.mcp.tools import harness
    entered, release, serving, finish = (threading.Event() for _ in range(4))

    if previous_snapshot:
        monkeypatch.setattr(embedded_inventory, 'discover_local_candidates',
                            lambda **_: SimpleNamespace(candidates=()))
        _, prior = app_for(tmp_path / 'home')
        with TestClient(prior) as client:
            wait_inventory(client)

    booted = []
    monkeypatch.setattr(harness, 'run_runtime_boot', lambda deps, **kwargs: booted.append(True))

    def discover(**_):
        entered.set()
        assert release.wait(15)
        return SimpleNamespace(candidates=())

    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', discover)
    deps, app = app_for(tmp_path / 'home')
    headers = {'Authorization': 'Bearer ' + agent_key(deps, app)}

    def serve():
        with TestClient(app) as client:
            owner = app.state.embedded_inventory_owner
            assert client.get('/healthz').status_code == 200
            assert client.get('/').status_code == 200
            route = f'/v1/runtime/executors/{owner.key.executor_id}/inventory'
            view = client.get(route, headers=headers)
            if previous_snapshot:
                assert view.status_code == 200, view.text
                assert view.json()['freshness'] == 'STALE'
                assert view.json()['eligible_for_new_start'] is False
            else:
                assert view.status_code == 404, view.text
            assert owner.generation is not None
            assert app.state.embedded_dispatch_owner.channel.connection_generation == owner.generation
            assert owner.publication is None and not owner.fresh
            assert not booted
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_sessions').fetchone()[0] == 0
            serving.set()
            assert finish.wait(15)
            wait_inventory(client)
            client.portal.call(app.state.runtime_boot_owner.wait)
            assert booted  # Partial publication can wake more than one bounded boot pass.
            assert client.get(route, headers=headers).json()['freshness'] == 'FRESH'

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(serve)
        try:
            assert entered.wait(10)
            if not serving.wait(5):
                if future.done():
                    future.result()
                pytest.fail('HTTP startup waited for the blocked inventory scan')
            assert not release.is_set()
        finally:
            release.set()
            finish.set()
        future.result(timeout=15)
    assert not app.state.inventory_fresh_publications


def test_shutdown_retains_approved_boot_worker_and_reports_it(tmp_path, monkeypatch):
    from okto_nexus.adapters.inbound.mcp.tools import harness
    entered, release = threading.Event(), threading.Event()
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates',
                        lambda **_: SimpleNamespace(candidates=()))

    def boot(deps, **kwargs):
        entered.set()
        assert release.wait(15)
        assert not deps.runtime_dispatcher._shutdown_finished.is_set()
        return []

    monkeypatch.setattr(harness, 'run_runtime_boot', boot)
    deps, app = app_for(tmp_path / 'home')
    with TestClient(app) as client:
        try:
            assert entered.wait(5)

            async def scenario():
                coordinator = app.state.runtime_shutdown
                report = await coordinator.request(timeout_seconds=.01)
                assert report['state'] == 'DRAINING_PENDING'
                assert any(r['owner'] == 'runtime-boot' for r in report['resources'])
                observing = asyncio.create_task(app.state.runtime_boot_owner.aclose())
                await asyncio.sleep(0)
                observing.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await observing
                assert not app.state.runtime_boot_owner.drained
                assert not deps.runtime_dispatcher._shutdown_finished.is_set()

            client.portal.call(scenario)
            assert client.get('/healthz').status_code == 200
        finally:
            release.set()
            client.portal.call(app.state.runtime_shutdown.wait)
        assert app.state.runtime_shutdown.status()['state'] == 'DRAINED'
        assert app.state.runtime_boot_owner.drained


def test_shutdown_before_inventory_is_ready_does_not_boot(tmp_path, monkeypatch):
    from okto_nexus.adapters.inbound.mcp.tools import harness
    entered, release = threading.Event(), threading.Event()
    calls = []

    def discover(**_):
        entered.set()
        assert release.wait(15)
        return SimpleNamespace(candidates=())

    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', discover)
    monkeypatch.setattr(harness, 'run_runtime_boot', lambda deps, **kwargs: calls.append(True))
    _, app = app_for(tmp_path / 'home')
    with TestClient(app) as client:
        try:
            assert entered.wait(5)
            async def request():
                return await app.state.runtime_shutdown.request(timeout_seconds=.01)
            assert client.portal.call(request)['state'] == 'DRAINING_PENDING'
        finally:
            release.set()
            client.portal.call(app.state.runtime_shutdown.wait)
        assert app.state.runtime_boot_owner.drained and not calls


def test_initial_discovery_failure_retries_without_restart_or_manual_refresh(tmp_path, monkeypatch):
    retried, release = threading.Event(), threading.Event()
    calls = []

    def discover(*, adapter_ids, **_):
        calls.append(adapter_ids[0])
        if adapter_ids == ('pi_rpc',) and calls.count('pi_rpc') == 1:
            raise OSError('initial discovery unavailable')
        if adapter_ids == ('pi_rpc',):
            retried.set()
            assert release.wait(15)
        return SimpleNamespace(candidates=())

    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', discover)
    original_init = embedded_inventory.EmbeddedInventoryOwner.__init__

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs, refresh_seconds=.02)

    monkeypatch.setattr(embedded_inventory.EmbeddedInventoryOwner, '__init__', init)
    _, app = app_for(tmp_path / 'home')
    with TestClient(app) as client:
        owner = app.state.embedded_inventory_owner
        try:
            assert client.get('/healthz').status_code == 200
            assert retried.wait(5)
            assert owner.failure is None
            assert owner.published_batch.coverage()['pi_rpc']['state'] == 'FAILED'
        finally:
            release.set()

        async def recovered():
            async with asyncio.timeout(5):
                while owner.published_batch.coverage()['pi_rpc']['state'] != 'ABSENT':
                    await asyncio.sleep(.01)
            assert owner.failure is None
            assert (owner.key.server_id, owner.key.executor_id) in owner.fresh

        client.portal.call(recovered)
        assert calls.count('pi_rpc') >= 2


def test_shutdown_retains_initial_scan_after_cancelled_observer(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def discover(**_):
        entered.set()
        assert release.wait(15)
        return SimpleNamespace(candidates=())

    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', discover)
    _, app = app_for(tmp_path / 'home')
    with TestClient(app) as client:
        owner = app.state.embedded_inventory_owner

        async def scenario():
            assert await asyncio.to_thread(entered.wait, 5)
            closing = asyncio.create_task(owner.close())
            try:
                async with asyncio.timeout(5):
                    while not owner._stop.is_set():
                        await asyncio.sleep(0)
                closing.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await closing
                assert any(not task.done() for task in owner._observer._tasks.values())
                assert not owner._close_task.done()
                assert owner.publication is None and not owner.fresh
            finally:
                release.set()
                await asyncio.wait_for(owner.close(), 5)
            assert all(task.done() for task in owner._observer._tasks.values()) and owner._task.done()
            assert owner.publication is None and not owner.fresh

        client.portal.call(scenario)


@pytest.mark.parametrize('change', ['generation=generation+1', "owner_instance_id='successor'", "revoked_at='2026-10-16T00:00:00Z'"])
def test_initial_scan_cannot_publish_after_authority_changes(tmp_path, monkeypatch, change):
    entered, release = threading.Event(), threading.Event()

    def discover(**_):
        entered.set()
        assert release.wait(15)
        return SimpleNamespace(candidates=())

    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', discover)
    deps, app = app_for(tmp_path / 'home')
    with TestClient(app) as client:
        owner = app.state.embedded_inventory_owner
        try:
            assert entered.wait(5)
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute('UPDATE execution_executors SET ' + change + " WHERE kind='embedded'")
            release.set()

            async def rejected():
                async with asyncio.timeout(5):
                    while owner.failure is None:
                        await asyncio.sleep(.01)
                assert isinstance(owner.failure, OktoNexusError)

            client.portal.call(rejected)
            assert owner.publication is None and not owner.fresh
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_inventory_snapshots').fetchone()[0] == 0
        finally:
            release.set()
