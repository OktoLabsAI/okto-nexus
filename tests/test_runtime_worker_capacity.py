"""Native terminal evidence must not pretend a blocked transport worker returned."""
import threading

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_production_multiplex import configure, open_endpoint
from test_runtime_commands import wait_operation

runtime = runtime_fixture


@pytest.mark.parametrize("runtime", ["production"], indirect=True)
def test_observed_native_result_does_not_free_a_still_blocked_agent_worker(runtime, monkeypatch):
    deps, client, root, _, operator, _ = runtime
    configure(runtime)
    first = open_endpoint(runtime)
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id="healthy", role="reviewer")
    sessions = []
    for endpoint, agent in (("worker-extra", "worker"), ("healthy-endpoint", "healthy")):
        response = client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator}, json={
            "endpoint_id": endpoint, "agent_id": agent, "adapter_id": "codex",
            "project_root": root, "profile_id": "profile-codex", "enabled": True})
        assert response.status_code == 200, response.text
        sessions.append(open_endpoint(runtime, endpoint, agent=agent))
    entered, release = threading.Event(), threading.Event()
    service = deps.runtime_dispatcher.command_dispatcher.service
    execute = service.execute

    def held_after_write(command):
        result = execute(command)
        if command["verb"] == "send_turn" and command["endpoint_id"] in {"endpoint-codex", "worker-extra"}:
            entered.set()
            assert release.wait(15), "fixture must release owned worker"
        return result

    monkeypatch.setattr(service, "execute", held_after_write)

    def send(session):
        result = tool(client, operator, "harness_send", {"session_id": session["session_id"], "payload": {"text": "capacity fixture"}})
        assert result["ok"], result
        return result["data"]["operation_id"]

    try:
        first_id = send(first)
        assert entered.wait(5)
        wait_operation(runtime, first_id, lambda row: row["result_durable"])
        assert deps.runtime_dispatcher.operation_inflight(first_id), "The original transport stack must still occupy its worker"
        sibling_id = send(sessions[0])
        healthy_id = send(sessions[1])
        wait_operation(runtime, healthy_id, lambda row: row["result_durable"])
        assert not release.is_set(), "Healthy work must progress before the blocked agent returns"
    finally:
        release.set()
    wait_operation(runtime, sibling_id, lambda row: row["result_durable"])
