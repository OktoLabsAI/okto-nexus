"""Normative R4 recovery acceptance with real owners and injected backends."""
import asyncio
import threading
import time
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timezone

import pytest
import httpx
import okto_nexus
from nexus_connector_core import CoreError, SessionKey, TurnOperation

from test_embedded_dispatch import (
    local_setup, connected_local, qualified_contract, admit, wait_receipt,
)


def test_ns14_01(tmp_path):
    helper = Path(__file__).with_name("ns14_restart_process.py")
    package_root = str(Path(okto_nexus.__file__).resolve().parent.parent)
    env = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
    env.update(PATH=str(Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32"),
               HOME=str(tmp_path), USERPROFILE=str(tmp_path), PYTHONIOENCODING="utf-8", OKTO_NEXUS_NO_BANNER="1")
    command = [sys.executable, "-I", str(helper), package_root, str(tmp_path)]
    produced = subprocess.run(command + ["produce"], cwd=tmp_path, env=env,
                              capture_output=True, text=True, timeout=30)
    assert produced.returncode == 0, produced.stderr
    record = json.loads((tmp_path / "restart-record.json").read_text(encoding="utf-8"))
    Path(record["binary"]).unlink()
    # Respect the crashed owner's real durable lease; never clear or rewrite it.
    expiry = datetime.fromisoformat(record["owner_expiry"].replace("Z", "+00:00"))
    remaining = (expiry - datetime.now(timezone.utc)).total_seconds()
    assert remaining <= 45
    if remaining > 0:
        time.sleep(remaining + .1)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log_path = tmp_path / "restarted-server.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command + ["serve", "--home", record["home"],
            "--host", "127.0.0.1", "--port", str(port), "--feature-harness-integrations", "true",
            "--embedding-mode", "off", "--harness-root", str(tmp_path)],
            cwd=tmp_path, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            until = time.monotonic() + 20
            probe_path = tmp_path / "restart-probe.json"
            while not probe_path.exists():
                assert process.poll() is None, log_path.read_text(encoding="utf-8")
                assert time.monotonic() < until, log_path.read_text(encoding="utf-8")
                time.sleep(.02)
            facts = json.loads(probe_path.read_text(encoding="utf-8"))
            opened = record["opened"]
            sid = opened["scope"]["session_id"]
            assert facts["pid"] != record["pid"]
            assert facts["operation_id"] == opened["operation_id"] and facts["stage"] == "SUBMITTED"
            assert facts["claim_ids"] == facts["reservations"] == [sid]
            assert facts["slot_released"] is False and facts["runtimes"] == 0
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=5,
                              headers=record["headers"]["subject"]) as client:
                intent = client.get("/v1/runtime/intents/" + opened["client_intent_id"])
                operation = client.get("/v1/runtime/operations/" + opened["operation_id"])
                session = client.get("/v1/runtime/sessions/" + sid)
                assert intent.status_code == operation.status_code == session.status_code == 200
                assert operation.json()["executor_stage"] == record["view"]["executor_stage"]
                assert session.json()["ownership"] == session.json()["process_state"] == "UNKNOWN"
                assert not session.json()["control_available"]
                replay = client.post("/v1/runtime/operations", json={k:opened[k] for k in
                    ("client_intent_id", "operation_id", "resolution_revision", "intent_hash")})
                assert replay.status_code == 200 and replay.json()["operation_id"] == opened["operation_id"]
                refused = client.post("/v1/runtime/intents:resolve", json={
                    "client_intent_id": "ns14-after-restart", "intent": "runtime.start",
                    "binding_id": record["binding"]["binding_id"],
                    "workspace_binding_id": record["binding"]["workspace_binding_id"], "new_session": True})
                assert refused.status_code == 200 and not refused.json()["can_submit"]
                assert not (tmp_path / "unexpected-runtime").exists()
                response = client.post("/v1/runtime/shutdown", headers=record["headers"]["operator"],
                                       json={"timeout_seconds": 1})
                assert response.status_code in {200, 202}
            assert process.wait(timeout=15) == 0
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)


