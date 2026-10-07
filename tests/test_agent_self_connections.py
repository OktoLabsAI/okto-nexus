"""Authenticated self discovery/opening through actual HTTP/MCP and owner proxy."""
import asyncio
import json
import httpx

import pytest
from test_pr34_remediation import runtime as runtime_fixture
from test_pr34_remediation import tool

from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.domain.base import iso_plus

runtime = runtime_fixture


def worker_key(runtime):
    deps = runtime[0]
    with deps.connection_factory.unit_of_work() as uow:
        return AgentKeyAuthService(deps.repos.agents, deps.clock).issue_key(uow, agent_id="worker")


def grant(runtime, actor="worker", endpoint="endpoint-pi"):
    deps, client, _, _, operator, _ = runtime
    result = client.post('/api/v1/harness/grants', headers={'x-api-key': operator}, json={
        'actor_agent_id': actor, 'endpoint_id': endpoint, 'actions': ['open', 'discover'],
        'expires_at': iso_plus(deps.clock.now_iso(), 600)})
    assert result.status_code == 200
    return result.json()['data']['grant_id']


def available(runtime, key):
    result = tool(runtime[1], key, 'harness_list', {'view': 'connections', 'maintenance': {'action': 'available'}})
    assert result['ok'], result
    return result['data']






def test_actual_http_mcp_self_discovery_and_connect_use_existing_serve_owner(runtime):
    _, client, _, peers, _, _ = runtime
    key = worker_key(runtime)
    grant(runtime)

    async def run():
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        async with httpx.AsyncClient(headers={"x-api-key": key}, trust_env=False) as http:
            async with streamable_http_client(str(client.base_url).rstrip("/") + "/mcp",
                                               http_client=http) as (reader, writer, _):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    response = await session.call_tool("harness_list", {
                        "view": "connections", "maintenance": {"action": "available"}})
                    result = response.structuredContent or json.loads(response.content[0].text)
                    assert result["ok"] and result["data"]["agent_id"] == "worker"
                    for _ in range(2):
                        response = await session.call_tool("harness_list", {"view": "connections",
                            "maintenance": {"action": "connect", "endpoint_id": "endpoint-pi",
                                            "idempotency_key": "http-self-fixture"}})
                        result = response.structuredContent or json.loads(response.content[0].text)
                        assert result["ok"], result
                    assert result["data"]["reused"]
    asyncio.run(asyncio.wait_for(run(), timeout=45))
    assert len(peers) == 1 and peers[0].session.owning_agent_id == "worker"






@pytest.mark.parametrize("runtime", ["additional"], indirect=True)
def test_registered_adapter_uses_self_discovery_and_connect(runtime):
    key = worker_key(runtime)
    grant(runtime, endpoint='endpoint-fixture.additional.v1')
    item = next(m for m in available(runtime, key)['methods'] if m['method'] == 'fixture.additional.v1')
    assert item['available']
    arguments = item['endpoints'][0]['connect']['arguments']
    arguments['maintenance']['idempotency_key'] = 'additional-adapter-self'
    result = tool(runtime[1], key, 'harness_list', arguments)
    assert result['ok'], result
    assert result['data']['owning_agent_id'] == 'worker'
    assert len(runtime[3]) == 1
