"""Authorization precedes persisted operation results and idempotent replies."""
import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool, open_rest
from test_runtime_grants import issue
from test_runtime_commands import codex_session, wait_operation

runtime = runtime_fixture


def test_foreign_actor_cannot_reuse_command_key_or_inspect_persisted_result(runtime):
    deps, client, _, _, operator, caller = runtime
    sid = codex_session(runtime)
    body = {"payload": {"text": "private-operation-fixture"}, "idempotency_key": "shared-key-fixture"}
    admitted = tool(client, operator, "harness_send", {"session_id": sid, **body})
    assert admitted["ok"], admitted
    op = admitted["data"]["operation_id"]
    completed = wait_operation(runtime, op, lambda row: row["result_durable"])
    assert "private-operation-fixture" in completed["result"]["output_text"]
    # Positive control: the authorized actor can recover its durable reply.
    repeated = tool(client, operator, "harness_send", {"session_id": sid, **body})
    assert repeated["ok"] and repeated["data"]["operation_id"] == op
    rest = client.post(f"/api/v1/harness/sessions/{sid}/send", headers={"x-api-key": caller}, json=body)
    mcp = tool(client, caller, "harness_send", {"session_id": sid, **body})
    assert rest.status_code == 403 and not mcp["ok"]
    assert rest.json()["error"]["code"] == mcp["error"]["code"] == "PERMISSION_DENIED"
    rest_reads, mcp_reads = [], []
    for target in (op, "missing-operation-fixture"):
        response = client.get(f"/api/v1/harness/operations/{target}", headers={"x-api-key": caller})
        result = tool(client, caller, "harness_get", {"operation_id": target})
        assert response.status_code == 403 and not result["ok"]
        assert response.json()["error"]["code"] == result["error"]["code"] == "PERMISSION_DENIED"
        rest_reads.append(response.json())
        mcp_reads.append(result)
    assert rest_reads[0] == rest_reads[1], "operation existence must remain opaque"
    assert mcp_reads[0] == mcp_reads[1], "operation existence must remain opaque"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_commands").fetchone()[0] == 1
        assert uow.connection.execute("SELECT count(*) FROM runtime_results WHERE command_operation_id=?", (op,)).fetchone()[0] == 1


@pytest.mark.parametrize("verb", ["send", "steer", "interrupt", "close"])
def test_revoked_actor_cannot_recover_cached_control_reply(runtime, verb):
    deps, client, _, peers, operator, caller = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    grant = issue(runtime, ["send", "steer", "interrupt", "close", "read"])
    if verb in {"steer", "interrupt"}:
        initial = tool(client, operator, "harness_send", {"session_id": sid, "payload": {"text": "active fixture"}})
        assert initial["ok"], initial
        target = initial["data"]["operation_id"]
        wait_operation(runtime, target, lambda row: row["state"] == "SENT_UNCONFIRMED")
    args = {"idempotency_key": "cached-control-fixture"}
    if verb in {"send", "steer"}:
        args["payload"] = {"text": "authorized fixture"}
    if verb in {"steer", "interrupt"}:
        args["expected_operation_id"] = target
    admitted = tool(client, caller, "harness_" + verb, {"session_id": sid, **args})
    assert admitted["ok"], admitted
    op = admitted["data"]["operation_id"]
    wait_operation(runtime, op, lambda row: row["state"] == ("DONE" if verb == "close" else "SENT_UNCONFIRMED"))
    repeated = tool(client, caller, "harness_" + verb, {"session_id": sid, **args})
    assert repeated["ok"] and repeated["data"]["operation_id"] == op
    assert client.delete("/api/v1/harness/grants/" + grant["grant_id"], headers={"x-api-key": operator}).status_code == 200
    calls = list(peers[0].sent)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        count = uow.connection.execute("SELECT count(*) FROM runtime_commands").fetchone()[0]
    denied = tool(client, caller, "harness_" + verb, {"session_id": sid, **args})
    rest = client.post(f"/api/v1/harness/sessions/{sid}/{verb}", headers={"x-api-key": caller}, json=args)
    assert not denied["ok"] and denied["error"]["code"] == "PERMISSION_DENIED"
    assert rest.status_code == 403 and rest.json()["error"]["code"] == "PERMISSION_DENIED"
    assert not tool(client, caller, "harness_get", {"operation_id": op})["ok"]
    assert client.get(f"/api/v1/harness/operations/{op}", headers={"x-api-key": caller}).status_code == 403
    assert peers[0].sent == calls
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_commands").fetchone()[0] == count
