"""Fresh disabled stores preserve actual stdio/HTTP MCP and REST baseline."""
import asyncio
import json
import sys

import pytest

from test_pr34_remediation import runtime as runtime_fixture, mcp_call, stdio_environment

runtime = runtime_fixture


@pytest.mark.parametrize("runtime", [False], indirect=True)
def test_disabled_stdio_http_and_rest_do_not_start_implicit_runtime(runtime):
    deps, client, root, peers, operator, _ = runtime
    http_tools = mcp_call(client, operator, "tools/list", {})["tools"]
    http_resources = mcp_call(client, operator, "resources/list", {})["resources"]
    assert len(http_tools) == 43 and not any(t["name"].startswith("harness_") for t in http_tools)

    async def query_stdio():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params = StdioServerParameters(command=sys.executable,
            args=["-m", "okto_nexus.adapters.inbound.mcp.server", "--home", str(deps.config.home_dir),
                "--feature-harness-integrations", "false"], env=stdio_environment(runtime))
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                resources = (await session.list_resources()).resources
                assert sorted(t.name for t in tools) == sorted(t["name"] for t in http_tools)
                assert sorted(str(r.uri) for r in resources) == sorted(r["uri"] for r in http_resources)
                result = await session.call_tool("message_create", {"project_root": root,
                    "from_agent_id": "caller", "subject": "disabled baseline", "body": "logical inbox still works",
                    "target": {"strategy": "direct", "agent_id": "worker"}})
                body = result.structuredContent or json.loads(result.content[0].text)
                assert body["ok"] and body["data"]["delivered_count"] == 1, body
                assert not body["data"].get("runtime_operations")
    asyncio.run(asyncio.wait_for(query_stdio(), timeout=30))
    routes = [("GET", "/kinds", None), ("GET", "/sessions/missing", None),
        ("GET", "/sessions/missing/events", None),
        ("POST", "/sessions", {"agent_id": "worker", "kind": "pi", "project_root": root})]
    routes += [("POST", "/sessions/missing/" + verb, {"payload": {"text": "unused"}} if verb in {"send", "steer"} else {})
        for verb in ("send", "steer", "interrupt", "close")]
    for method, suffix, body in routes:
        response = client.request(method, "/api/v1/harness" + suffix,
            headers={"x-api-key": operator}, **({"json": body} if body is not None else {}))
        assert response.status_code == 403, (suffix, response.text)
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"
    assert peers == []
    assert getattr(deps, "runtime_dispatcher", None) is None
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM message_deliveries").fetchone()[0] == 1
        for table in ("harness_sessions", "runtime_commands", "delivery_outbox"):
            assert uow.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
