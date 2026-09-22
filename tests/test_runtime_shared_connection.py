"""Shared production supervisor, real Codex transport and scripted native peer."""
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor

from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from test_pr34_remediation import runtime as runtime_fixture

runtime = runtime_fixture


def test_closing_one_codex_session_preserves_other_thread_and_process(runtime):
    deps, client, root, _, operator_key, _ = runtime
    peer = CodexAppServerConnector(command=[sys.executable, "-u", "-c", _FAKE_SERVER_SOURCE], cwd=root)
    deps.harness_connector_factories["codex"] = lambda **_: peer
    headers = {"x-api-key": operator_key}
    response = client.post("/api/v1/harness/endpoints", headers=headers, json={
        "endpoint_id": "second-codex", "agent_id": "worker", "adapter_id": "codex",
        "project_root": root, "profile_id": "profile-codex", "enabled": True})
    assert response.status_code == 200
    sessions = []
    for endpoint in ("endpoint-codex", "second-codex"):
        response = client.post("/api/v1/harness/sessions", headers=headers, json={
            "agent_id": "worker", "kind": "codex", "endpoint_id": endpoint, "project_root": root})
        assert response.status_code == 200, response.text
        sessions.append(response.json()["data"]["session_id"])
    process = peer._transport._proc
    assert len(peer._sessions_by_thread) == 2
    response = client.post(f"/api/v1/harness/sessions/{sessions[0]}/close", headers=headers, json={})
    assert response.status_code == 200, response.text
    closed = response.json()["data"]
    assert closed["lifecycle_state"] == "detached"
    assert closed["status"] != "ENDED", "unsubscribe is not observed native process exit"
    assert process.poll() is None, "closing a session killed another authorized session's process"
    repeated = client.post(f"/api/v1/harness/sessions/{sessions[0]}/close", headers=headers, json={})
    assert repeated.status_code == 200
    assert repeated.json()["data"]["lifecycle_state"] == "detached"
    response = client.post(f"/api/v1/harness/sessions/{sessions[1]}/send", headers=headers,
                           json={"payload": {"text": "second thread still works"}})
    assert response.status_code == 200, response.text
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        events = deps.harness_supervisor.replay_events(sessions[1])
        if any(event.kind == "turn_completed" for event in events):
            break
        time.sleep(.02)
    assert sum(event.kind == "turn_completed" for event in events) == 1
    assert all(event.session_id == sessions[1] for event in events)
    response = client.post(f"/api/v1/harness/sessions/{sessions[1]}/close", headers=headers, json={})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["lifecycle_state"] == "stopped"
    assert process.wait(timeout=5) is not None


def test_close_state_survives_projection_failure_and_repeated_close(runtime, monkeypatch):
    from test_pr34_remediation import open_rest
    deps, client, _, _, operator_key, _ = runtime
    session_id = open_rest(runtime).json()["data"]["session_id"]
    ingress = deps.harness_supervisor.event_ingress
    project = ingress.repo.project
    def unavailable(uow, **kwargs):
        if kwargs["event"].origin == "nexus":
            raise OSError("fixture lifecycle projection unavailable")
        return project(uow, **kwargs)
    monkeypatch.setattr(ingress.repo, "project", unavailable)
    headers = {"x-api-key": operator_key}
    response = client.post(f"/api/v1/harness/sessions/{session_id}/close", headers=headers, json={})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["metadata"]["lifecycle_projection_pending"]
    assert session_id in deps.harness_supervisor._closing
    repeated = client.post(f"/api/v1/harness/sessions/{session_id}/close", headers=headers, json={})
    assert repeated.status_code == 200
    assert ingress.journal.watermark == 2, "repeat must not issue another stop"
    monkeypatch.undo()
    ingress.recover()
    assert session_id not in deps.harness_supervisor._closing
    with deps.connection_factory.unit_of_work(write=False) as uow:
        session = deps.repos.harness_sessions.get(uow, session_id=session_id)
        assert session.lifecycle_state == "detached"  # fixture has no OS stop observation
        presence = deps.repos.sessions.get(uow, session.presence_session_id)
        assert presence.status == "closed"


