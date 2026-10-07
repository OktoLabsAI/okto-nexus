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








def test_notification_configuration_and_open_override_require_authority(runtime):
    _, client, root, peers, operator, caller = runtime
    response = client.patch("/api/v1/harness/endpoints/endpoint-pi", headers={"x-api-key": caller}, json={
        "expected_revision": 1, "public_config": {"notify_target": {"strategy": "broadcast"}}})
    assert response.status_code == 403, response.text
    denied = tool(client, operator, "harness_open", {"agent_id": "worker", "kind": "pi", "project_root": root,
        "notify_target": {"strategy": "broadcast"}})
    assert not denied["ok"] and denied["error"]["code"] == "PERMISSION_DENIED", denied
    assert not peers










def test_stale_configuration_cannot_overwrite_new_notification_audience(runtime):
    _, client, _, _, operator, _ = runtime
    path = "/api/v1/harness/endpoints/endpoint-codex"
    response = client.patch(path, headers={"x-api-key": operator}, json={"expected_revision": 1,
        "public_config": {"notify_target": {"strategy": "direct", "agent_id": "caller"}}})
    assert response.status_code == 200, response.text
    stale = client.patch(path, headers={"x-api-key": operator}, json={"expected_revision": 1,
        "public_config": {"notify_target": {"strategy": "broadcast"}}})
    assert stale.status_code == 409, stale.text








def test_private_reply_does_not_require_initiator_to_send_to_itself(runtime):
    from test_runtime_relay import configure, wait_blocked
    configure(runtime, depth=1)
    _, client, _, _, operator, _ = runtime
    headers = {"x-api-key": operator}
    assert client.post("/api/v1/tags", headers=headers, json={"key": "team"}).status_code == 200
    assert client.post("/api/v1/tags/team/values", headers=headers, json={"value": "worker"}).status_code == 200
    assert client.patch("/api/v1/agents/worker", headers=headers, json={"tags": {"team": ["worker"]}}).status_code == 200
    assert client.patch("/api/v1/agents/caller", headers=headers, json={
        "comm_scope": {"outbound": {"team": ["worker"]}}}).status_code == 200
    send_message(runtime)
    rows = wait_blocked(runtime)
    assert len(rows) == 2
