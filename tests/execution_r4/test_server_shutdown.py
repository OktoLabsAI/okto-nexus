"""Administrative shutdown retains HTTP recovery and the same local owners."""
import threading
import time
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import httpx
import uvicorn
import okto_nexus

from test_embedded_dispatch import (
    local_setup, connected_local, qualified_contract, admit, wait_receipt,
)


def test_shutdown_contains_native_open_finishing_after_deadline(connected_local, monkeypatch):
    setup, binding, factory = connected_local
    deps, app, client, headers, *_ = setup
    entered, release = threading.Event(), threading.Event()
    original_open = factory.open

    async def held_open(*args, **kwargs):
        entered.set()
        await asyncio.to_thread(release.wait)
        return await original_open(*args, **kwargs)

    monkeypatch.setattr(factory, "open", held_open)
    admitted = admit(setup, binding, "shutdown-late-open", "runtime.start", new_session=True)
    try:
        assert entered.wait(5)
        response = client.post("/v1/runtime/shutdown", headers=headers["operator"],
            json={"timeout_seconds": .1})
        assert response.status_code == 202, response.text
        assert response.json()["state"] == "DRAINING_PENDING"
        assert deps.runtime_admission_fence.closed
        assert not deps.runtime_dispatcher._shutdown_finished.is_set()
        assert client.get("/healthz").status_code == 200
    finally:
        release.set()
        until = time.monotonic() + 15
        while app.state.runtime_shutdown.status()["state"] != "DRAINED":
            assert time.monotonic() < until, app.state.runtime_shutdown.status()
            time.sleep(.02)
    assert factory.opens == 1 and factory.native.stopped
    assert not app.state.embedded_dispatch_owner.host._runtime_tasks
    assert deps.runtime_dispatcher._shutdown_finished.is_set()
    history = client.get("/v1/runtime/operations/" + admitted["operation_id"],
        headers=headers["subject"])
    assert history.status_code == 200


