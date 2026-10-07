"""Foreign readers cannot enumerate captured canonical runtime evidence."""
import json

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, wait_receipt
from test_canonical_grant_regressions import mcp_helpers, open_scoped, invoke_command
from test_canonical_result_publication import emit
from test_agent_recovery_isolation import create_agent


def test_private_session_replay_results_and_listing_hide_foreign_evidence(connected_local, monkeypatch):
    from test_pr34_remediation import tool
    setup, _, native, _, sid = open_scoped(connected_local)
    deps, _, client, headers, *_, root = setup
    foreign = create_agent(setup, "foreign")[3]["subject"]
    foreign_key = foreign["Authorization"].removeprefix("Bearer ")
    subject_key = headers["subject"]["Authorization"].removeprefix("Bearer ")
    marker = "private-canonical-evidence"
    sent = invoke_command(setup, monkeypatch, "rest", sid,
        dict(payload=dict(text=marker), idempotency_key="private-history"))
    assert sent["ok"], sent
    operation = sent["data"]["operation_id"]
    wait_receipt(setup, sent["data"])
    emit(setup, native, dict(operation_id=operation), marker)
    read = tool(client, subject_key, "harness_get", dict(operation_id=operation))
    assert read["ok"] and marker in json.dumps(read), read
    replay = tool(client, subject_key, "harness_event_list", dict(session_id=sid))
    assert replay["ok"] and marker in json.dumps(replay), replay
    missing_stream = client.get(f"/api/v1/harness/sessions/{sid}/events", headers=headers["subject"],
        params=dict(stream_epoch="missing-stream"))
    assert missing_stream.status_code == 404, missing_stream.text
    missing_stream_mcp = tool(client, subject_key, "harness_event_list",
        dict(session_id=sid, stream_epoch="missing-stream"))
    assert missing_stream_mcp["error"]["code"] == "NOT_FOUND"
    for verb, suffix in (("harness_get", ""), ("harness_event_list", "/events")):
        rest_denials, mcp_denials = [], []
        for target in (sid, "missing-private-session"):
            response = client.get(f"/api/v1/harness/sessions/{target}{suffix}", headers=foreign)
            denied = tool(client, foreign_key, verb, dict(session_id=target))
            assert response.status_code == 403, response.text
            assert not denied["ok"] and denied["error"]["code"] == "PERMISSION_DENIED", denied
            rest_denials.append(response.json())
            mcp_denials.append(denied)
        assert rest_denials[0] == rest_denials[1]
        assert mcp_denials[0] == mcp_denials[1]
        assert str(root) not in json.dumps(rest_denials + mcp_denials)
        assert marker not in json.dumps(rest_denials + mcp_denials)
    for view in ("endpoints", "profiles", "diagnostics"):
        response = client.get("/api/v1/harness/" + view, headers=foreign)
        denied = tool(client, foreign_key, "harness_list", dict(view=view))
        assert response.status_code == 403 and not denied["ok"], (response.text, denied)
        assert str(root) not in json.dumps([response.json(), denied])
    operation_denials = []
    for target in (operation, "missing-private-operation"):
        response = client.get("/api/v1/harness/operations/" + target, headers=foreign)
        denied = tool(client, foreign_key, "harness_get", dict(operation_id=target))
        assert response.status_code == 403 and not denied["ok"], (response.text, denied)
        assert marker not in json.dumps([response.json(), denied])
        operation_denials.append((response.json(), denied))
    assert operation_denials[0] == operation_denials[1]
    rest = client.get("/api/v1/harness/bindings", headers=foreign)
    mcp = tool(client, foreign_key, "harness_list", dict(view="bindings"))
    assert rest.status_code == 200 and mcp["ok"]
    assert rest.json()["data"] == mcp["data"] and not mcp["data"]["agents"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 1
    assert len(native.native.sent) == 1
