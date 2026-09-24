"""Real restricted credentials and anonymous stdio never gain runtime authority."""
import asyncio
import json
import sys

from test_pr34_remediation import runtime as runtime_fixture, open_rest, tool, stdio_environment
from test_runtime_grants import issue
from test_poll_tokens import _issue_token

runtime = runtime_fixture


def test_valid_ept_can_monitor_but_cannot_reach_runtime_rest_or_mcp(runtime):
    deps, client, root, peers, _, _ = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    _, issued, _, _ = _issue_token(deps)
    headers = {"authorization": "Bearer " + issued["token"]}
    valid = client.get("/api/v1/events/cursor", headers=headers)
    assert valid.status_code == 200, valid.text
    assert client.get("/api/v1/inbox/count", headers=headers).status_code == 200
    requests = [("GET", f"/api/v1/harness/sessions/{sid}", None),
        ("GET", f"/api/v1/harness/sessions/{sid}/events", None),
        ("GET", "/api/v1/harness/endpoints", None),
        ("POST", "/api/v1/harness/sessions", {"agent_id": "worker", "kind": "pi",
            "endpoint_id": "endpoint-pi", "project_root": root})]
    requests.extend(("POST", f"/api/v1/harness/sessions/{sid}/{verb}", {"payload": {"text": "never"}})
        for verb in ("send", "steer", "interrupt", "close"))
    for method, path, body in requests:
        response = client.request(method, path, headers=headers, **({"json": body} if body else {}))
        assert response.status_code == 401, (path, response.text)
        assert response.json()["error"]["code"] == "AUTH_FAILED"
    response = client.post("/mcp/", headers=headers | {"Accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "harness_send", "arguments": {"session_id": sid, "payload": {"text": "never"}}}})
    assert response.status_code == 401, response.text
    assert len(peers) == 1 and not peers[0].sent
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute("SELECT 1 FROM runtime_commands").fetchone()
        assert uow.connection.execute("SELECT count(*) FROM harness_sessions").fetchone()[0] == 1


def test_read_only_runtime_grant_has_identical_control_denials_and_audit(runtime):
    deps, client, root, peers, _, caller = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    issue(runtime, ["read", "events"])
    assert tool(client, caller, "harness_get", {"session_id": sid})["ok"]
    assert client.get(f"/api/v1/harness/sessions/{sid}", headers={"x-api-key": caller}).status_code == 200
    opening = {"agent_id": "worker", "kind": "pi", "endpoint_id": "endpoint-pi", "project_root": root}
    assert not tool(client, caller, "harness_open", opening)["ok"]
    assert client.post("/api/v1/harness/sessions", headers={"x-api-key": caller}, json=opening).status_code == 403
    for verb in ("send", "steer", "interrupt", "close"):
        args = {"payload": {"text": "never"}} if verb in {"send", "steer"} else {}
        rest_errors = []
        for target in (sid, "foreign-missing"):
            mcp = tool(client, caller, "harness_" + verb, {"session_id": target, **args})
            rest = client.post(f"/api/v1/harness/sessions/{target}/{verb}", headers={"x-api-key": caller}, json=args)
            assert rest.status_code == 403, rest.text
            assert not mcp["ok"] and mcp["error"]["code"] == "PERMISSION_DENIED", mcp
            assert rest.json()["error"]["code"] == mcp["error"]["code"]
            rest_errors.append(rest.json())
        assert rest_errors[0] == rest_errors[1]
        known = tool(client, caller, "harness_" + verb, {"session_id": sid, **args})
        missing = tool(client, caller, "harness_" + verb, {"session_id": "foreign-missing", **args})
        assert known == missing
    assert len(peers) == 1 and not peers[0].sent
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute("SELECT 1 FROM runtime_commands").fetchone()
        for action in ("open", "send", "steer", "interrupt", "close"):
            assert uow.connection.execute("SELECT 1 FROM runtime_access_audit WHERE actor_agent_id='caller' "
                "AND action=? AND decision='deny'", (action,)).fetchone(), action


def test_anonymous_real_stdio_cannot_open_or_control_existing_runtime(runtime):
    deps, client, root, peers, operator, _ = runtime
    # Even a broken denial can only select this approved harmless local command;
    # no installed provider executable is available through this profile.
    changed = client.patch("/api/v1/harness/profiles/profile-pi", headers={"x-api-key": operator},
        json={"expected_revision": 1, "config": {"command": [sys.executable, "--mode", "rpc"]}})
    assert changed.status_code == 200, changed.text
    sid = open_rest(runtime).json()["data"]["session_id"]

    async def query():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        env = stdio_environment(runtime)
        env.pop("OKTO_NEXUS_API_KEY")
        params = StdioServerParameters(command=sys.executable,
            args=["-m", "okto_nexus.adapters.inbound.mcp.server", "--home", str(deps.config.home_dir),
                "--feature-harness-integrations", "true"], env=env)
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                calls = [("harness_open", {"agent_id": "worker", "kind": "pi", "endpoint_id": "endpoint-pi", "project_root": root})]
                calls.extend(("harness_" + verb, {"session_id": sid, **(
                    {"payload": {"text": "never"}} if verb in {"send", "steer"} else {})})
                    for verb in ("send", "steer", "interrupt", "close", "get"))
                for name, args in calls:
                    result = await session.call_tool(name, args)
                    data = result.structuredContent or json.loads(result.content[0].text)
                    assert not data["ok"] and data["error"]["code"] == "PERMISSION_DENIED", (name, data)

    asyncio.run(asyncio.wait_for(query(), timeout=30))
    assert len(peers) == 1 and not peers[0].sent
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM harness_sessions").fetchone()[0] == 1
        assert not uow.connection.execute("SELECT 1 FROM runtime_commands").fetchone()