def test_native_payload_cannot_forge_lifecycle_transition(runtime):
    from okto_nexus.domain.harness import HarnessEvent
    from test_pr34_remediation import open_rest
    deps, _, _, _, _, _ = runtime
    session_id = open_rest(runtime).json()["data"]["session_id"]
    deps.harness_supervisor._handle_event(session_id, HarnessEvent(
        session_id=session_id, harness_kind="pi", kind="tool_activity", native_event="nexus/runtime_state",
        occurred_at=deps.clock.now_iso(), payload={"origin": "nexus", "lifecycle_state": "stopped", "stop_observed": True}))
    with deps.connection_factory.unit_of_work(write=False) as uow:
        session = deps.repos.harness_sessions.get(uow, session_id=session_id)
        assert session.lifecycle_state == "protocol_ready"
        assert session.status == "RUNNING"


def test_connection_leases_protect_live_and_starting_siblings():
    import pytest
    from okto_nexus.application.runtime_lifecycle import RuntimeConnectionLifecycle
    connection = RuntimeConnectionLifecycle()
    first = connection.new_scope(multiplexing=True)
    second = connection.new_scope(multiplexing=True)
    stopped = []
    first.register(lambda: stopped.append("owned-process"))
    assert not first.claim_exclusive_teardown()
    first.cancel()
    assert stopped == []
    third = connection.new_scope(multiplexing=True)
    second.cancel()
    assert stopped == []
    assert third.claim_exclusive_teardown()
    with pytest.raises(RuntimeError):
        connection.new_scope(multiplexing=True)
    third.cancel()
    assert stopped == ["owned-process"]
    with pytest.raises(RuntimeError):
        first.register(lambda: stopped.append("late-process"))
    assert stopped == ["owned-process", "late-process"]


def test_concurrent_close_drains_final_event_once(runtime, monkeypatch):
    from test_pr34_remediation import open_rest
    deps, client, _, peers, operator_key, _ = runtime
    session_id = open_rest(runtime).json()["data"]["session_id"]
    entered, release = threading.Event(), threading.Event()
    peer = peers[0]
    original = peer.close
    calls = []
    def closing():
        calls.append("close")
        entered.set()
        assert release.wait(5)
        original()
    monkeypatch.setattr(peer, "close", closing)
    def request_close():
        return client.post(f"/api/v1/harness/sessions/{session_id}/close",
                          headers={"x-api-key": operator_key}, json={})
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(request_close)
        try:
            assert entered.wait(5)
            peer.push_event(kind="turn_completed", payload={"text": "final while closing"})
            peer.end()
            second = pool.submit(request_close).result(timeout=5)
            assert second.status_code == 200
            assert second.json()["data"]["lifecycle_state"] == "stop_requested"
        finally:
            release.set()
        assert first.result(timeout=10).status_code == 200
    assert calls == ["close"]
    events = deps.harness_supervisor.replay_events(session_id)
    assert sum(item.kind == "turn_completed" for item in events) == 1
    assert events[-1].origin == "nexus"
    assert events[-1].payload["lifecycle_state"] == "detached"
    assert session_id not in deps.harness_supervisor._closing


def test_shared_connection_cannot_cross_approved_profile_context(runtime):
    deps, client, root, _, operator_key, _ = runtime
    peer = CodexAppServerConnector(command=[sys.executable, "-u", "-c", _FAKE_SERVER_SOURCE], cwd=root)
    deps.harness_connector_factories["codex"] = lambda **_: peer
    headers = {"x-api-key": operator_key}
    response = client.post("/api/v1/harness/sessions", headers=headers, json={
        "agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert response.status_code == 200, response.text
    response = client.post("/api/v1/harness/profiles", headers=headers,
                           json={"profile_id": "other-profile", "adapter_id": "codex", "enabled": True})
    assert response.status_code == 200
    response = client.post("/api/v1/harness/endpoints", headers=headers, json={
        "endpoint_id": "other-profile-endpoint", "agent_id": "worker", "adapter_id": "codex",
        "project_root": root, "profile_id": "other-profile", "enabled": True})
    assert response.status_code == 200
    response = client.post("/api/v1/harness/sessions", headers=headers, json={
        "agent_id": "worker", "kind": "codex", "endpoint_id": "other-profile-endpoint", "project_root": root})
    assert response.status_code == 409, response.text
    assert len(peer._sessions_by_thread) == 1
    assert peer._transport._proc.poll() is None
