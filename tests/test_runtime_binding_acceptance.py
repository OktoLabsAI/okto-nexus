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
