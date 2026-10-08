"""Read-only binding discovery filters canonical history by current grants."""
import json

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_canonical_grant_regressions import mcp_helpers
from test_agent_recovery_isolation import create_agent
from okto_nexus.domain.base import iso_plus


@pytest.fixture
def discovery(connected_local):
    setup, binding, native = connected_local
    caller = create_agent(setup, "caller")
    setup[2].headers["host"] = "127.0.0.1:8000"
    return setup, binding, native, caller[3]["subject"]


def issue(discovery, endpoint=None):
    setup, binding, _, _ = discovery
    response = setup[2].post("/api/v1/harness/grants", headers=setup[3]["operator"], json=dict(
        actor_agent_id="caller", endpoint_id=endpoint or binding["endpoint_id"], actions=["discover"],
        max_executions=1, expires_at=iso_plus(setup[0].clock.now_iso(), 600)))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def read(discovery, **params):
    from test_pr34_remediation import tool
    setup, _, _, auth = discovery
    response = setup[2].get("/api/v1/harness/bindings", headers=auth, params=params)
    assert response.status_code == 200, response.text
    mcp = tool(setup[2], auth["Authorization"].removeprefix("Bearer "), "harness_list",
        dict(view="bindings", maintenance=params))
    assert mcp["ok"] and mcp["data"] == response.json()["data"], mcp
    return mcp["data"]


def second_retained_endpoint(discovery):
    # Discovery also reads retained canonical endpoint records that have no
    # currently live session. Creating this record must not spawn a harness.
    setup, binding, _, _ = discovery
    with setup[0].connection_factory.unit_of_work() as uow:
        row = dict(uow.connection.execute("SELECT * FROM agent_endpoints WHERE endpoint_id=?", (binding["endpoint_id"],)).fetchone())
        row["endpoint_id"] = "second-retained-canonical-endpoint"
        uow.connection.execute("INSERT INTO agent_endpoints(" + ",".join(row) + ") VALUES(" + ",".join("?" for _ in row) + ")", tuple(row.values()))
    issue(discovery, row["endpoint_id"])
    return row["endpoint_id"]


def test_discovery_groups_authorized_history_without_private_configuration(discovery):
    setup, binding, native, _ = discovery
    opened = admit(setup, binding, "discovery-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    issue(discovery)
    second = second_retained_endpoint(discovery)
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET capabilities=?,metadata=? WHERE agent_id='subject'",
            (json.dumps(dict(review=True)), json.dumps(dict(private="fixture-private-metadata"))))
        uow.connection.execute("UPDATE runtime_profiles SET secret_refs=?", ('{"FIXTURE_SECRET":"vault:private-ref"}',))
    data = read(discovery)
    assert len(data["agents"]) == 1
    agent = data["agents"][0]
    assert agent["agent_id"] == "subject" and agent["skill_names"] == ["review"]
    assert {r["endpoint_id"] for r in agent["endpoints"]} == {binding["endpoint_id"], second}
    endpoint = next(r for r in agent["endpoints"] if r["endpoint_id"] == binding["endpoint_id"])
    assert endpoint["sessions"][0]["session_id"] == opened["session_id"]
    assert endpoint["sessions"][0]["process_liveness"] == "not_probed"
    for private in (str(setup[-1]), "FIXTURE_SECRET", "private-ref", "fixture-private-metadata", "credential_binding", "notify_target"):
        assert private not in json.dumps(data)
    assert native.opens == 1 and not native.native.sent


def test_discovery_pages_only_visible_endpoint_ids(discovery):
    issue(discovery)
    second_retained_endpoint(discovery)
    first = read(discovery, limit=1)
    assert first["has_more"]
    identity = first["agents"][0]["endpoints"][0]["endpoint_id"]
    assert first["next_endpoint_id"] == identity
    second = read(discovery, limit=1, after_endpoint_id=identity)
    assert not second["has_more"]
    assert second["agents"][0]["endpoints"][0]["endpoint_id"] != identity
    assert discovery[2].opens == 0
    from test_pr34_remediation import tool
    denied = tool(discovery[0][2], discovery[3]["Authorization"].removeprefix("Bearer "),
        "harness_list", dict(view="bindings", maintenance=dict(limit=True)))
    assert denied["error"]["code"] == "VALIDATION_ERROR", denied


