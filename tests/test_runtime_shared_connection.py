"""Shared production supervisor, real Codex transport and scripted native peer."""
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest

from legacy_native_fixture.codex import CodexAppServerConnector
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from test_pr34_remediation import runtime as runtime_fixture

from test_runtime_commands import wait_close_result

runtime = runtime_fixture


@pytest.mark.parametrize("terminal_current", [True, False])
def test_active_close_observes_interrupt_completion_before_detaching_shared_thread(runtime, terminal_current):
    deps, client, root, _, operator_key, _ = runtime
    peers = []
    source = _FAKE_SERVER_SOURCE if terminal_current else _FAKE_SERVER_SOURCE.replace(
        '"id": params["turnId"], "status": "interrupted"',
        '"id": "stale-turn", "status": "interrupted"')
    def factory(**kwargs):
        if not peers:
            peers.append(CodexAppServerConnector(command=[sys._base_executable, "-u", "-c", source],
                cwd=root, env=kwargs["backend"]["env"]))
            if not terminal_current:
                peers[0]._close_settle_timeout_s = .1
        return peers[0]
    deps.harness_connector_factories["codex"] = factory
    headers = {"x-api-key": operator_key}
    assert client.post("/api/v1/harness/endpoints", headers=headers, json={
        "endpoint_id": "sibling", "agent_id": "worker", "adapter_id": "codex",
        "project_root": root, "profile_id": "profile-codex", "enabled": True}).status_code == 200
    sessions = []
    for endpoint in ("endpoint-codex", "sibling"):
        response = client.post("/api/v1/harness/sessions", headers=headers, json={
            "agent_id": "worker", "kind": "codex", "endpoint_id": endpoint, "project_root": root})
        assert response.status_code == 200, response.text
        sessions.append(response.json()["data"]["session_id"])
    assert client.post(f"/api/v1/harness/sessions/{sessions[0]}/send", headers=headers,
                       json={"payload": {"text": "TRIGGER_HOLD"}}).status_code == 200
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if any(event.native_event == "turn/started" for event in deps.harness_supervisor.replay_events(sessions[0])):
            break
        time.sleep(.02)
    assert peers[0]._sessions_by_id[sessions[0]].active_turn_id
    closed = client.post(f"/api/v1/harness/sessions/{sessions[0]}/close", headers=headers, json={})
    assert closed.status_code == 200, closed.text
    expected = "detached" if terminal_current else "outcome_unknown"
    assert wait_close_result(client, operator_key, closed)["lifecycle_state"] == expected
    events = deps.harness_supervisor.replay_events(sessions[0])
    terminals = [event for event in events if event.native_event == "turn/completed"]
    assert len(terminals) == 1
    assert terminals[0].payload["turn"]["status"] == "interrupted"
    assert terminals[0].sequence < events[-1].sequence
    assert events[-1].payload["lifecycle_state"] == expected
    if not terminal_current:
        assert any(event.native_event == "transport/close_unsettled" for event in events)
        assert peers[0]._sessions_by_id[sessions[0]].active_turn_id
        assert "endpoint-codex" in deps.harness_supervisor._quarantined_bindings
    assert peers[0]._transport._proc.poll() is None
    assert client.post(f"/api/v1/harness/sessions/{sessions[1]}/send", headers=headers,
                       json={"payload": {"text": "sibling healthy"}}).status_code == 200








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
