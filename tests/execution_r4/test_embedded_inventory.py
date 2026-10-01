"""Local inventory is owned by the real serve lifecycle without WSS or Core stores."""
import asyncio
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from nexus_connector_core import InstallationCandidate
from nexus_connector_core.discovery import fingerprint

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.bootstrap import embedded_inventory
from okto_nexus.errors import OktoNexusError


def app_for(home):
    deps = bootstrap({}, ["--home", str(home), "--feature-harness-integrations", "true"])
    return deps, build_app(deps)


def agent_key(deps, app):
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("INSERT OR IGNORE INTO agents(agent_id,created_at) VALUES ('viewer',?)",
                               (deps.clock.now_iso(),))
        return app.state.auth.issue_key(uow, agent_id="viewer")


def test_serve_publishes_path_free_local_inventory_without_runtime_or_wss(tmp_path, monkeypatch):
    binary = tmp_path / "codex.exe"
    binary.write_bytes(b"Discovery-only technical candidate")
    candidate = InstallationCandidate("codex_app_server", str(binary), fingerprint(binary), "explicit", "selected")
    monkeypatch.setattr(embedded_inventory, "discover_local_candidates",
                        lambda **_: SimpleNamespace(candidates=(candidate,)))
    deps, app = app_for(tmp_path / "home")
    key = agent_key(deps, app)
    with TestClient(app) as client:
        owner = app.state.embedded_inventory_owner
        assert owner.candidates == (candidate,)
        assert not (tmp_path / "home/core-runtime").exists()
        headers = {"Authorization": "Bearer " + key}
        viewed = client.get(f"/v1/runtime/executors/{owner.key.executor_id}/inventory", headers=headers)
        assert viewed.status_code == 200, viewed.text
        assert str(tmp_path) not in viewed.text
        assert viewed.json()["snapshot"]["evidence"][0]["candidate_ref"]
        assert viewed.json()["freshness"] == "OFFLINE"
        assert viewed.json()["eligible_for_new_start"] is False
        options = client.get("/v1/agents/viewer/runtime-options",
            params={"executor_id":owner.key.executor_id}, headers=headers)
        assert options.status_code == 200, options.text
        assert all(not item["can_start"] for item in options.json()["options"])
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT control_state FROM execution_executors WHERE kind='embedded'").fetchone()[0] == "RECOVERING"
            assert uow.connection.execute("SELECT COUNT(*) FROM execution_link_tickets").fetchone()[0] == 0
            assert uow.connection.execute("SELECT COUNT(*) FROM execution_sessions").fetchone()[0] == 0
    assert not (tmp_path / "home/core-runtime").exists()
    assert not app.state.inventory_fresh_publications
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT control_state FROM execution_executors WHERE kind='embedded'").fetchone()[0] == "DISCONNECTED"


def test_new_serve_owner_republishes_empty_inventory_and_retains_two_snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr(embedded_inventory, "discover_local_candidates",
                        lambda **_: SimpleNamespace(candidates=()))
    records = []
    for _ in range(3):
        deps, app = app_for(tmp_path / "home")
        with TestClient(app):
            owner = app.state.embedded_inventory_owner
            records.append((owner.key, owner.generation, owner.publication.publication_sequence))
            assert owner.candidates == ()
        assert not (tmp_path / "home/core-runtime").exists()
    assert len({row[0] for row in records}) == 1
    assert [row[1] for row in records] == [2, 3, 4]
    assert [row[2] for row in records] == [1, 2, 3]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert [row[0] for row in uow.connection.execute("SELECT publication_sequence FROM execution_inventory_snapshots ORDER BY publication_sequence")] == [2, 3]


@pytest.mark.parametrize("change", ["generation", "owner", "revoked"])
def test_delayed_publication_cannot_cross_embedded_owner_change(tmp_path, monkeypatch, change):
    monkeypatch.setattr(embedded_inventory, "discover_local_candidates",
                        lambda **_: SimpleNamespace(candidates=()))
    deps, app = app_for(tmp_path / "home")
    with TestClient(app) as client:
        owner = app.state.embedded_inventory_owner
        with deps.connection_factory.unit_of_work() as uow:
            sql = {
                "generation":"generation=generation+1",
                "owner":"owner_instance_id='successor'",
                "revoked":"revoked_at='2026-01-01T00:00:00Z'",
            }[change]
            uow.connection.execute("UPDATE execution_executors SET " + sql + " WHERE kind='embedded'")
        with pytest.raises(OktoNexusError, match="no longer current"):
            client.portal.call(owner.refresh)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT MAX(publication_sequence) FROM execution_inventory_snapshots").fetchone()[0] == 1
        assert owner.publication.publication_sequence == 1
        assert (owner.key.server_id, owner.key.executor_id) not in app.state.inventory_fresh_publications


