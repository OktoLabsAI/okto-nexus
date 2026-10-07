"""Monitoring credentials cannot admit or control canonical Core work."""
import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, wait_receipt
from test_canonical_grant_regressions import mcp_helpers, open_scoped


@pytest.mark.parametrize("credential", ["anonymous", "poll"])
def test_monitor_credentials_cannot_open_read_or_control_runtime(connected_local, monkeypatch, credential):
    from test_poll_tokens import _issue_token
    setup, binding, native, _, sid = open_scoped(connected_local)
    deps, _, client, headers, *_, root = setup
    # Simulate a network peer; loopback REST deliberately permits local UI
    # administration and is a different authorization contract.
    monkeypatch.setattr(client._transport, "client", ("192.0.2.10", 50000))
    auth = {}
    if credential == "poll":
        _, issued, _, _ = _issue_token(deps)
        auth = {"Authorization": "Bearer " + issued["token"]}
        assert client.get("/api/v1/events/cursor", headers=auth).status_code == 200
        assert client.get("/api/v1/inbox/count", headers=auth).status_code == 200
    opening = dict(agent_id="subject", kind="codex", endpoint_id=binding["endpoint_id"],
        project_root=str(root), idempotency_key="monitor-open")
    calls = [("POST", "/api/v1/harness/sessions", "harness_open", opening),
        ("GET", f"/api/v1/harness/sessions/{sid}", "harness_get", dict(session_id=sid)),
        ("GET", f"/api/v1/harness/sessions/{sid}/events", "harness_event_list", dict(session_id=sid))]
    for verb in ("send", "steer", "interrupt", "close"):
        args = dict(session_id=sid, idempotency_key="monitor-" + verb)
        if verb in ("send", "steer"):
            args["payload"] = dict(text="must not execute")
        calls.append(("POST", f"/api/v1/harness/sessions/{sid}/{verb}", "harness_" + verb, args))
    for method, path, name, args in calls:
        response = client.request(method, path, headers=auth,
            **({"json": {k: v for k, v in args.items() if k != "session_id"}} if method == "POST" else {}))
        assert response.status_code == 401, (path, response.text)
        assert response.json()["error"]["code"] == "AUTH_FAILED"
        response = client.post("/mcp/", headers=auth | {"Accept": "application/json, text/event-stream"},
            json=dict(jsonrpc="2.0", id=1, method="tools/call", params=dict(name=name, arguments=args)))
        assert response.status_code == 401, response.text
    assert native.opens == 1 and not native.native.sent and not native.native.stopped
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 1


def test_read_only_grant_never_grants_control_on_rest_or_mcp(connected_local):
    from test_pr34_remediation import tool
    setup, binding, native, _, sid = open_scoped(connected_local)
    deps, _, client, headers, *_, root = setup
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_execution_grants SET actions='[\"read\",\"events\",\"discover\"]'")
    key = headers["subject"]["Authorization"].removeprefix("Bearer ")
    assert tool(client, key, "harness_get", dict(session_id=sid))["ok"]
    assert client.get(f"/api/v1/harness/sessions/{sid}", headers=headers["subject"]).status_code == 200
    opening = dict(agent_id="subject", kind="codex", endpoint_id=binding["endpoint_id"],
        project_root=str(root), idempotency_key="read-only-open")
    assert not tool(client, key, "harness_open", opening)["ok"]
    assert client.post("/api/v1/harness/sessions", headers=headers["subject"], json=opening).status_code == 403
    for verb in ("send", "steer", "interrupt", "close"):
        body = dict(idempotency_key="read-only-" + verb)
        if verb in ("send", "steer"):
            body["payload"] = dict(text="must not execute")
        rest_denials, mcp_denials = [], []
        for target in (sid, "missing-private-session"):
            result = tool(client, key, "harness_" + verb, dict(session_id=target, **body))
            response = client.post(f"/api/v1/harness/sessions/{target}/{verb}",
                headers=headers["subject"], json=body)
            assert response.status_code == 403, response.text
            assert result["error"]["code"] == "PERMISSION_DENIED", result
            rest_denials.append(response.json())
            mcp_denials.append(result)
        assert rest_denials[0] == rest_denials[1]
        assert mcp_denials[0] == mcp_denials[1]
    assert native.opens == 1 and not native.native.sent and not native.native.stopped
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 1
        for action in ("open", "send", "steer", "interrupt", "close"):
            assert uow.connection.execute("SELECT 1 FROM runtime_access_audit WHERE actor_agent_id='subject' "
                "AND action=? AND decision='deny'", (action,)).fetchone(), action
