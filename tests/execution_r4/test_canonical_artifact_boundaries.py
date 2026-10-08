"""Private Core result artifacts retain quota and shutdown ownership boundaries."""
import threading
import time

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract
from test_canonical_delivery import connected_local
from test_canonical_grant_regressions import mcp_helpers
from test_canonical_result_artifact import large_result
from test_canonical_result_publication import wait_result, workspace
from test_agent_recovery_isolation import create_agent


def test_complete_result_artifact_is_private_to_its_recorded_readers(connected_local, monkeypatch):
    from test_pr34_remediation import tool
    from okto_nexus.adapters.inbound.mcp.tools.artifacts import build_service
    from okto_nexus.errors import OktoNexusError
    setup, _, native = connected_local
    deps, _, client, headers, *_ = setup
    outsider = create_agent(setup, "outsider")
    large_result(connected_local, monkeypatch)
    published = wait_result(setup, "PUBLISHED")
    aid = published["output_artifact_id"]
    assert aid
    with deps.connection_factory.unit_of_work(write=False) as uow:
        artifact = deps.repos.artifacts.get(uow, workspace_id=workspace(setup), artifact_id=aid)
        assert artifact.reader_agent_ids == ["operator", "subject"]
        assert artifact.size_bytes == 90000
        message = uow.connection.execute("SELECT artifacts,body FROM messages WHERE message_id=?", (published["publication_message_id"],)).fetchone()
        assert aid in message["artifacts"] and "Preview truncated" in message["body"]
    assert deps.repos.artifact_store.read_bytes(artifact.storage_path) == b"L" * 90000
    client.headers["host"] = "127.0.0.1:8000"
    args = dict(project_root=str(setup[-1]), artifact_id=aid)
    assert tool(client, headers["subject"]["Authorization"].removeprefix("Bearer "), "artifact_get", args)["ok"]
    hidden = tool(client, outsider[3]["subject"]["Authorization"].removeprefix("Bearer "), "artifact_get", args)
    assert not hidden["ok"] and hidden["error"]["code"] == "NOT_FOUND", hidden
    with pytest.raises(OktoNexusError):
        build_service(deps).artifact_get(**args)
    assert native.opens == 1 and len(native.native.sent) == 1


def test_artifact_quota_refuses_before_reservation_or_filesystem_effect(connected_local, monkeypatch):
    setup, _, native = connected_local
    deps, _, client, headers, *_ = setup
    configured = client.post("/api/v1/harness/artifacts", headers=headers["operator"], json=dict(
        action="quota", quota_bytes=262144, idempotency_key="small-artifact-quota", reason="Fixture capacity boundary"))
    assert configured.status_code == 200, configured.text
    def forbidden(**kwargs):
        raise AssertionError("Quota refusal reached artifact filesystem effect")
    monkeypatch.setattr(deps.repos.artifact_store, "put", forbidden)
    large_result(connected_local, monkeypatch)
    row = wait_result(setup, "BLOCKED")
    assert row["publication_reason"] == "QUOTA_EXCEEDED"
    assert row["artifact_reserved_bytes"] == 0 and not row["output_artifact_id"]
    assert row["output_text"] == "L" * 90000
    assert not list(deps.repos.artifact_store.root.rglob("runtime-result.txt"))
    assert native.opens == 1 and len(native.native.sent) == 1


def test_blocked_artifact_keeps_dispatch_heartbeat_and_shutdown_ownership(connected_local, monkeypatch):
    from okto_nexus.application.runtime_shutdown import shutdown_runtime
    setup, _, _ = connected_local
    deps = setup[0]
    entered, release = threading.Event(), threading.Event()
    original = deps.repos.artifact_store.put
    calls = []
    def blocked(**kwargs):
        calls.append(kwargs["artifact_id"])
        entered.set()
        assert release.wait(20)
        return original(**kwargs)
    monkeypatch.setattr(deps.repos.artifact_store, "put", blocked)
    dispatcher = deps.runtime_dispatcher
    try:
        large_result(connected_local, monkeypatch)
        assert entered.wait(10)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            lease = uow.connection.execute("SELECT lease_expires_at FROM runtime_dispatcher_owner").fetchone()[0]
        for _ in range(5):
            dispatcher.wake()
        deadline = time.monotonic() + 5
        while True:
            with deps.connection_factory.unit_of_work(write=False) as uow:
                current = uow.connection.execute("SELECT lease_expires_at FROM runtime_dispatcher_owner").fetchone()[0]
            if current != lease:
                break
            assert time.monotonic() < deadline, "Artifact filesystem effect blocked owner heartbeat"
            time.sleep(.01)
        assert len(calls) == 1 and dispatcher._publication_active
        shut = shutdown_runtime(dispatcher, deps.harness_supervisor, timeout=.1)
        assert shut == dict(state="pending", owner_released=False)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert dispatcher.repo.owns(uow, owner_id=dispatcher.owner_id, epoch=dispatcher.epoch, now=deps.clock.now_iso())
    finally:
        release.set()
    assert dispatcher._shutdown_finished.wait(10)
