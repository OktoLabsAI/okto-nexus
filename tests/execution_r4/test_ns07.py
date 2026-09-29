"""Embedded Core owner composition smoke for NS07.01."""

import asyncio
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from nexus_connector_core import (
    CoreError, ExecutionContext, InstallationCandidate, Operation,
    OperationKey, ShutdownPolicy, intent_hash,
)
from nexus_connector_core.discovery import fingerprint

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.bootstrap.runtime_host import EmbeddedRuntimeHost
from okto_nexus.adapters.outbound.execution.embedded import (
    EmbeddedExecutor, core_error_projection,
)


def _candidate():
    return InstallationCandidate(
        adapter_id="codex", executable="C:/tools/codex.exe",
        fingerprint="selected-local-build", source="explicit", trust="trusted",
    )


def test_ns07_01(tmp_path, monkeypatch):
    async def scenario():
        store = tmp_path / "core"
        host = EmbeddedRuntimeHost(store, max_owned_slots=1)
        assert not store.exists()

        entered = asyncio.Event()
        release = asyncio.Event()
        original = host._open_ledger
        calls = 0

        async def delayed_ledger():
            nonlocal calls
            calls += 1
            entered.set()
            await release.wait()
            return await original()

        monkeypatch.setattr(host, "_open_ledger", delayed_ledger)

        async def environment(_launch):
            return {}

        options = dict(executor_id="exe_one", session_id="session_one",
                       candidates={"codex": _candidate()},
                       workspace_roots={"workspace": str(tmp_path)},
                       environment=environment)
        first = asyncio.create_task(host.acquire(**options))
        second = asyncio.create_task(host.acquire(**options))
        await asyncio.wait_for(entered.wait(), 5)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        runtime = await asyncio.wait_for(second, 10)
        assert await host.acquire(**options) is runtime
        assert calls == 1
        await host.acquire(**{**options, "executor_id": "exe_two",
                              "session_id": "session_two"})
        other_session = await host.acquire(**{
            **options, "session_id": "session_three",
            "workspace_roots": {"workspace": str(tmp_path / "other")}})
        assert other_session is not runtime
        assert calls == 1
        ledger = await host._ledger()
        first_key = OperationKey("server", "exe_one", "operation_one")
        second_key = OperationKey("server", "exe_two", "operation_two")
        await ledger.reserve_owned_slot(first_key, "session_one")
        with pytest.raises(CoreError) as full:
            await ledger.reserve_owned_slot(second_key, "session_two")
        assert full.value.code == "CAPACITY_EXCEEDED"
        assert await ledger.release_owned_slot(first_key, "session_one")
        assert len(list(store.glob("session-*.db"))) == 3
        assert (store / "owned-slots.db").exists()
        with pytest.raises(RuntimeError, match="changed"):
            await host.acquire(**{**options,
                "workspace_roots": {"workspace": str(tmp_path / "other")}})
        report = await host.shutdown(ShutdownPolicy(0, 0))
        assert report[("exe_one", "session_one")].session_outcomes == {}
        assert report[("exe_two", "session_two")].session_outcomes == {}
        assert report[("exe_one", "session_three")].session_outcomes == {}
        with pytest.raises(RuntimeError, match="shutting down"):
            await host.acquire(**options)

    asyncio.run(scenario())


def test_passive_serve_does_not_open_core_stores(tmp_path):
    home = tmp_path / "home"
    deps = bootstrap({}, ["--home", str(home)])
    app = build_app(deps)
    with TestClient(app) as client:
        assert client.get("/v1/connections/protocol").status_code == 200
        assert isinstance(app.state.embedded_core_host, EmbeddedRuntimeHost)
        assert not (home / "core-runtime").exists()
    assert not (home / "core-runtime").exists()


def test_ns07_02(tmp_path):
    class Native:
        native_id = "native-one"
        active_turn_id = "turn-from-native"

        def __init__(self):
            self.sent = []
            self.queue = asyncio.Queue()
            self.stopped = False

        async def send(self, verb, payload, operation_id, *, expected_turn_id=None):
            if verb == "steer":
                assert expected_turn_id == self.active_turn_id
            self.sent.append((verb, operation_id, expected_turn_id))

        async def events(self):
            while True:
                event = await self.queue.get()
                if event is None:
                    return
                yield event

        async def close(self):
            self.stopped = True
            await self.queue.put(None)
            return "graceful"

        async def observe(self):
            return ("STOPPED" if self.stopped else "RUNNING", "IDLE")

    class Factory:
        def __init__(self):
            self.native = Native()
            self.opens = 0

        async def open(self, prepared, session_id, context, *, stream_epoch):
            self.opens += 1
            assert session_id == "session_one"
            assert context.binding_id == "binding"
            return self.native

    async def scenario():
        binary = tmp_path / "codex.exe"
        binary.write_bytes(b"synthetic local candidate")
        candidate = InstallationCandidate(
            "codex_app_server", str(binary), fingerprint(binary),
            "explicit", "selected")
        factory = Factory()
        host = EmbeddedRuntimeHost(tmp_path / "core")

        async def environment(_launch):
            return {}

        context = ExecutionContext(
            "server", "executor", "binding", "agent", "workspace",
            1, 1, 1, time.monotonic() + 60,
            frozenset({"runtime.open", "turn.submit", "turn.steer",
                       "turn.interrupt", "runtime.close"}),
        )
        executor = EmbeddedExecutor(
            host, context=context, session_id="session_one",
            candidate=candidate, workspace_root=str(tmp_path),
            environment=environment, native_factory=factory,
        )
        try:
            opened = await executor.open(operation_id="open_one",
                                         stream_epoch="stream_one")
            assert opened.operation_id == "open_one" and factory.opens == 1
            submitted = await executor.submit(operation_id="submit_one",
                                              text="Hello")
            assert submitted.operation_id == "submit_one"
            steered = await executor.control(operation_id="steer_one",
                                             verb="steer", text="Continue",
                                             expected_turn_id=factory.native.active_turn_id)
            assert steered.operation_id == "steer_one"
            interrupted = await executor.control(operation_id="interrupt_one",
                                                 verb="interrupt",
                                                 reason="Requested by the agent")
            assert interrupted.operation_id == "interrupt_one"
            assert interrupted.intent_hash == intent_hash(
                Operation("interrupt_one", "session_one", "turn.interrupt",
                          {"reason": "Requested by the agent"}), context)
            before = list(factory.native.sent)
            stale = EmbeddedExecutor(
                host, context=replace(context, configuration_revision=2),
                session_id="session_one", candidate=candidate,
                workspace_root=str(tmp_path), environment=environment,
                native_factory=factory)
            with pytest.raises(CoreError):
                await stale.submit(operation_id="stale_submit", text="Denied")
            assert factory.native.sent == before
            closed = await executor.close(operation_id="close_one",
                                          reason="Requested by the agent")
            assert closed.operation_id == "close_one"
            assert closed.intent_hash == intent_hash(
                Operation("close_one", "session_one", "runtime.close",
                          {"reason": "Requested by the agent"}), context)
            assert [item[1] for item in factory.native.sent] == [
                "submit_one", "steer_one", "interrupt_one"]
            assert factory.native.stopped
        finally:
            await host.shutdown(ShutdownPolicy(0, 0))
        assert core_error_projection(CoreError(
            "STALE_GENERATION", "open", possible_effect=True,
            retry_safe=False, operation_id="open_one")) == {
                "code": "STALE_GENERATION", "stage": "open",
                "possible_effect": True, "retry_safe": False,
                "operation_id": "open_one", "message": "STALE_GENERATION"}

    asyncio.run(scenario())
