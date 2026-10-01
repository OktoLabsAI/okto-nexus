"""Normative R4 recovery acceptance with real owners and injected backends."""
import asyncio
import threading
import time

from test_embedded_dispatch import (
    local_setup, connected_local, qualified_contract, admit, wait_receipt,
)


def test_ns14_03(connected_local, monkeypatch):
    setup, binding, factory = connected_local
    deps, app, client, headers, *_ = setup
    owner = app.state.embedded_dispatch_owner
    opening_entered = threading.Event()
    finish_open = threading.Event()
    finish_close = threading.Event()
    finish_release = threading.Event()
    close_entered = threading.Event()
    release_entered = threading.Event()
    force_entered = threading.Event()
    natives, force_calls = {}, []
    store_closures = []
    original_open = factory.open

    async def delayed_open(prepared, session_id, context, **kwargs):
        native = await original_open(prepared, session_id, context, **kwargs)
        natives[session_id] = native
        if len(natives) == 1:
            async def stuck_close():
                close_entered.set()
                await asyncio.to_thread(finish_close.wait)
                native.stopped = True
                await native.queue.put(None)
                return "forced" if force_entered.is_set() else "graceful"
            async def force_stop():
                force_calls.append(session_id)
                force_entered.set()
                native.stopped = True
                await native.queue.put(None)
            native.close = stuck_close
            native.force_stop = force_stop
            opening_entered.set()
            await asyncio.to_thread(finish_open.wait)
        return native

    monkeypatch.setattr(factory, "open", delayed_open)
    try:
        first = admit(setup, binding, "ns14-late-open", "runtime.start", new_session=True)
        assert opening_entered.wait(3)
        second = admit(setup, binding, "ns14-release-pending", "runtime.start", new_session=True)
        wait_receipt(setup, second)
        first_id, second_id = first["scope"]["session_id"], second["scope"]["session_id"]
        assert set(natives) == {first_id, second_id} and factory.opens == 2
        original_tasks = dict(owner.host._runtime_tasks)
        ledger = owner.host._ledger_task.result()
        original_release = ledger.release_owned_slot
        stores = [task.result()[1] for task in original_tasks.values()] + [ledger]
        for store in stores:
            original_aclose = store.aclose
            async def observed_aclose(close=original_aclose):
                store_closures.append((finish_open.is_set(), finish_close.is_set(), finish_release.is_set()))
                await close()
            monkeypatch.setattr(store, "aclose", observed_aclose)

        async def held_release(key, session_id):
            if session_id == second_id:
                release_entered.set()
                await asyncio.to_thread(finish_release.wait)
            return await original_release(key, session_id)

        monkeypatch.setattr(ledger, "release_owned_slot", held_release)
        started = time.monotonic()
        response = client.post("/v1/runtime/shutdown", headers=headers["operator"],
                               json={"timeout_seconds": .1})
        assert response.status_code == 202, response.text
        assert time.monotonic() - started < 1
        report = response.json()
        assert report["state"] == "DRAINING_PENDING" and deps.runtime_admission_fence.closed
        refused = client.post("/v1/runtime/intents:resolve", headers=headers["subject"], json={
            "client_intent_id": "ns14-refused-start", "intent": "runtime.start",
            "binding_id": binding["binding_id"], "workspace_binding_id": binding["workspace_binding_id"],
            "new_session": True})
        assert refused.status_code == 200 and not refused.json()["can_submit"]
        assert "runtime_draining" in refused.json()["blockers"]
        rows = {r.get("session_id"): r for r in report["resources"] if r["owner"] == "embedded"}
        assert set(rows) == {first_id, second_id}
        assert rows[first_id]["process_state"] == "UNKNOWN"
        assert release_entered.wait(3)

        # Let the already-started native opening return after admission closed.
        # Its stuck close must not prevent its independent force, even while
        # the other runtime's shared-ledger release is still blocked.
        finish_open.set()
        assert close_entered.wait(3)
        assert force_entered.wait(3)
        assert not finish_release.is_set() and not finish_close.is_set()
        assert owner.host._runtime_tasks == original_tasks
        assert force_calls == [first_id]
        assert client.get("/healthz").status_code == 200
        again = client.post("/v1/runtime/shutdown", headers=headers["operator"],
                            json={"timeout_seconds": 30}).json()
        assert again["state"] == "DRAINING_PENDING"
        assert again["deadline_monotonic"] == report["deadline_monotonic"]
        rows = {r.get("session_id"): r for r in again["resources"] if r["owner"] == "embedded"}
        assert set(rows) == {first_id, second_id}
        assert rows[second_id]["process_state"] == "STOPPED"
        assert rows[second_id]["core_release_pending"] is True
        assert all(row["store_retained"] for row in rows.values())
        assert store_closures == []
        assert client.get("/v1/runtime/operations/" + second["operation_id"],
                          headers=headers["subject"]).status_code == 200
        with deps.connection_factory.unit_of_work(write=False) as uow:
            dispatcher = owner.inventory.dispatcher
            assert dispatcher.repo.owns(uow, owner_id=dispatcher.owner_id,
                epoch=dispatcher.epoch, now=deps.clock.now_iso())
    finally:
        finish_open.set()
        finish_close.set()
        finish_release.set()
        async def drain():
            await app.state.runtime_shutdown.request(timeout_seconds=.1)
            await asyncio.wait_for(app.state.runtime_shutdown.wait(), 15)
        client.portal.call(drain)
    assert app.state.runtime_shutdown.status()["state"] == "DRAINED"
    assert owner.host._runtime_tasks == {}
    assert factory.opens == 2 and all(native.stopped for native in natives.values())
    assert force_calls == [first_id]
    assert deps.runtime_dispatcher._shutdown_finished.is_set()
    assert len(store_closures) >= 3
    assert all(states == (True, True, True) for states in store_closures)
