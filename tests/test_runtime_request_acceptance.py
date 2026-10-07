"""Concurrent authenticated command admission and immutable request identity."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_pr34_remediation import runtime as runtime_fixture, open_rest, tool
from test_runtime_commands import wait_operation
from test_runtime_grants import issue

runtime = runtime_fixture


def send(runtime, surface, key, arguments):
    client = runtime[1]
    if surface == "mcp":
        return tool(client, key, "harness_send", arguments)
    body = dict(arguments)
    session = body.pop("session_id")
    response = client.post(f"/api/v1/harness/sessions/{session}/send",
                           headers={"x-api-key": key}, json=body)
    assert response.status_code in {200, 409}, response.text
    return response.json()


def snapshot(runtime):
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        # Transport progress may legitimately change while a repeated request
        # arrives. These are the immutable admission facts, without credentials.
        return [tuple(row) for row in uow.connection.execute(
            "SELECT operation_id,actor_agent_id,idempotency_key,request_hash,"
            "grant_id,runtime_session_id,endpoint_id,endpoint_revision,"
            "profile_revision,verb,payload,expected_owner_epoch,"
            "expected_operation_id,expected_turn_id FROM runtime_commands")]




@pytest.mark.parametrize("surface", ["rest", "mcp"])
@pytest.mark.parametrize("change", ["content", "target", "owner_context"])
def test_changed_request_cannot_replace_original_command(runtime, surface, change):
    deps, client, root, peers, operator, caller = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    grant = issue(runtime, ["send"], max_executions=1)
    arguments = {"session_id": sid, "payload": {"text": "immutable original"},
                 "idempotency_key": "immutable-send"}
    first = send(runtime, surface, caller, arguments)
    assert first["ok"], first
    operation = first["data"]["operation_id"]
    wait_operation(runtime, operation, lambda row: row["state"] == "SENT_UNCONFIRMED")
    before = snapshot(runtime)
    changed = dict(arguments)
    second_grant = None
    if change == "content":
        changed["payload"] = {"text": "replacement must not execute"}
    elif change == "owner_context":
        # Even specifying the correct epoch changes the original request's
        # context (which omitted it). An idempotency key cannot be rebound.
        changed["expected_owner_epoch"] = deps.runtime_dispatcher.epoch
    else:
        created = client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator}, json={
            "endpoint_id": "other-target", "agent_id": "worker", "adapter_id": "pi",
            "project_root": root, "profile_id": "profile-pi", "enabled": True})
        assert created.status_code == 200, created.text
        opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
            "agent_id": "worker", "kind": "pi", "endpoint_id": "other-target", "project_root": root})
        assert opened.status_code == 200, opened.text
        changed["session_id"] = opened.json()["data"]["session_id"]
        # Positive authority on both targets ensures the conflict is request
        # identity enforcement, rather than an unrelated ACL denial.
        second_grant = issue(runtime, ["send"], endpoint_id="other-target", max_executions=1)
    rejected = send(runtime, surface, caller, changed)
    assert not rejected["ok"] and rejected["error"]["code"] == "CONFLICT", rejected
    assert snapshot(runtime) == before
    assert json.loads(before[0][10]) == {"text": "immutable original"}
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants "
            "WHERE grant_id=?", (grant["grant_id"],)).fetchone()[0] == 1
        if second_grant:
            assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants "
                "WHERE grant_id=?", (second_grant["grant_id"],)).fetchone()[0] == 0
    retry = send(runtime, "mcp" if surface == "rest" else "rest", caller, arguments)
    assert retry["ok"] and retry["data"]["operation_id"] == operation
    assert [command.payload for peer in peers for command in peer.sent] == [{"text": "immutable original"}]
