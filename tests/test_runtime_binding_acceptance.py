"""Canonical workspace isolation and continuation affinity across selection changes."""
import json
import time

import pytest

from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, tool
from test_runtime_outbox import wait_status
from test_runtime_commands import wait_operation

runtime = runtime_fixture


def add_endpoint(runtime, *, endpoint, root, priority=0):
    _, client, _, _, operator, _ = runtime
    response = client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator}, json={
        "endpoint_id": endpoint, "agent_id": "worker", "adapter_id": "pi", "project_root": root,
        "profile_id": "profile-pi", "enabled": True, "response_policy": "conversation", "priority": priority})
    assert response.status_code == 200, response.text
    opened = tool(client, operator, "harness_open", {"agent_id": "worker", "kind": "pi",
        "project_root": root, "endpoint_id": endpoint})
    assert opened["ok"], opened
    return opened["data"]


def test_same_agent_in_two_workspaces_receives_only_each_authorized_context(runtime, tmp_path):
    deps, client, root, peers, operator, caller = runtime
    first = open_rest(runtime).json()["data"]
    other = tmp_path / "other-project"
    other.mkdir()
    second = add_endpoint(runtime, endpoint="other-workspace", root=str(other))
    assert first["workspace_id"] != second["workspace_id"]
    assert first["owning_agent_id"] == second["owning_agent_id"] == "worker"
    for index, (project, session) in enumerate(((root, first), (str(other), second))):
        created = tool(client, caller, "message_create", {"project_root": project, "from_agent_id": "caller",
            "target": {"strategy": "direct", "agent_id": "worker"}, "subject": "workspace isolation",
            "body": f"PRIVATE_WORKSPACE_{index}"})
        assert created["ok"], created
        op = created["data"]["runtime_operations"][0]
        stored = wait_status(runtime, op, "SENT_UNCONFIRMED")
        assert stored["runtime_session_id"] == session["session_id"]
        assert stored["workspace_id"] == session["workspace_id"]
        envelope = json.loads(stored["envelope"])
        assert envelope["workspace_id"] == session["workspace_id"]
    for index, peer in enumerate(peers):
        turns = [command for command in peer.sent if command.verb == "send_turn"]
        assert len(turns) == 1
        encoded = json.dumps(turns[0].payload)
        assert f"PRIVATE_WORKSPACE_{index}" in encoded
        assert f"PRIVATE_WORKSPACE_{1-index}" not in encoded
    closed = tool(client, operator, "harness_close", {"session_id": first["session_id"]})
    assert closed["ok"], closed
    wait_operation(runtime, closed["data"]["operation_id"], lambda row: row["state"] == "DONE")
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert deps.repos.sessions.get(uow, second["presence_session_id"]).status == "active"
        assert deps.repos.sessions.get(uow, first["presence_session_id"]).status == "closed"
        before = {sid: deps.repos.sessions.get(uow, sid).last_heartbeat_at
            for sid in (first["presence_session_id"], second["presence_session_id"])}
    peers[1].push_event(kind="output_delta", payload={"text": "remaining binding heartbeat"})
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            fresh = deps.repos.sessions.get(uow, second["presence_session_id"])
        if fresh.last_heartbeat_at > before[second["presence_session_id"]]:
            break
        time.sleep(.01)
    assert fresh.last_heartbeat_at > before[second["presence_session_id"]]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        closed_presence = deps.repos.sessions.get(uow, first["presence_session_id"])
        assert closed_presence.status == "closed"
        assert closed_presence.last_heartbeat_at == before[first["presence_session_id"]]
    for project, expected in ((root, []), (str(other), ["worker"])):
        routed = tool(client, caller, "message_create", {"project_root": project,
            "from_agent_id": "caller", "subject": "remaining workspace presence", "body": "binding eligibility",
            "target": {"strategy": "broadcast"}})
        assert routed["ok"] and routed["data"]["recipients"] == expected, routed
        assert routed["data"]["delivered_count"] == len(expected)
        assert len(routed["data"].get("runtime_operations", [])) == len(expected)
        if expected:
            with deps.connection_factory.unit_of_work(write=False) as uow:
                row = uow.connection.execute("SELECT workspace_id,runtime_session_id FROM delivery_outbox WHERE operation_id=?",
                    (routed["data"]["runtime_operations"][0],)).fetchone()
                assert row["workspace_id"] == second["workspace_id"] and row["runtime_session_id"] == second["session_id"]


@pytest.mark.parametrize("surface", ["rest", "mcp"])
def test_priority_change_does_not_retarget_steer_or_interrupt(runtime, surface):
    deps, client, root, peers, operator, _ = runtime
    headers = {"x-api-key": operator}
    first = open_rest(runtime).json()["data"]
    second = add_endpoint(runtime, endpoint="next-preferred", root=root, priority=-1)
    source = send_message(runtime, body="original operation")
    op = source["runtime_operations"][0]
    row = wait_status(runtime, op, "SENT_UNCONFIRMED")
    assert row["runtime_session_id"] == first["session_id"]
    changed = client.patch("/api/v1/harness/endpoints/next-preferred", headers=headers,
        json={"expected_revision": 1, "priority": 10})
    assert changed.status_code == 200, changed.text
    for verb in ("steer", "interrupt"):
        args = {"expected_operation_id": op}
        if verb == "steer":
            args["payload"] = {"text": "only the original turn"}
        if surface == "mcp":
            controlled = tool(client, operator, "harness_" + verb, {"session_id": first["session_id"], **args})
        else:
            response = client.post(f'/api/v1/harness/sessions/{first["session_id"]}/{verb}', headers=headers, json=args)
            assert response.status_code == 200, response.text
            controlled = response.json()
        assert controlled["ok"], controlled
        result = wait_operation(runtime, controlled["data"]["operation_id"], lambda r: r["state"] == "SENT_UNCONFIRMED")
        assert result["expected_operation_id"] == op
        assert result["session_id"] == first["session_id"]
    assert [command.verb for command in peers[0].sent] == ["send_turn", "steer", "interrupt"]
    assert not peers[1].sent
    newer = send_message(runtime, body="new selection uses new priority")
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert deps.runtime_dispatcher.repo.get(uow, op)["runtime_session_id"] == first["session_id"]
        assert deps.runtime_dispatcher.repo.get(uow, newer["runtime_operations"][0])["endpoint_id"] == second["endpoint_id"]
        assert uow.connection.execute("SELECT priority FROM agent_endpoints WHERE endpoint_id=?",
            (second["endpoint_id"],)).fetchone()[0] == 10
