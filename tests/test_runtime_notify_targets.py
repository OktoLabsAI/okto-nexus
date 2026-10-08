"""Explicit result audience uses canonical routing and approved endpoint state."""
import json
import threading
import time

import pytest

from test_pr34_remediation import runtime as runtime_fixture, send_message, tool, wait_sent
from test_runtime_commands import codex_session
from test_runtime_result_publication import result

runtime = runtime_fixture


def setup_notify(runtime, target, *, relay=False):
    deps, client, root, _, operator, _ = runtime
    codex_session(runtime)
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id="observer", role="observer")
    for agent in ("caller", "observer"):
        response = client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator}, json={
            "endpoint_id": "notify-" + agent, "agent_id": agent, "adapter_id": "pi", "project_root": root,
            "profile_id": "profile-pi", "enabled": True, "response_policy": "conversation" if relay else "explicit"})
        assert response.status_code == 200, response.text
        response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
            "agent_id": agent, "kind": "pi", "endpoint_id": "notify-" + agent, "project_root": root})
        assert response.status_code == 200, response.text
    response = client.patch("/api/v1/harness/endpoints/endpoint-codex", headers={"x-api-key": operator}, json={
        "expected_revision": 1, "public_config": {"notify_target": target, "relay_results": relay}})
    assert response.status_code == 200, response.text


def recipients(deps, message_id):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return [r[0] for r in uow.connection.execute(
            "SELECT recipient_agent_id FROM message_deliveries WHERE message_id=? ORDER BY recipient_agent_id", (message_id,))]
