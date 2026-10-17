"""Reset completion observes preserved selections without a global scan barrier."""
import threading
import time

import pytest

from test_canonical_delivery import connected_local, enable, send
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_harness_canonical import qualified_bridge


@pytest.mark.parametrize('held_adapter', ['codex_app_server', 'pi_rpc'])
def test_reset_waits_only_for_preserved_selected_harness(connected_local, monkeypatch, held_adapter):
    from okto_nexus.bootstrap.embedded_inventory import EmbeddedInventoryOwner
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    previous = app.state.embedded_inventory_owner
    original = EmbeddedInventoryOwner._observe
    entered, release = threading.Event(), threading.Event()
    async def observe(owner, adapter_id, cancel_requested):
        if owner is not previous and adapter_id == held_adapter:
            entered.set()
            # A retained blocking observer models a slow native/filesystem read.
            import asyncio
            await asyncio.to_thread(release.wait)
        return await original(owner, adapter_id, cancel_requested)
    monkeypatch.setattr(EmbeddedInventoryOwner, '_observe', observe)
    try:
        response = client.post('/api/v1/admin/reset?keep_agents=true', headers=headers['operator'])
        assert response.status_code in (200, 202), response.text
        assert entered.wait(15)
        response = client.get('/api/v1/admin/reset', headers=headers['operator'])
        assert client.get('/healthz').status_code == 200
        assert not deps.runtime_admission_fence.closed
        if held_adapter == 'codex_app_server':
            assert response.json()['data']['pending'] and response.json()['data']['phase'] == 'reconnecting'
            release.set()
        deadline = time.monotonic() + 30
        while response.json()['data'].get('pending') and time.monotonic() < deadline:
            time.sleep(.05)
            response = client.get('/api/v1/admin/reset', headers=headers['operator'])
        assert response.status_code == 200 and not response.json()['data'].get('pending'), response.text
        enable(setup, binding)
        delivered = send(setup, monkeypatch)
        assert delivered['ok'], delivered
        with deps.connection_factory.unit_of_work(write=False) as uow:
            turn = dict(uow.connection.execute("SELECT operation_id FROM execution_operations WHERE action='turn.submit'").fetchone())
        wait_receipt(setup, turn)
        assert native.opens == 1
        if held_adapter == 'pi_rpc':
            assert not release.is_set()  # Successful delivery while unused discovery remains held.
    finally:
        release.set()
