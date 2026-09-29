"""Embedded Core owner composition smoke for NS07.01."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from nexus_connector_core import (
    CoreError, InstallationCandidate, OperationKey, ShutdownPolicy,
)

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.bootstrap.runtime_host import EmbeddedRuntimeHost


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
