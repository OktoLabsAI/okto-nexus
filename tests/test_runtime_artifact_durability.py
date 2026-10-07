"""Shared artifact storage prerequisite for durable runtime result artifacts."""
from contextlib import contextmanager
import threading
import os
import stat
import sys
import time

import pytest

from test_pr34_remediation import runtime as runtime_fixture

runtime = runtime_fixture


@pytest.mark.parametrize("runtime", ["unconfigured"], indirect=True)
def test_artifact_storage_does_not_hold_sqlite_writer(runtime, monkeypatch):
    from okto_nexus.adapters.inbound.mcp.tools.artifacts import build_service
    deps, _, root, _, _, _ = runtime
    service = build_service(deps)
    state = threading.local()
    unit = deps.connection_factory.unit_of_work
    @contextmanager
    def observed(*args, **kwargs):
        write = kwargs.get("write", True)
        with unit(*args, **kwargs) as uow:
            state.depth = getattr(state, "depth", 0) + int(write)
            try:
                yield uow
            finally:
                state.depth -= int(write)
    monkeypatch.setattr(deps.connection_factory, "unit_of_work", observed)
    put = service._artifact_store.put
    def checked(**kwargs):
        assert not getattr(state, "depth", 0), "artifact filesystem IO holds the SQLite write transaction"
        return put(**kwargs)
    monkeypatch.setattr(service._artifact_store, "put", checked)
    saved = service.artifact_put(project_root=root, agent_id="worker", artifact_type="text", content="fixture artifact")
    assert saved["artifact_id"]


@pytest.mark.parametrize("runtime", ["unconfigured"], indirect=True)
def test_permission_change_during_storage_prevents_catalog_commit(runtime, monkeypatch):
    from okto_nexus.adapters.inbound.mcp.tools.artifacts import build_service
    from okto_nexus.errors import OktoNexusError
    deps, _, root, _, _, _ = runtime
    service = build_service(deps)
    put = service._artifact_store.put
    paths = []
    def revoke(**kwargs):
        stored = put(**kwargs)
        paths.append(stored.storage_path)
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agents SET permissions=? WHERE agent_id='worker'", ('{"artifacts":{"put":false}}',))
        return stored
    monkeypatch.setattr(service._artifact_store, "put", revoke)
    with pytest.raises(OktoNexusError):
        service.artifact_put(project_root=root, agent_id="worker", artifact_type="text", content="fixture")
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM artifacts").fetchone()[0] == 0
    assert paths and not (service._artifact_store.root / paths[0]).exists()


@pytest.mark.parametrize("runtime", ["unconfigured"], indirect=True)
def test_payload_and_manifest_fsync_precede_catalog_reference(runtime, monkeypatch):
    from okto_nexus.adapters.inbound.mcp.tools.artifacts import build_service
    deps, _, root, _, _, _ = runtime
    service = build_service(deps)
    synced = []
    sync = os.fsync
    def observe(fd):
        regular = stat.S_ISREG(os.fstat(fd).st_mode)
        sync(fd)
        if regular:
            synced.append(fd)
    create = deps.repos.artifacts.create
    def checked(*args, **kwargs):
        assert len(synced) >= 2, "catalog references bytes that have not been fsynced"
        return create(*args, **kwargs)
    monkeypatch.setattr(os, "fsync", observe)
    monkeypatch.setattr(deps.repos.artifacts, "create", checked)
    service.artifact_put(project_root=root, agent_id="worker", artifact_type="text", content="durable fixture")


@pytest.mark.parametrize("runtime", ["unconfigured"], indirect=True)
def test_uncertain_artifact_fsync_never_creates_catalog_reference(runtime, monkeypatch):
    from okto_nexus.adapters.inbound.mcp.tools.artifacts import build_service
    deps, _, root, _, _, _ = runtime
    service = build_service(deps)
    sync = os.fsync
    def fail(fd):
        if stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("fixture artifact flush failure")
        return sync(fd)
    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", fail)
        with pytest.raises(Exception, match="persist artifact"):
            service.artifact_put(project_root=root, agent_id="worker", artifact_type="text", content="uncertain fixture")
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM artifacts").fetchone()[0] == 0


def large_output_session(runtime):
    from legacy_native_fixture.codex import CodexAppServerConnector
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE
    deps, client, root, _, operator, _ = runtime
    source = _FAKE_SERVER_SOURCE.replace('"delta": text', '"delta": "L" * 70000')
    assert source != _FAKE_SERVER_SOURCE
    deps.harness_connector_factories["codex"] = lambda **kwargs: CodexAppServerConnector(
        command=[sys._base_executable, "-u", "-c", source], cwd=root, env=kwargs["backend"]["env"])
    response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator},
        json={"agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert response.status_code == 200, response.text
