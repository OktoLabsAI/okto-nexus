"""Safe runtime discovery through authenticated production HTTP/MCP."""
import json
import asyncio
import sys

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool, open_rest
from test_runtime_grants import issue
from test_runtime_commands import wait_close_result
from okto_nexus.domain.base import iso_plus

runtime = runtime_fixture


def discover(runtime, key=None, **parameters):
    return tool(runtime[1], key or runtime[5], "harness_list", {"view": "bindings", "maintenance": parameters})


def test_discovery_groups_authorized_endpoints_under_one_agent_and_redacts_config(runtime, monkeypatch):
    monkeypatch.setenv("FIXTURE_SECRET", "fixture-only-value")
    deps, client, root, _, operator, caller = runtime
    headers = {"x-api-key": operator}
    assert client.patch("/api/v1/harness/profiles/profile-pi", headers=headers, json={"expected_revision": 1,
        "config": {"env": {"PI_CODING_AGENT_DIR": root}}, "secret_refs": {"FIXTURE_KEY": "env:FIXTURE_SECRET"}}).status_code == 200
    for adapter in ("pi", "codex"):
        issue(runtime, ["discover"], endpoint_id="endpoint-" + adapter)
        opened = client.post("/api/v1/harness/sessions", headers=headers, json={"agent_id": "worker", "kind": adapter,
            "project_root": root, "endpoint_id": "endpoint-" + adapter, "metadata": {"private": "fixture-private-metadata"}})
        assert opened.status_code == 200, opened.text
    result = discover(runtime)
    assert result["ok"], result
    rest = client.get("/api/v1/harness/bindings", headers={"x-api-key": caller})
    assert rest.status_code == 200 and rest.json()["data"] == result["data"], rest.text
    agents = result["data"]["agents"]
    assert len(agents) == 1 and agents[0]["agent_id"] == "worker"
    assert agents[0]["skill_names"] == ["review"]
    endpoints = agents[0]["endpoints"]
    assert {e["endpoint_id"] for e in endpoints} == {"endpoint-pi", "endpoint-codex"}
    assert all(len(e["sessions"]) == 1 for e in endpoints)
    assert all(e["sessions"][0]["current_owner_ready_record"] for e in endpoints)
    assert all(e["capability_verification"] == "not_probed" for e in endpoints)
    rendered = json.dumps(result["data"])
    for private in (root, "FIXTURE_SECRET", "FIXTURE_KEY", "fixture-private-metadata", "credential_binding", "notify_target"):
        assert private not in rendered
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert deps.repos.agents.get(uow, "worker").capabilities == {"review": True}


def test_discovery_grant_never_grants_control_and_revocation_removes_projection(runtime):
    _, client, _, peers, operator, caller = runtime
    assert discover(runtime)["data"]["agents"] == []
    grant = issue(runtime, ["discover"])
    session = open_rest(runtime).json()["data"]["session_id"]
    result = discover(runtime)
    assert result["ok"] and len(result["data"]["agents"]) == 1, result
    denied = tool(client, caller, "harness_send", {"session_id": session, "payload": {"text": "not authorized"}})
    assert not denied["ok"] and not peers[0].sent
    assert client.delete("/api/v1/harness/grants/" + grant["grant_id"], headers={"x-api-key": operator}).status_code == 200
    assert discover(runtime)["data"]["agents"] == []
    assert discover(runtime, agent_id="nonexistent")["data"]["agents"] == []


def test_discovery_rechecks_policy_and_cached_flag_and_marks_closed_session(runtime):
    deps, client, _, _, operator, caller = runtime
    issue(runtime, ["discover"])
    session = open_rest(runtime).json()["data"]["session_id"]
    closed = tool(client, operator, "harness_close", {"session_id": session})
    wait_close_result(client, operator, closed)
    projection = discover(runtime)["data"]["agents"][0]["endpoints"][0]["sessions"][0]
    assert not projection["current_owner_ready_record"]
    assert projection["process_liveness"] == "not_probed"
    assert client.patch("/api/v1/agents/caller", headers={"x-api-key": operator}, json={
        "permissions": {"events": {"read": False}}}).status_code == 200
    assert discover(runtime)["data"]["agents"] == []
    deps.config.feature_harness_integrations = False
    denied = discover(runtime, key=operator)
    assert not denied["ok"] and denied["error"]["code"] == "PERMISSION_DENIED", denied