def test_cancelled_waiters_keep_discovery_and_cleanup_owned(tmp_path, monkeypatch):
    monkeypatch.setattr(embedded_inventory, "discover_local_candidates",
                        lambda **_: SimpleNamespace(candidates=()))
    deps, app = app_for(tmp_path / "home")
    with TestClient(app) as client:
        owner = app.state.embedded_inventory_owner
        entered, release = threading.Event(), threading.Event()

        def held(**_):
            entered.set()
            assert release.wait(5)
            return SimpleNamespace(candidates=())

        monkeypatch.setattr(embedded_inventory, "discover_local_candidates", held)

        async def scenario():
            refresh = asyncio.create_task(owner.refresh())
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                refresh.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await refresh
                closing = asyncio.create_task(owner.close())
                await asyncio.sleep(0)
                closing.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await closing
                assert not owner._refresh_task.done() and not owner._close_task.done()
            finally:
                release.set()
                await asyncio.wait_for(owner.close(), 3)
            assert owner._refresh_task.done()
            assert not app.state.inventory_fresh_publications

        client.portal.call(scenario)


def test_close_interrupts_passive_core_read_without_publishing(tmp_path, monkeypatch):
    import io
    import os
    from pathlib import Path
    from okto_nexus.adapters.outbound.execution.core_inventory import discover_local_candidates
    from okto_nexus.bootstrap.local_discovery import split_discovery_args

    monkeypatch.setattr(embedded_inventory, "discover_local_candidates",
                        lambda **_: SimpleNamespace(candidates=()))
    deps, app = app_for(tmp_path / "home")
    directory = tmp_path / "providers"
    directory.mkdir()
    binary = directory / ("codex.exe" if os.name == "nt" else "codex")
    binary.write_bytes(b"native bytes")
    if os.name != "nt":
        binary.chmod(0o755)
    configuration, _ = split_discovery_args(["--harness-root", str(directory)])
    monkeypatch.setenv("PATH", str(directory))
    with TestClient(app) as client:
        owner = app.state.embedded_inventory_owner
        previous = owner.publication.publication_sequence
        monkeypatch.setattr(deps, "local_discovery", configuration, raising=False)
        entered, release, exited = threading.Event(), threading.Event(), threading.Event()
        original_open = Path.open
        class Reader(io.BytesIO):
            def read(self, size=-1):
                entered.set()
                assert release.wait(3)
                return super().read(size)
            def close(self):
                super().close()
                exited.set()
        def opened(path, *args, **kwargs):
            if path == binary and args == ("rb",):
                return Reader(b"native bytes")
            return original_open(path, *args, **kwargs)
        monkeypatch.setattr(Path, "open", opened)
        monkeypatch.setattr(embedded_inventory, "discover_local_candidates", discover_local_candidates)
        async def scenario():
            refreshing = asyncio.create_task(owner.refresh())
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                closing = asyncio.create_task(owner.close())
                async with asyncio.timeout(2):
                    while not owner._stop.is_set():
                        await asyncio.sleep(0)
                assert not closing.done()
                release.set()
                await asyncio.wait_for(asyncio.shield(closing), 3)
                await refreshing
                assert exited.is_set() and owner._refresh_task.done()
                assert owner.publication.publication_sequence == previous
                assert owner.failure is None and not app.state.inventory_fresh_publications
            finally:
                release.set()
                await owner.close()
        client.portal.call(scenario)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT MAX(publication_sequence) FROM execution_inventory_snapshots").fetchone()[0] == previous
            assert uow.connection.execute("SELECT control_state FROM execution_executors WHERE kind='embedded'").fetchone()[0] == "DISCONNECTED"


def test_close_waits_for_started_inventory_publication(tmp_path, monkeypatch):
    monkeypatch.setattr(embedded_inventory, "discover_local_candidates",
                        lambda **_: SimpleNamespace(candidates=()))
    deps, app = app_for(tmp_path / "home")
    with TestClient(app) as client:
        owner = app.state.embedded_inventory_owner
        previous = owner.publication.publication_sequence
        entered, release = threading.Event(), threading.Event()
        original = owner._publish
        def publish(*args):
            entered.set()
            assert release.wait(3)
            return original(*args)
        monkeypatch.setattr(owner, "_publish", publish)
        async def scenario():
            refreshing = asyncio.create_task(owner.refresh())
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                closing = asyncio.create_task(owner.close())
                async with asyncio.timeout(2):
                    while not owner._stop.is_set():
                        await asyncio.sleep(0)
                assert not closing.done()
                release.set()
                await asyncio.wait_for(asyncio.shield(closing), 3)
                await refreshing
                assert owner.publication.publication_sequence == previous + 1
                assert not app.state.inventory_fresh_publications
            finally:
                release.set()
                await owner.close()
        client.portal.call(scenario)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT MAX(publication_sequence) FROM execution_inventory_snapshots").fetchone()[0] == previous + 1
            assert uow.connection.execute("SELECT control_state FROM execution_executors WHERE kind='embedded'").fetchone()[0] == "DISCONNECTED"
