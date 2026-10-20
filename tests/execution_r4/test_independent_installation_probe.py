"""Version checks retain selected evidence without blocking sibling discovery."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import threading
from types import SimpleNamespace

from okto_nexus.application import execution_local_observations as observations
from okto_nexus.bootstrap import embedded_inventory
from test_local_realization import local_setup
from test_local_installation_check import checking, rows
from test_independent_embedded_inventory import eventually


def test_selected_probe_survives_sibling_publication_and_does_not_wait_for_slow_pi(checking, monkeypatch):
    deps, app, client, headers, body, route, source, calls = checking
    owner = app.state.embedded_inventory_owner
    pi_entered, pi_release = threading.Event(), threading.Event()
    probe_entered, probe_release = threading.Event(), threading.Event()
    sibling_failed = threading.Event()

    def discover(*, adapter_ids, **_):
        adapter = adapter_ids[0]
        if adapter == 'pi_rpc':
            pi_entered.set()
            assert pi_release.wait(30)
        if adapter == 'claude_stream' and sibling_failed.is_set():
            raise OSError('synthetic sibling discovery failure')
        return SimpleNamespace(candidates=(source,) if adapter == source.adapter_id else ())

    async def probe(selected):
        calls.append(selected)
        probe_entered.set()
        assert await asyncio.to_thread(probe_release.wait, 20)
        return replace(selected, version='0.159.0')

    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', discover)
    monkeypatch.setattr(observations, 'probe_version', probe)

    async def hold_pi():
        return asyncio.create_task(owner.refresh(('pi_rpc',)))

    held = client.portal.call(hold_pi)
    with ThreadPoolExecutor(max_workers=1) as requests:
        response = None
        try:
            assert pi_entered.wait(5)
            response = requests.submit(client.post, route, json=body, headers=headers['operator'])
            assert probe_entered.wait(5)
            sibling_failed.set()
            client.portal.call(owner.refresh, ('claude_stream',))
            assert owner.published_batch.coverage()['claude_stream']['state'] == 'FAILED'
            assert not response.done()
            probe_release.set()
            reply = response.result(timeout=10)
            assert reply.status_code == 200, reply.text
            assert reply.json()['publication_pending'] is False
            assert len(rows(deps)) == len(calls) == 1
            assert not pi_release.is_set() and not held.done()
        finally:
            probe_release.set()
            pi_release.set()
            if response is not None:
                response.result(timeout=10)
            client.portal.call(eventually, held.done)
