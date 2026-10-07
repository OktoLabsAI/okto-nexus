"""Authenticated conversational canonical input, without payload authority."""
import json

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool, wait_sent

runtime = runtime_fixture


def request(runtime, surface, sid, payload, key="canonical-fixture"):
    _, client, _, _, operator, _ = runtime
    arguments = {"session_id": sid, "payload": payload, "idempotency_key": key}
    if surface == "mcp":
        return tool(client, operator, "harness_send", arguments)
    response = client.post(f"/api/v1/harness/sessions/{sid}/send",
        headers={"x-api-key": operator}, json={k: v for k, v in arguments.items() if k != "session_id"})
    assert response.status_code in {200, 422}, response.text
    return {"ok": response.status_code == 200, **response.json()}










@pytest.mark.parametrize("surface", ["mcp", "rest"])
def test_canonical_command_uses_granted_actor_and_real_adapter_results(runtime, surface):
    from test_runtime_commands import codex_session, wait_operation
    from test_runtime_grants import issue
    deps, client, _, _, operator, caller = runtime
    sid = codex_session(runtime)
    issue(runtime, ["send", "read"], endpoint_id="endpoint-codex")
    payload = {"schema_version": 1, "content": [{"type": "text", "text": "CANONICAL_CALLER_RESULT"}]}
    args = {"payload": payload, "idempotency_key": "granted-canonical"}
    if surface == "mcp":
        admitted = tool(client, caller, "harness_send", {"session_id": sid, **args})
    else:
        response = client.post(f"/api/v1/harness/sessions/{sid}/send", headers={"x-api-key": caller}, json=args)
        assert response.status_code == 200, response.text
        admitted = response.json()
    assert admitted["ok"], admitted
    op = admitted["data"]["operation_id"]
    result = wait_operation(runtime, op, lambda row: row["result_durable"])
    output = result["result"]["output_text"]
    assert "CANONICAL_CALLER_RESULT" in output
    assert '"sender_agent_id": "caller"' in output
    assert '"recipient_agent_id": "worker"' in output
    assert op in output and result["external_acceptance"] == "harness_accepted"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT actor_agent_id FROM runtime_commands WHERE operation_id=?", (op,)).fetchone()[0] == "caller"
        assert uow.connection.execute("SELECT count(*) FROM runtime_results WHERE command_operation_id=?", (op,)).fetchone()[0] == 1
