"""Independent producers through the real Server lifecycle and HTTP boundary."""
import asyncio
import threading
from collections import Counter
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from okto_nexus.bootstrap import embedded_inventory
from test_embedded_inventory import app_for, agent_key, request_refresh
from test_embedded_dispatch import local_setup, connected_local, connect_local, admit, wait_receipt


async def eventually(predicate):
    async with asyncio.timeout(10):
        while not predicate():
            await asyncio.sleep(.01)


def test_initial_slow_harness_does_not_block_sibling_publication_or_http(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    attempts = Counter()

    def discover(*, adapter_ids, **_):
        assert len(adapter_ids) == 1
        adapter = adapter_ids[0]
        attempts[adapter] += 1
        if adapter == 'pi_rpc':
            entered.set()
            assert release.wait(20)
        return SimpleNamespace(candidates=())

    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', discover)
    deps, app = app_for(tmp_path / 'home')
    headers = {'Authorization': 'Bearer ' + agent_key(deps, app)}
    with TestClient(app) as client:
        owner = app.state.embedded_inventory_owner
        try:
            assert entered.wait(5)
            client.portal.call(eventually, lambda: owner.published_batch is not None and
                owner.published_batch.coverage()['codex_app_server']['state'] == 'ABSENT')
            route = f'/v1/runtime/executors/{owner.key.executor_id}/inventory'
            view = client.get(route, headers=headers).json()
            assert view['adapter_freshness']['pi_rpc'] == 'STALE'
            assert view['adapter_freshness']['codex_app_server'] == 'FRESH'
            coverage = {row['adapter_id']: row['state'] for row in view['snapshot']['observations']}
            assert coverage['pi_rpc'] == 'PENDING'
            assert coverage['codex_app_server'] == 'ABSENT'
            assert client.get('/healthz').status_code == 200
            before = attempts['codex_app_server']
            client.portal.call(owner.refresh, ('codex_app_server',))
            assert attempts['codex_app_server'] > before and attempts['pi_rpc'] == 1
            assert not release.is_set()
        finally:
            release.set()
            client.portal.call(eventually, lambda: owner.published_batch is not None and
                all(row.state == 'ABSENT' for row in owner.published_batch.observations))


def test_held_refresh_keeps_sibling_execution_and_does_not_ack_early(connected_local, monkeypatch):
    setup, binding, native = connected_local
    deps, app, client, headers, _, candidate, _ = setup
    agent_key(deps, app)
    owner = app.state.embedded_inventory_owner
    entered, release = threading.Event(), threading.Event()
    attempts = Counter()

    def discover(*, adapter_ids, **_):
        adapter = adapter_ids[0]
        attempts[adapter] += 1
        if adapter == 'pi_rpc':
            entered.set()
            assert release.wait(30)
        return SimpleNamespace(candidates=(candidate,) if adapter == candidate.adapter_id else ())

    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', discover)
    request_refresh(deps, owner, 'held-pi')

    async def start_refresh():
        return asyncio.create_task(owner.refresh())

    task = client.portal.call(start_refresh)
    try:
        assert entered.wait(5)
        before = owner.publication.publication_sequence
        client.portal.call(owner.refresh, (candidate.adapter_id,))
        assert owner.publication.publication_sequence > before
        assert request_refresh(deps, owner, 'held-pi')['state'] == 'REQUESTED'
        assert not task.done() and not release.is_set()
        opened = admit(setup, binding, 'independent-open', 'runtime.start', new_session=True)
        wait_receipt(setup, opened)
        assert native.opens == 1
        sent = admit(setup, binding, 'independent-turn', 'turn.submit',
            session_id=opened['scope']['session_id'], text='Independent observation test')
        wait_receipt(setup, sent)
        assert not release.is_set()
    finally:
        release.set()
        client.portal.call(eventually, task.done)
        task.result()
    assert request_refresh(deps, owner, 'held-pi')['state'] == 'UPDATED'


def test_failed_harness_is_visible_and_retries_without_removing_siblings(tmp_path, monkeypatch):
    failing = threading.Event()
    failing.set()
    def discover(*, adapter_ids, **_):
        if adapter_ids == ('pi_rpc',) and failing.is_set():
            raise OSError('private provider path must not enter public inventory')
        return SimpleNamespace(candidates=())
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', discover)
    deps, app = app_for(tmp_path / 'home')
    headers = {'Authorization': 'Bearer ' + agent_key(deps, app)}
    with TestClient(app) as client:
        owner = app.state.embedded_inventory_owner
        client.portal.call(eventually, lambda: owner.published_batch is not None and
            owner.published_batch.coverage()['pi_rpc']['state'] == 'FAILED' and
            owner.published_batch.coverage()['codex_app_server']['state'] == 'ABSENT')
        assert owner.failure is None
        view = client.get(f'/v1/runtime/executors/{owner.key.executor_id}/inventory', headers=headers)
        assert 'private provider path' not in view.text
        assert view.json()['adapter_freshness']['codex_app_server'] == 'FRESH'
        assert view.json()['adapter_freshness']['pi_rpc'] == 'STALE'
        failing.clear()
        client.portal.call(eventually, lambda: owner.published_batch.coverage()['pi_rpc']['state'] == 'ABSENT')
