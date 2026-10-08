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
