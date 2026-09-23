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
    from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE
    deps, client, root, _, operator, _ = runtime
    source = _FAKE_SERVER_SOURCE.replace('"delta": text', '"delta": "L" * 70000')
    assert source != _FAKE_SERVER_SOURCE
    deps.harness_connector_factories["codex"] = lambda **kwargs: CodexAppServerConnector(
        command=[sys._base_executable, "-u", "-c", source], cwd=root, env=kwargs["backend"]["env"])
    response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator},
        json={"agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert response.status_code == 200, response.text


def test_large_runtime_result_uses_private_canonical_artifact(runtime):
    from test_pr34_remediation import send_message, tool
    from test_runtime_result_publication import result
    from okto_nexus.application.auth import AgentKeyAuthService
    from okto_nexus.adapters.inbound.mcp.tools.artifacts import build_service
    from okto_nexus.errors import OktoNexusError
    deps, client, root, _, _, caller = runtime
    large_output_session(runtime)
    source = send_message(runtime, body="produce large fixture")
    published = result(runtime, source["runtime_operations"][0], "PUBLISHED")
    aid = published["output_artifact_id"]
    assert aid
    with deps.connection_factory.unit_of_work(write=False) as uow:
        artifact = deps.repos.artifacts.get(uow, workspace_id=source["workspace_id"], artifact_id=aid)
        assert artifact.reader_agent_ids == ["caller", "worker"]
        assert artifact.size_bytes == 70000
        message = uow.connection.execute("SELECT artifacts,body FROM messages WHERE message_id=?", (published["publication_message_id"],)).fetchone()
        assert aid in message["artifacts"] and "Preview truncated" in message["body"]
    assert deps.repos.artifact_store.read_bytes(artifact.storage_path) == b"L" * 70000
    assert tool(client, caller, "artifact_get", {"project_root": root, "artifact_id": aid})["ok"]
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id="outsider")
        outsider = AgentKeyAuthService(deps.repos.agents, deps.clock).issue_key(uow, agent_id="outsider")
    hidden = tool(client, outsider, "artifact_get", {"project_root": root, "artifact_id": aid})
    assert not hidden["ok"] and hidden["error"]["code"] == "NOT_FOUND"
    with pytest.raises(OktoNexusError):
        build_service(deps).artifact_get(project_root=root, artifact_id=aid)


def test_runtime_artifact_catalog_rolls_back_with_publication_and_reuses_durable_blob(runtime, monkeypatch):
    from test_pr34_remediation import send_message
    from test_runtime_result_publication import result
    from okto_nexus.application.runtime_results import RuntimeResultService
    deps = runtime[0]
    large_output_session(runtime)
    finish = RuntimeResultService.finish
    failed = threading.Event()
    def fail(uow, **kwargs):
        finish(uow, **kwargs)
        failed.set()
        raise OSError("fixture artifact/publication cut")
    with monkeypatch.context() as patch:
        patch.setattr(RuntimeResultService, "finish", staticmethod(fail))
        source = send_message(runtime, body="artifact commit cut")
        result(runtime, source["runtime_operations"][0], "PENDING_AUTHORIZATION")
        assert failed.wait(5), "production publication worker did not reach the injected commit cut"
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT count(*) FROM artifacts").fetchone()[0] == 0
        blobs = list(deps.repos.artifact_store.root.rglob("runtime-result.txt"))
        assert len(blobs) == 1 and blobs[0].read_bytes() == b"L" * 70000
    deps.runtime_dispatcher.wake()
    row = result(runtime, source["runtime_operations"][0], "PUBLISHED")
    assert row["output_artifact_id"]
    assert list(deps.repos.artifact_store.root.rglob("runtime-result.txt")) == blobs


def test_blocked_artifact_worker_keeps_heartbeat_and_holds_shutdown_ownership(runtime, monkeypatch):
    from test_pr34_remediation import send_message
    from okto_nexus.application.runtime_shutdown import shutdown_runtime
    deps = runtime[0]
    large_output_session(runtime)
    entered, release = threading.Event(), threading.Event()
    put = deps.repos.artifact_store.put
    calls = []
    def blocked(**kwargs):
        calls.append(kwargs["artifact_id"])
        entered.set()
        assert release.wait(15)
        return put(**kwargs)
    monkeypatch.setattr(deps.repos.artifact_store, "put", blocked)
    dispatcher = deps.runtime_dispatcher
    try:
        send_message(runtime, body="block artifact storage")
        assert entered.wait(5)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            lease = uow.connection.execute("SELECT lease_expires_at FROM runtime_dispatcher_owner").fetchone()[0]
        for _ in range(5):
            dispatcher.wake()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            with deps.connection_factory.unit_of_work(write=False) as uow:
                current = uow.connection.execute("SELECT lease_expires_at FROM runtime_dispatcher_owner").fetchone()[0]
            if current != lease:
                break
            time.sleep(.01)
        assert current != lease, "artifact storage blocked owner heartbeat"
        assert len(calls) == 1 and dispatcher._publication_active
        shut = shutdown_runtime(dispatcher, deps.harness_supervisor, timeout=.1)
        assert shut == {"state": "pending", "owner_released": False}
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert dispatcher.repo.owns(uow, owner_id=dispatcher.owner_id, epoch=dispatcher.epoch, now=deps.clock.now_iso())
    finally:
        release.set()
    assert dispatcher._shutdown_finished.wait(5)