def test_discovery_paginates_visible_endpoints_without_private_cursor(runtime):
    for adapter in ("pi", "codex"):
        issue(runtime, ["discover"], endpoint_id="endpoint-" + adapter)
    first = discover(runtime, limit=1)
    assert first["ok"], first
    assert first["data"]["has_more"]
    identity = first["data"]["agents"][0]["endpoints"][0]["endpoint_id"]
    assert first["data"]["next_endpoint_id"] == identity
    second = discover(runtime, limit=1, after_endpoint_id=identity)
    assert second["ok"] and not second["data"]["has_more"], second
    assert second["data"]["agents"][0]["endpoints"][0]["endpoint_id"] != identity
    denied = discover(runtime, limit=True)
    assert not denied["ok"] and denied["error"]["code"] == "VALIDATION_ERROR", denied


@pytest.mark.parametrize("change", ["expire", "scope", "credential", "profile", "inactive"])
def test_discovery_revalidates_current_authority(runtime, change):
    deps, client, _, _, _, caller = runtime
    issue(runtime, ["discover"])
    assert len(discover(runtime)["data"]["agents"]) == 1
    with deps.connection_factory.unit_of_work() as uow:
        if change == "expire":
            uow.connection.execute("UPDATE runtime_execution_grants SET expires_at=?", (iso_plus(deps.clock.now_iso(), -1),))
        elif change == "scope":
            uow.connection.execute("UPDATE agents SET comm_scope=? WHERE agent_id='caller'", ('{"outbound":{"team":["elsewhere"]}}',))
        elif change == "credential":
            uow.connection.execute("UPDATE runtime_execution_grants SET credential_binding='obsolete'")
        elif change == "profile":
            uow.connection.execute("UPDATE runtime_profiles SET revision=revision+1 WHERE profile_id='profile-pi'")
        else:
            uow.connection.execute("UPDATE agents SET is_active=0 WHERE agent_id='worker'")
    assert discover(runtime)["data"]["agents"] == []
    assert client.get("/api/v1/harness/bindings", headers={"x-api-key": caller}).json()["data"]["agents"] == []


def test_discovery_internal_payload_identity_cannot_authenticate(runtime):
    from okto_nexus.application.runtime_discovery import RuntimeDiscoveryService
    from okto_nexus.adapters.inbound.mcp.tools.harness import build_access_service
    from okto_nexus.domain.runtime_context import RuntimeRequestContext
    from okto_nexus.errors import OktoNexusError
    service = RuntimeDiscoveryService(access=build_access_service(runtime[0]))
    for context in (RuntimeRequestContext("operator", "payload"),
                    RuntimeRequestContext("caller", "agent_key", credential_binding="obsolete")):
        with pytest.raises(OktoNexusError, match="not authorized"):
            service.list(context)


def test_discovery_authenticated_stdio_shares_persisted_http_projection(runtime):
    from test_pr34_remediation import stdio_environment
    deps, client, _, _, _, caller = runtime
    issue(runtime, ["discover"])
    open_rest(runtime)
    expected = client.get("/api/v1/harness/bindings", headers={"x-api-key": caller}).json()

    async def query():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params = StdioServerParameters(command=sys.executable,
            args=["-m", "okto_nexus.adapters.inbound.mcp.server", "--home", str(deps.config.home_dir),
                  "--feature-harness-integrations", "true"], env=stdio_environment(runtime))
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                response = await session.call_tool("harness_list", {"view": "bindings"})
                assert (response.structuredContent or json.loads(response.content[0].text)) == expected
    asyncio.run(asyncio.wait_for(query(), timeout=30))


def test_discovery_preserves_partial_attach_capabilities_without_opening_peer(runtime):
    deps, _, _, peers, _, _ = runtime
    deps.config.feature_harness_attach = True
    for adapter in ("codex", "claude_code.attach"):
        issue(runtime, ["discover"], endpoint_id="endpoint-" + adapter)
    result = discover(runtime)
    assert result["ok"], result
    bindings = {item["adapter_id"]: item for item in result["data"]["agents"][0]["endpoints"]}
    assert bindings["codex"]["declared_capabilities"]["correlated_results"]
    partial = bindings["claude_code.attach"]["declared_capabilities"]
    assert partial["conversation"]
    assert not any(partial[key] for key in ("events", "managed_work", "interrupt", "correlated_results", "native_deduplication"))
    assert peers == []
    deps.config.feature_harness_attach = False
    assert [e["adapter_id"] for e in discover(runtime)["data"]["agents"][0]["endpoints"]] == ["codex"]