@pytest.mark.parametrize("change", ["expire", "scope", "credential", "profile", "inactive", "permission", "revoke"])
def test_discovery_rechecks_current_authority(discovery, change):
    setup, _, native, _ = discovery
    grant = issue(discovery)
    assert len(read(discovery)["agents"]) == 1
    mutations = dict(
        expire="UPDATE runtime_execution_grants SET expires_at='2000-01-01T00:00:00Z' WHERE actor_agent_id='caller'",
        scope="UPDATE agents SET comm_scope='{\"outbound\":{\"team\":[\"elsewhere\"]}}' WHERE agent_id='caller'",
        credential="UPDATE runtime_execution_grants SET credential_binding='obsolete' WHERE actor_agent_id='caller'",
        profile="UPDATE runtime_profiles SET revision=revision+1",
        inactive="UPDATE agents SET is_active=0 WHERE agent_id='subject'",
        permission="UPDATE agents SET permissions='{\"events\":{\"read\":false}}' WHERE agent_id='caller'")
    if change == "revoke":
        assert setup[2].delete("/api/v1/harness/grants/" + grant["grant_id"], headers=setup[3]["operator"]).status_code == 200
    else:
        with setup[0].connection_factory.unit_of_work() as uow:
            uow.connection.execute(mutations[change])
    assert read(discovery)["agents"] == []
    assert read(discovery, agent_id="missing")["agents"] == []
    assert native.opens == 0


def test_discovery_grant_does_not_authorize_execution_and_closed_history_stays_truthful(discovery):
    from test_pr34_remediation import tool
    setup, binding, native, auth = discovery
    issue(discovery)
    opened = admit(setup, binding, "discover-control-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    key = auth["Authorization"].removeprefix("Bearer ")
    denied = tool(setup[2], key, "harness_send", dict(session_id=opened["session_id"],
        payload=dict(text="Not authorized"), idempotency_key="discovery-cannot-send"))
    assert denied["error"]["code"] == "PERMISSION_DENIED", denied

    wait_receipt(setup, admit(setup, binding, "discover-control-close", "runtime.close",
        session_id=opened["session_id"]), stages=("SUCCEEDED",))
    session = read(discovery)["agents"][0]["endpoints"][0]["sessions"][0]
    assert session["lifecycle_state"] == "CLOSED" and not session["current_owner_ready_record"]
    assert session["process_liveness"] == "not_probed"
    assert native.opens == 1 and not native.native.sent
    setup[0].config.feature_harness_integrations = False
    denied = tool(setup[2], key, "harness_list", dict(view="bindings"))
    assert denied["error"]["code"] == "PERMISSION_DENIED", denied


def test_actual_tcp_mcp_discovery_and_copied_connect_share_the_existing_owner(discovery):
    import asyncio
    import socket
    import time
    import httpx
    import uvicorn
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    setup, binding, native, caller_auth = discovery
    _, app, client, headers, *_ = setup
    issue(discovery)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    address = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, lifespan="off", log_level="error"))
    async def serve():
        await server.serve(sockets=[sock])
    running = client.portal.start_task_soon(serve)
    async def query():
        async with httpx.AsyncClient(headers=headers["subject"], trust_env=False) as http:
            available = (await http.get(address + "/api/v1/connections/available")).json()["data"]
            async with streamable_http_client(address + "/mcp", http_client=http) as (reader, writer, _):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    response = await session.call_tool("harness_list", dict(view="connections", maintenance=dict(action="available")))
                    view = response.structuredContent or json.loads(response.content[0].text)
                    assert view["ok"] and view["data"] == available, view
                    endpoint = next(e for method in available["methods"] for e in method["endpoints"]
                        if e["endpoint_id"] == binding["endpoint_id"])
                    call = endpoint["connect"]
                    call["arguments"]["maintenance"]["idempotency_key"] = "tcp-copied-connect"
                    response = await session.call_tool(call["tool"], call["arguments"])
                    opened = response.structuredContent or json.loads(response.content[0].text)
                    assert opened["ok"], opened
                    repeated = await session.call_tool(call["tool"], call["arguments"])
                    replay = repeated.structuredContent or json.loads(repeated.content[0].text)
                    assert replay["data"]["operation_id"] == opened["data"]["operation_id"]
        return opened["data"]
    async def history():
        async with httpx.AsyncClient(headers=caller_auth, trust_env=False) as http:
            expected = (await http.get(address + "/api/v1/harness/bindings")).json()
            async with streamable_http_client(address + "/mcp", http_client=http) as (reader, writer, _):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    response = await session.call_tool("harness_list", dict(view="bindings"))
                    actual = response.structuredContent or json.loads(response.content[0].text)
                    assert actual == expected
                    assert actual["data"]["agents"][0]["endpoints"][0]["sessions"]
    try:
        until = time.monotonic() + 5
        while not server.started:
            assert time.monotonic() < until
            time.sleep(.01)
        opened = asyncio.run(asyncio.wait_for(query(), 20))
        wait_receipt(setup, opened)
        asyncio.run(asyncio.wait_for(history(), 20))
        assert native.opens == 1
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 1
            assert uow.connection.execute("SELECT COUNT(*) FROM harness_sessions").fetchone()[0] == 0
    finally:
        server.should_exit = True
        running.result(timeout=10)
        sock.close()