@pytest.mark.parametrize("fault", ["newer_generation", "rollback", "unknown", "revoke_ack_lost"])
def test_ns14_02(connected_local, monkeypatch, fault):
    setup, binding, native = connected_local
    _, app, client, *_ = setup
    opened = admit(setup, binding, "ns14-authority-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    owner = app.state.embedded_dispatch_owner
    sid = opened["scope"]["session_id"]
    executor = owner.sessions[sid]["executor"]

    async def scenario():
        runtime, journal = owner.host._runtime_tasks[(opened["scope"]["executor_id"], sid)].result()
        base = executor.context
        key = SessionKey(base.server_id, base.executor_id, sid)
        original_cas, original_read = journal.cas_session_lease, journal.get_session_lease
        readable = fault == "newer_generation"
        writes = []
        async def unavailable_read(*args, **kwargs):
            if not readable:
                raise CoreError("STORAGE_UNAVAILABLE", "test_lease_read")
            return await original_read(*args, **kwargs)
        async def ambiguous_write(*args, **kwargs):
            writes.append(dict(kwargs))
            if fault == "revoke_ack_lost":
                await original_cas(*args, **kwargs)
            raise CoreError("STORAGE_UNAVAILABLE", "test_lease_confirmation", possible_effect=True)
        if fault == "newer_generation":
            await original_cas(key, expected_connection_generation=base.connection_generation,
                connection_generation=base.connection_generation + 2,
                owner_generation=base.session_owner_generation,
                authorization_revision=base.authorization_revision,
                configuration_revision=base.configuration_revision, revoked=False)
        else:
            monkeypatch.setattr(journal, "cas_session_lease", ambiguous_write)
            monkeypatch.setattr(journal, "get_session_lease", unavailable_read)
        try:
            with pytest.raises(CoreError) as failure:
                if fault == "revoke_ack_lost":
                    await executor.revoke_r4(authorization_revision=base.authorization_revision + 1)
                else:
                    await runtime.renew_lease(key, replace(base,
                        connection_generation=base.connection_generation + 1,
                        lease_deadline_monotonic=base.lease_deadline_monotonic + .001),
                        expected_connection_generation=base.connection_generation)
            assert failure.value.stage in {"test_lease_confirmation", "lease_cas"}, (failure.value.code, failure.value.stage)
            for index in range(3):
                with pytest.raises(CoreError):
                    await runtime.submit(TurnOperation(f"old-context-{index}", sid, "Must not reach native"), base)
                await asyncio.sleep(.05)
            assert native.native.sent == [] and native.opens == 1
            snapshot = await runtime.inspect(key)
            assert snapshot.session_id == sid
            if fault == "unknown":
                # A concluded producer and elapsed time do not prove rollback.
                assert len(writes) == 1
                return
            readable = True
            if fault == "rollback":
                async with asyncio.timeout(3):
                    while True:
                        try:
                            receipt = await runtime.submit(TurnOperation("rollback-recovered", sid, "Allowed after proof"), base)
                            break
                        except CoreError:
                            await asyncio.sleep(.02)
                assert receipt.stage == "SUBMITTED" and len(native.native.sent) == 1
            elif fault == "revoke_ack_lost":
                async with asyncio.timeout(3):
                    while True:
                        try:
                            applied = await executor.revoke_r4(authorization_revision=base.authorization_revision + 1)
                            break
                        except CoreError as error:
                            if error.code not in {"REVOKE_BUSY", "LEASE_UPDATE_PENDING"}:
                                raise
                            await asyncio.sleep(.02)
                assert applied.acknowledgement["application_stage"] == "REVOKED"
                assert len(writes) == 1, "Lost confirmation must not repeat the durable revoke"
                assert (await original_read(key)).revoked
            if fault != "rollback":
                with pytest.raises(CoreError):
                    await runtime.submit(TurnOperation("old-after-recovery", sid, "Still forbidden"), base)
                assert native.native.sent == []
        finally:
            readable = True
            monkeypatch.setattr(journal, "cas_session_lease", original_cas)
            monkeypatch.setattr(journal, "get_session_lease", original_read)
    client.portal.call(scenario)


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