def test_operator_shutdown_returns_pending_and_keeps_recovery_available(connected_local, monkeypatch):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    opened = admit(setup, binding, "server-shutdown-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    owner = app.state.embedded_dispatch_owner
    before = dict(owner.host._runtime_tasks)
    released = threading.Event()
    original_close = native.native.close

    async def held_close():
        if not released.is_set():
            return "unknown"
        return await original_close()

    monkeypatch.setattr(native.native, "close", held_close)
    assert client.post("/v1/runtime/shutdown", headers=headers["subject"],
        json={"timeout_seconds": .1}).status_code == 403
    assert client.get("/v1/runtime/shutdown", headers=headers["subject"]).status_code == 403
    assert not deps.runtime_admission_fence.closed
    assert client.post("/v1/runtime/shutdown", headers=headers["operator"],
        json={"timeout_seconds": -1}).status_code == 400
    assert not deps.runtime_admission_fence.closed

    try:
        started = time.monotonic()
        response = client.post("/v1/runtime/shutdown", headers=headers["operator"],
            json={"timeout_seconds": .1})
        assert time.monotonic() - started < 1
        assert response.status_code == 202, response.text
        report = response.json()
        assert report["state"] == "DRAINING_PENDING"
        assert any(row.get("session_id") == opened["scope"]["session_id"]
                   for row in report["resources"])
        assert deps.runtime_admission_fence.closed
        assert owner.host._runtime_tasks == before
        assert client.get("/healthz").status_code == 200
        status = client.get("/v1/runtime/shutdown", headers=headers["operator"])
        assert status.status_code == 200 and status.headers["cache-control"] == "no-store"
        assert status.json()["state"] == "DRAINING_PENDING"
        again = client.post("/v1/runtime/shutdown", headers=headers["operator"],
            json={"timeout_seconds": 20})
        assert again.json()["deadline_monotonic"] == report["deadline_monotonic"]
        assert client.get("/v1/runtime/operations/" + opened["operation_id"],
            headers=headers["subject"]).status_code == 200
        with deps.connection_factory.unit_of_work(write=False) as uow:
            dispatcher = owner.inventory.dispatcher
            assert dispatcher.repo.owns(uow, owner_id=dispatcher.owner_id,
                epoch=dispatcher.epoch, now=deps.clock.now_iso())
    finally:
        released.set()
        deadline = time.monotonic() + 10
        while app.state.runtime_shutdown.status()["state"] != "DRAINED":
            assert time.monotonic() < deadline, app.state.runtime_shutdown.status()
            time.sleep(.02)
    status = client.get("/v1/runtime/shutdown", headers=headers["operator"]).json()
    assert status["state"] == "DRAINED" and status["resources"] == []
    assert native.native.stopped and native.opens == 1
    assert not owner.host._runtime_tasks
    assert deps.runtime_dispatcher._shutdown_finished.is_set()


def test_shutdown_cli_over_tcp_retains_server_until_recovery(connected_local, monkeypatch):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    opened = admit(setup, binding, "tcp-shutdown-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    release = threading.Event()
    original = native.native.close

    async def held_close():
        return await original() if release.is_set() else "unknown"

    monkeypatch.setattr(native.native, "close", held_close)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    address = f"http://127.0.0.1:{sock.getsockname()[1]}"
    # The fixture owns the real application lifespan. Run the TCP transport
    # on that same loop, so the retained tasks keep their original owner.
    server = uvicorn.Server(uvicorn.Config(app, lifespan="off", log_level="error"))
    app.state.server = server

    async def serve():
        await server.serve(sockets=[sock])

    running = client.portal.start_task_soon(serve)
    env = dict(os.environ)
    env["OKTO_NEXUS_API_KEY"] = headers["operator"]["Authorization"].removeprefix("Bearer ")
    package_root = str(Path(okto_nexus.__file__).resolve().parent.parent)

    def cli(command, *arguments):
        code = "import sys; sys.path.insert(0," + repr(package_root) + "); from okto_nexus.adapters.inbound.cli.main import main; raise SystemExit(main())"
        result = subprocess.run([sys.executable, "-I", "-c", code, "admin", command,
            "--url", address, *arguments], env=env, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    try:
        deadline = time.monotonic() + 5
        while not server.started:
            assert time.monotonic() < deadline
            time.sleep(.01)
        report = cli("shutdown", "--timeout-seconds", "0.1")
        assert report["state"] == "DRAINING_PENDING"
        assert not server.should_exit and not running.done()
        status = cli("shutdown-status")
        assert status["deadline_monotonic"] == report["deadline_monotonic"]
        assert status["state"] == "DRAINING_PENDING"
        with httpx.Client(trust_env=False) as transport:
            assert transport.get(address + "/healthz").status_code == 200
        assert native.opens == 1
    finally:
        release.set()
        async def ensure_shutdown():
            await app.state.runtime_shutdown.request(timeout_seconds=.1)
        client.portal.call(ensure_shutdown)
        try:
            running.result(timeout=10)
        finally:
            server.should_exit = True
            running.result(timeout=5)
            sock.close()
    assert app.state.runtime_shutdown.status()["state"] == "DRAINED"
    assert native.native.stopped and native.opens == 1


def test_shutdown_retry_recovers_inventory_release_and_cancelled_observer(connected_local, monkeypatch):
    _, app, client, *_ = connected_local[0]
    coordinator = app.state.runtime_shutdown
    inventory = app.state.embedded_inventory_owner
    original_close = inventory.close
    restored = threading.Event()

    async def unavailable():
        if not restored.is_set():
            raise OSError("technical inventory release failure")
        await original_close()

    monkeypatch.setattr(inventory, "close", unavailable)

    async def cancel_observer():
        observer = asyncio.create_task(coordinator.request(timeout_seconds=.1))
        await asyncio.sleep(.02)
        observer.cancel()
        try:
            await observer
        except asyncio.CancelledError:
            pass
        assert not coordinator._task.cancelled()

    try:
        client.portal.call(cancel_observer)
        deadline = time.monotonic() + 5
        while "EMBEDDED_SHUTDOWN_RECOVERY_REQUIRED" not in coordinator.status()["error_codes"]:
            assert time.monotonic() < deadline
            time.sleep(.02)
        assert coordinator.status()["state"] == "DRAINING_PENDING"
        assert not coordinator.deps.runtime_dispatcher._shutdown_finished.is_set()
    finally:
        restored.set()
        client.portal.call(coordinator.wait)
    assert coordinator.status()["state"] == "DRAINED"
    assert coordinator.status()["error_codes"] == []


def test_two_runtime_shutdown_reports_stopped_release_and_unknown_separately(connected_local, monkeypatch):
    setup, binding, factory = connected_local
    _, app, client, headers, *_ = setup
    natives = []
    original_open = factory.open
    async def capture(*args, **kwargs):
        native = await original_open(*args, **kwargs)
        natives.append(native)
        return native
    monkeypatch.setattr(factory, "open", capture)
    operations = []
    for index in range(2):
        operation = admit(setup, binding, f"shutdown-facts-{index}", "runtime.start", new_session=True)
        wait_receipt(setup, operation)
        operations.append(operation)
    owner = app.state.embedded_dispatch_owner
    ledger = owner.host._ledger_task.result()
    release = ledger.release_owned_slot
    restore = threading.Event()
    first = operations[0]["scope"]["session_id"]
    second = operations[1]["scope"]["session_id"]
    async def blocked_release(key, session_id):
        if session_id == first:
            await asyncio.to_thread(restore.wait)
        return await release(key, session_id)
    original_close = natives[1].close
    async def unknown_close():
        if not restore.is_set():
            return "unknown"
        return await original_close()
    monkeypatch.setattr(ledger, "release_owned_slot", blocked_release)
    monkeypatch.setattr(natives[1], "close", unknown_close)
    before = dict(owner.host._runtime_tasks)
    try:
        response = client.post("/v1/runtime/shutdown", headers=headers["operator"], json={"timeout_seconds": .1})
        assert response.status_code == 202
        until = time.monotonic() + 3
        while True:
            response = client.get("/v1/runtime/shutdown", headers=headers["operator"])
            rows = {r.get("session_id"): r for r in response.json()["resources"] if r["owner"] == "embedded"}
            if rows[first]["process_state"] == "STOPPED":
                break
            assert time.monotonic() < until
            time.sleep(.01)
        assert rows[first]["core_release_pending"] is True
        assert rows[second]["process_state"] == "UNKNOWN"
        assert all(r["store_retained"] for r in rows.values())
        assert owner.host._runtime_tasks == before
        assert client.get("/healthz").status_code == 200
    finally:
        restore.set()
        until = time.monotonic() + 15
        while app.state.runtime_shutdown.status()["state"] != "DRAINED":
            assert time.monotonic() < until
            time.sleep(.02)
    assert factory.opens == 2 and all(native.stopped for native in natives)
