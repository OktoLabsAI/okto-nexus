"""Foreign authenticated actors cannot enumerate private runtime evidence."""
import json

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_commands import codex_session, wait_operation

runtime = runtime_fixture


def test_private_session_replay_results_and_endpoint_listing_have_no_foreign_audience(runtime):
    deps, client, root, _, operator, caller = runtime
    sid = codex_session(runtime)
    marker = "private-audience-fixture"
    admitted = tool(client, operator, "harness_send", {"session_id": sid, "payload": {"text": marker}})
    assert admitted["ok"], admitted
    op = admitted["data"]["operation_id"]
    result = wait_operation(runtime, op, lambda row: row["result_durable"])
    assert marker in result["result"]["output_text"]
    # Prove nonempty private replay exists before attempting the foreign read.
    replay = tool(client, operator, "harness_event_list", {"session_id": sid})
    assert replay["ok"] and marker in json.dumps(replay), replay
    for verb, suffix in (("harness_get", ""), ("harness_event_list", "/events")):
        denied_rest, denied_mcp = [], []
        for target in (sid, "missing-session-fixture"):
            response = client.get(f"/api/v1/harness/sessions/{target}{suffix}", headers={"x-api-key": caller})
            denied = tool(client, caller, verb, {"session_id": target})
            assert response.status_code == 403, response.text
            assert not denied["ok"] and denied["error"]["code"] == "PERMISSION_DENIED", denied
            denied_rest.append(response.json())
            denied_mcp.append(denied)
        assert denied_rest[0] == denied_rest[1]
        assert denied_mcp[0] == denied_mcp[1]
        assert root not in json.dumps(denied_rest + denied_mcp)
        assert marker not in json.dumps(denied_rest + denied_mcp)
    for view in ("endpoints", "profiles", "diagnostics"):
        response = client.get("/api/v1/harness/" + view, headers={"x-api-key": caller})
        denied = tool(client, caller, "harness_list", {"view": view})
        assert response.status_code == 403 and not denied["ok"], (response.text, denied)
        assert root not in json.dumps([response.json(), denied])
    for target in (op, "missing-operation-fixture"):
        response = client.get(f"/api/v1/harness/operations/{target}", headers={"x-api-key": caller})
        denied = tool(client, caller, "harness_get", {"operation_id": target})
        assert response.status_code == 403 and not denied["ok"]
        assert marker not in json.dumps([response.json(), denied])
    # Safe discovery deliberately returns an empty projection, not private IDs.
    rest = client.get("/api/v1/harness/bindings", headers={"x-api-key": caller})
    mcp = tool(client, caller, "harness_list", {"view": "bindings"})
    assert rest.status_code == 200 and mcp["ok"]
    assert rest.json()["data"] == mcp["data"] and not mcp["data"]["agents"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_commands").fetchone()[0] == 1
