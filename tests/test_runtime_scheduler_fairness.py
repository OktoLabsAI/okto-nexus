"""Selection is bounded by eligible lanes, not repeated rows from one endpoint."""
import threading

import pytest

from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, tool

runtime = runtime_fixture


def healthy_peer(runtime):
    deps, client, root, _, operator, _ = runtime
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id="healthy", role="reviewer")
    response = client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator}, json={
        "endpoint_id": "healthy-endpoint", "agent_id": "healthy", "adapter_id": "pi",
        "project_root": root, "profile_id": "profile-pi", "enabled": True,
        "response_policy": "conversation"})
    assert response.status_code == 200, response.text
    response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "healthy", "kind": "pi", "endpoint_id": "healthy-endpoint", "project_root": root})
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.parametrize("lane", ["delivery", "close"])
def test_pending_limit_selects_distinct_lanes_before_truncation(runtime, lane, monkeypatch):
    deps, client, _, _, operator, _ = runtime
    first = open_rest(runtime)
    assert first.status_code == 200, first.text
    second = healthy_peer(runtime)
    monkeypatch.setattr(deps.runtime_dispatcher, "scan_once", lambda: None)
    monkeypatch.setattr(deps.runtime_dispatcher.command_dispatcher, "scan_once", lambda: None)
    for index, session in enumerate((first.json()["data"], first.json()["data"], second)):
        if lane == "delivery":
            send_message(runtime, target={"strategy": "direct", "agent_id": session["owning_agent_id"]})
        else:
            response = tool(client, operator, "harness_close", {"session_id": session["session_id"],
                "idempotency_key": "fairness-close-" + str(index)})
            assert response["ok"], response
    with deps.connection_factory.unit_of_work(write=False) as uow:
        if lane == "delivery":
            selected = deps.runtime_dispatcher.repo.pending(uow, limit=2)
        else:
            selected = deps.runtime_dispatcher.command_dispatcher.repo.pending(uow, control=True, close_only=True, limit=2)
    assert {row["endpoint_id"] for row in selected} == {"endpoint-pi", "healthy-endpoint"}


def test_healthy_lane_dispatches_while_first_native_call_is_blocked(runtime, monkeypatch):
    deps = runtime[0]
    assert open_rest(runtime).status_code == 200
    healthy_peer(runtime)
    owner = deps.runtime_dispatcher
    original_scan, original_dispatch = owner.scan_once, owner.dispatch
    entered, release, healthy = threading.Event(), threading.Event(), threading.Event()

    def dispatch(operation):
        if operation["recipient_agent_id"] == "worker":
            entered.set()
            assert release.wait(10), "fixture release missing"
        result = original_dispatch(operation)
        if operation["recipient_agent_id"] == "healthy":
            healthy.set()
        return result

    monkeypatch.setattr(owner, "scan_once", lambda: None)
    monkeypatch.setattr(owner, "dispatch", dispatch)
    for recipient in ("worker", "worker", "healthy"):
        send_message(runtime, target={"strategy": "direct", "agent_id": recipient})
    monkeypatch.setattr(owner, "scan_once", original_scan)
    try:
        owner.wake()
        assert entered.wait(5), "blocked lane was not dispatched"
        assert healthy.wait(5), "healthy lane waited behind repeated rows from the blocked endpoint"
        assert not release.is_set()
    finally:
        release.set()


def test_one_agent_cannot_reserve_all_normal_workers_with_extra_endpoints(runtime, monkeypatch):
    deps, client, root, _, operator, _ = runtime
    first = open_rest(runtime)
    assert first.status_code == 200, first.text
    healthy = healthy_peer(runtime)
    headers = {"x-api-key": operator}
    response = client.post("/api/v1/harness/endpoints", headers=headers, json={
        "endpoint_id": "worker-extra", "agent_id": "worker", "adapter_id": "pi",
        "project_root": root, "profile_id": "profile-pi", "enabled": True})
    assert response.status_code == 200, response.text
    second = client.post("/api/v1/harness/sessions", headers=headers, json={
        "agent_id": "worker", "kind": "pi", "endpoint_id": "worker-extra", "project_root": root})
    assert second.status_code == 200, second.text
    monkeypatch.setattr(deps.runtime_dispatcher.command_dispatcher, "scan_once", lambda: None)
    for session in (first.json()["data"], second.json()["data"], healthy):
        result = tool(client, operator, "harness_send", {"session_id": session["session_id"],
            "payload": {"text": "bounded normal worker"}})
        assert result["ok"], result
    with deps.connection_factory.unit_of_work(write=False) as uow:
        selected = deps.runtime_dispatcher.command_dispatcher.repo.pending(uow, control=False, limit=2)
    assert len(selected) == 2
    assert "healthy-endpoint" in {row["endpoint_id"] for row in selected}, "Extra endpoints multiplied one agent's worker budget"
