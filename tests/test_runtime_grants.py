"""P04: one production composition, real HTTP/MCP, synthetic external peer."""
import asyncio
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from okto_nexus.domain.base import iso_plus
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError
from okto_nexus.adapters.inbound.mcp.tools.harness import build_access_service
from test_pr34_remediation import open_rest, tool

pytest_plugins = ["test_pr34_remediation"]


def issue(runtime, actions, **extra):
    deps, client, _, _, operator, _ = runtime
    result = client.post("/api/v1/harness/grants", headers={"x-api-key": operator}, json={
        "actor_agent_id": "caller", "endpoint_id": "endpoint-pi", "actions": actions,
        "expires_at": iso_plus(deps.clock.now_iso(), 3600), **extra})
    assert result.status_code == 200, result.text
    return result.json()["data"]


def test_p04_grant_allows_same_scoped_action_in_rest_and_mcp(runtime):
    _, client, _, peers, _, caller = runtime
    session = open_rest(runtime).json()["data"]["session_id"]
    issue(runtime, ["read", "send"], max_executions=2)
    assert client.get(f"/api/v1/harness/sessions/{session}", headers={"x-api-key": caller}).status_code == 200
    assert tool(client, caller, "harness_get", {"session_id": session})["ok"]
    assert client.post(f"/api/v1/harness/sessions/{session}/send", headers={"x-api-key": caller},
                       json={"payload": {"text": "first fixture"}}).status_code == 200
    assert tool(client, caller, "harness_send", {"session_id": session, "payload": {"text": "second fixture"}})["ok"]
    assert len(peers[0].sent) == 2
    assert not tool(client, caller, "harness_send", {"session_id": session, "payload": {"text": "budget spent"}})["ok"]
    assert not tool(client, caller, "harness_interrupt", {"session_id": session})["ok"]
    assert client.get("/api/v1/harness/endpoints", headers={"x-api-key": caller}).status_code == 403


def test_p04_grant_open_requires_explicit_scoped_binding(runtime):
    _, client, root, peers, _, caller = runtime
    issue(runtime, ["open"])
    base = {"agent_id": "worker", "kind": "pi", "project_root": root}
    assert client.post("/api/v1/harness/sessions", headers={"x-api-key": caller}, json=base).status_code == 403
    assert peers == []
    result = tool(client, caller, "harness_open", base | {"endpoint_id": "endpoint-pi"})
    assert result["ok"], result
    assert len(peers) == 1


@pytest.mark.parametrize("change", ["revoke", "expire", "permissions", "scope", "credential", "profile"])
def test_p04_authority_is_revalidated_before_send(runtime, change):
    deps, client, _, peers, operator, caller = runtime
    session = open_rest(runtime).json()["data"]["session_id"]
    grant = issue(runtime, ["send", "read"])
    if change == "revoke":
        assert client.delete("/api/v1/harness/grants/" + grant["grant_id"], headers={"x-api-key": operator}).status_code == 200
    else:
        # Inject state changes through the same persistence used by administration.
        with deps.connection_factory.unit_of_work() as uow:
            if change == "expire":
                uow.connection.execute("UPDATE runtime_execution_grants SET expires_at=?", (iso_plus(deps.clock.now_iso(), -1),))
            elif change == "permissions":
                uow.connection.execute("UPDATE agents SET permissions=? WHERE agent_id='caller'", ('{"messages":{"send_direct":false}}',))
            elif change == "scope":
                uow.connection.execute("UPDATE agents SET comm_scope=? WHERE agent_id='caller'", ('{"outbound":{"team":["elsewhere"]}}',))
            elif change == "credential":
                uow.connection.execute("UPDATE runtime_execution_grants SET credential_binding='different-key-hash'")
            else:
                uow.connection.execute("UPDATE runtime_profiles SET revision=revision+1 WHERE profile_id='profile-pi'")
    result = tool(client, caller, "harness_send", {"session_id": session, "payload": {"text": "never sent"}})
    assert result["error"]["code"] == "PERMISSION_DENIED", result
    assert client.post(f"/api/v1/harness/sessions/{session}/send", headers={"x-api-key": caller},
                       json={"payload": {"text": "never sent"}}).status_code == 403
    assert peers[0].sent == []
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM runtime_access_audit WHERE decision='deny'").fetchone()[0] >= 2


def test_p04_internal_missing_authentication_cannot_impersonate_operator(runtime):
    deps, _, _, peers, _, _ = runtime
    with pytest.raises(OktoNexusError):
        build_access_service(deps).authorize(RuntimeRequestContext("operator", "payload"))
    assert peers == []


def test_p04_native_options_and_payload_identity_are_rejected(runtime):
    _, client, _, peers, operator, _ = runtime
    session = open_rest(runtime).json()["data"]["session_id"]
    for payload in ({"text": "hi", "actor_agent_id": "operator"}, {"text": "hi", "sandbox": "danger-full-access"}):
        result = tool(client, operator, "harness_send", {"session_id": session, "payload": payload})
        assert result["error"]["code"] == "VALIDATION_ERROR"
    assert peers[0].sent == []


def test_p04_authenticated_stdio_reuses_grant_policy_and_durable_resource(runtime):
    deps, _, _, _, _, caller = runtime
    session = open_rest(runtime).json()["data"]["session_id"]
    issue(runtime, ["read"])

    async def query():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from okto_nexus.adapters.outbound.harness.environment import child_environment

        # Only the disposable fixture caller key reaches this Nexus test process.
        env = child_environment(os.environ)
        env["OKTO_NEXUS_API_KEY"] = caller
        params = StdioServerParameters(command=sys.executable,
            args=["-m", "okto_nexus.adapters.inbound.mcp.server", "--home", str(deps.config.home_dir),
                  "--feature-harness-integrations", "true"], env=env)
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()
                result = await client.call_tool("harness_get", {"session_id": session})
                data = result.structuredContent or json.loads(result.content[0].text)
                assert data["ok"], data
                result = await client.call_tool("harness_close", {"session_id": session})
                data = result.structuredContent or json.loads(result.content[0].text)
                assert data["error"]["code"] == "PERMISSION_DENIED"

    asyncio.run(asyncio.wait_for(query(), timeout=30))


def test_p04_concurrent_grant_budget_has_one_admitted_send(runtime):
    _, client, _, peers, _, caller = runtime
    session = open_rest(runtime).json()["data"]["session_id"]
    issue(runtime, ["send"], max_executions=1)

    def send(index):
        return client.post(f"/api/v1/harness/sessions/{session}/send", headers={"x-api-key": caller},
                           json={"payload": {"text": f"fixture {index}"}}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(send, [1, 2])) == [200, 403]
    assert len(peers[0].sent) == 1


def test_p04_wrong_endpoint_is_opaque_and_internal_control_is_authorized(runtime):
    deps, client, _, peers, _, caller = runtime
    session = open_rest(runtime).json()["data"]["session_id"]
    issue(runtime, ["read", "send"], endpoint_id="endpoint-codex")
    known = tool(client, caller, "harness_get", {"session_id": session})
    unknown = tool(client, caller, "harness_get", {"session_id": "nonexistent"})
    assert known == unknown
    assert known["error"]["code"] == "PERMISSION_DENIED"
    from okto_nexus.application.runtime_control import RuntimeControlService
    with pytest.raises(OktoNexusError):
        RuntimeControlService(access=build_access_service(deps), supervisor=deps.harness_supervisor).send(
            RuntimeRequestContext("operator", "payload"), session_id=session,
            verb="send_turn", payload={"text": "never sent"})
    assert peers[0].sent == []