def test_native_terminal_wake_during_publication_scan_is_not_lost(runtime):
    from test_pr34_remediation import send_message
    from test_runtime_result_publication import result
    from test_runtime_commands import codex_session
    deps = runtime[0]
    codex_session(runtime)
    dispatcher = deps.runtime_dispatcher
    publish = dispatcher.publish_results
    entered, release = threading.Event(), threading.Event()
    calls = []
    def paused():
        calls.append(True)
        if len(calls) == 1:
            entered.set()
            assert release.wait(10)
            return 0
        return publish()
    dispatcher.publish_results = paused
    try:
        dispatcher.wake()
        assert entered.wait(3)
        source = send_message(runtime, body="publication wake during active scan")
        result(runtime, source["runtime_operations"][0], "PENDING_AUTHORIZATION")
        dispatcher.wake()
        # Wait for the owner to observe this wake while publication is busy.
        with deps.connection_factory.unit_of_work(write=False) as uow:
            lease = uow.connection.execute("SELECT lease_expires_at FROM runtime_dispatcher_owner").fetchone()[0]
        dispatcher.wake()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            with deps.connection_factory.unit_of_work(write=False) as uow:
                renewed = uow.connection.execute("SELECT lease_expires_at FROM runtime_dispatcher_owner").fetchone()[0]
            if renewed != lease:
                break
            time.sleep(.01)
        assert renewed != lease
        release.set()
        assert result(runtime, source["runtime_operations"][0], "PUBLISHED")["publication_message_id"]
    finally:
        release.set()
        dispatcher.publish_results = publish


def test_runtime_artifact_quota_is_reserved_before_filesystem_effect(runtime):
    from test_pr34_remediation import send_message
    from test_runtime_result_publication import result
    deps, client, _, _, operator, _ = runtime
    large_output_session(runtime)
    configured = client.post("/api/v1/harness/artifacts", headers={"x-api-key": operator},
        json={"action": "quota", "quota_bytes": 262144, "idempotency_key": "small-fixture-quota", "reason": "fixture quota boundary"})
    assert configured.status_code == 200, configured.text
    source = send_message(runtime, body="fixture retention quota")
    row = result(runtime, source["runtime_operations"][0], "BLOCKED")
    assert row["publication_reason"] == "QUOTA_EXCEEDED"
    assert row["artifact_reserved_bytes"] == 0 and not row["output_artifact_id"]
    assert row["output_text"] == "L" * 70000
    assert not list(deps.repos.artifact_store.root.rglob("runtime-result.txt"))


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_large_result_artifact_remains_uncatalogued_until_canonical_approval(runtime, decision):
    from test_pr34_remediation import send_message, tool
    from test_runtime_result_publication import result
    from test_governance import _attach, _rule
    from okto_nexus.application.runtime_results import RuntimeResultService
    deps, client, root, _, operator, caller = runtime
    deps.config.feature_hitl = True
    large_output_session(runtime)
    _attach(deps, "worker", governance=[_rule("message_create", "require_approval")])
    source = send_message(runtime, body="artifact awaiting decision")
    row = result(runtime, source["runtime_operations"][0], "PENDING_APPROVAL")
    artifact_id = RuntimeResultService.artifact_id(row)
    hidden = tool(client, caller, "artifact_get", {"project_root": root, "artifact_id": artifact_id})
    assert not hidden["ok"] and hidden["error"]["code"] == "NOT_FOUND"
    assert row["artifact_reserved_bytes"] == 70000
    response = client.post(f"/api/v1/approvals/{row['publication_approval_id']}/decision",
        headers={"x-api-key": operator}, json={"decision": decision})
    assert response.status_code == 200, response.text
    deps.runtime_dispatcher.wake()
    final = result(runtime, source["runtime_operations"][0], "PUBLISHED" if decision == "approve" else "BLOCKED")
    assert bool(final["output_artifact_id"]) == (decision == "approve")
    read = tool(client, caller, "artifact_get", {"project_root": root, "artifact_id": artifact_id})
    assert read["ok"] == (decision == "approve")
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
