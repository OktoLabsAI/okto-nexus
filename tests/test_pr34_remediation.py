"""Behavior-first PR34 regressions. No real providers or personal stores.

The HTTP fixture runs the production app on a real socket with its actual
authentication middleware and MCP mount. Only the external peer is synthetic.
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
from dataclasses import asdict
from pathlib import Path

import httpx
import pytest
import uvicorn

from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key
from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.inbound.mcp.tools import harness
from okto_nexus.application.auth import AgentKeyAuthService
from test_harness_tools import FakeConnector


@pytest.fixture
def runtime(tmp_path, request):
    # Some process fixtures invoke __wrapped__ directly with these two args.
    with pytest.MonkeyPatch.context() as monkeypatch:
        yield from _runtime(tmp_path, request, monkeypatch)


def _runtime(tmp_path, request, monkeypatch):
    # These legacy HTTP tests use synthetic peers. Do not scan the developer's
    # real installations during each production-app startup.
    from types import SimpleNamespace
    from okto_nexus.bootstrap import embedded_inventory
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates',
                        lambda **_: SimpleNamespace(candidates=()))
    root = tmp_path / "project"
    root.mkdir()
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    deps.config.feature_harness_integrations = getattr(request, "param", True)
    if getattr(request, "param", None) == "stored_runtime":
        # Preserve the declared default so this is a stored setting, not an
        # in-memory explicit override that would pin the opposite value.
        deps.config.feature_harness_integrations = True
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("INSERT INTO settings(key,value,updated_at) VALUES(?,?,?)",
                ("feature_harness_integrations", "true", deps.clock.now_iso()))
    if getattr(request, "param", None) == "strict":
        deps.config.trust_mode = "strict"
    peers = []

    def factory(kind):
        def build(**kwargs):
            from test_harness_tools import _ATTACH_CAPS
            peer = FakeConnector(kind=kind, capabilities=(
                _ATTACH_CAPS if kwargs.get("substrate") == "attach" else None))
            peers.append(peer)
            return peer
        return build

    if getattr(request, "param", None) != "production":
        deps.harness_connector_factories = {kind: factory(kind) for kind in ("pi", "codex", "claude_code")}
    if getattr(request, "param", None) in {"additional", "additional_readonly", "additional_unverified"}:
        from okto_nexus.application.adapter_registry import AdapterDescriptor
        from okto_nexus.domain.endpoints import EndpointCapabilities
        registry = harness.build_connector_factories(deps)
        registry.register(AdapterDescriptor("fixture.additional.v1", "fixture.additional.v1", None,
            "fixture-no-process", factory("fixture.additional.v1"), lambda _: None,
            EndpointCapabilities(conversation=request.param != "additional_readonly", events=True), FakeConnector().capabilities,
            input_schema={"transport_binding_contract": 1},
            compatibility_probe=(None if request.param == "additional_unverified" else
                lambda report: EndpointCapabilities(conversation=True, events=True))))
        deps.harness_adapter_registry = registry
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    _, operator_key = ensure_operator_key(deps, auth)
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id="worker", role="reviewer",
                                 capabilities={"review": True}, metadata={"keep": "profile"})
        deps.repos.agents.upsert(uow, agent_id="caller")
        caller_key = auth.issue_key(uow, agent_id="caller")
    ready = threading.Event()

    class Server(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets)
            ready.set()

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = Server(uvicorn.Config(build_app(deps, runtime_owner_api_url=f"http://127.0.0.1:{port}"), log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        assert ready.wait(10), "production HTTP app did not start"
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
            # Setup no longer registers removed native profiles/endpoints.
            # Tests requiring execution must prepare an approved R4 binding;
            # HTTP, policy and retained-history tests can use this bare server.
            yield deps, client, str(root), peers, operator_key, caller_key
    finally:
        supervisor = getattr(deps, "harness_supervisor", None)
        if supervisor:
            for session in supervisor.list_live():
                supervisor.close(session.session_id)
        server.should_exit = True
        thread.join(10)
        sock.close()
        assert not thread.is_alive()


def mcp_call(client, key, method, params):
    response = client.post("/mcp/", headers={"x-api-key": key,
        "Accept": "application/json, text/event-stream"}, json={
            "jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    assert response.status_code == 200, response.text
    if "text/event-stream" in response.headers.get("content-type", ""):
        result = json.loads(next(line[6:] for line in response.text.splitlines()
                                 if line.startswith("data: ")))
    else:
        result = response.json()
    assert "result" in result, result
    return result["result"]


def tool(client, key, name, arguments):
    result = mcp_call(client, key, "tools/call", {"name": name, "arguments": arguments})
    return result.get("structuredContent") or json.loads(result["content"][0]["text"])


def open_rest(runtime, agent="worker"):
    _, client, root, _, key, _ = runtime
    return client.post("/api/v1/harness/sessions", headers={"x-api-key": key},
                       json={"agent_id": agent, "kind": "pi", "project_root": root})


def send_message(runtime, *, subject="fixture", body="fixture", target=None):
    _, client, root, _, _, caller = runtime
    result = tool(client, caller, "message_create", {"project_root": root, "from_agent_id": "caller",
        "subject": subject, "body": body, "target": target or {"strategy": "direct", "agent_id": "worker"}})
    assert result["ok"], result
    return result["data"]


def wait_sent(peers, count=1):
    deadline = time.monotonic() + 5
    while sum(len(peer.sent) for peer in peers) < count and time.monotonic() < deadline:
        time.sleep(0.01)
    assert sum(len(peer.sent) for peer in peers) == count


def stdio_environment(runtime):
    deps, _, _, _, _, caller = runtime
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP"}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env.update(OKTO_NEXUS_API_KEY=caller, HOME=str(deps.config.home_dir), USERPROFILE=str(deps.config.home_dir))
    # Child Nexus writers must use this checkout, not another editable install
    # associated with the shared interpreter. Native harness env stays sealed.
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    return env




@pytest.mark.parametrize("runtime", ["unconfigured"], indirect=True)
def test_unknown_agent_is_rejected_before_factory(runtime):
    _, _, _, peers, _, _ = runtime
    response = open_rest(runtime, "does-not-exist")
    assert response.status_code == 409, response.text
    assert 'Legacy connection setup was removed' in response.text
    assert peers == []


@pytest.mark.parametrize("runtime", ["unconfigured"], indirect=True)
def test_authenticated_mcp_cannot_open_another_agent(runtime):
    _, client, root, peers, _, caller = runtime
    result = tool(client, caller, "harness_open", {
        "agent_id": "worker", "kind": "pi", "project_root": root})
    assert result["ok"] is False, result
    assert result["error"]["code"] == "PERMISSION_DENIED"
    assert peers == []




@pytest.mark.parametrize("runtime", [False], indirect=True)
def test_unconfigured_surface_does_not_publish_harness_tools(runtime):
    _, client, _, _, key, _ = runtime
    result = mcp_call(client, key, "tools/list", {})
    assert not [t["name"] for t in result["tools"] if t["name"].startswith("harness_")]


def test_backend_diagnostics_do_not_echo_credentials():
    result = harness.describe_backend("codex", None, {"env": {"API_TOKEN": "fixture-secret"}})
    assert "fixture-secret" not in json.dumps(result)




@pytest.mark.parametrize("runtime", ["unconfigured"], indirect=True)
def test_keyed_loopback_rest_does_not_upgrade_caller_to_operator(runtime):
    _, client, root, peers, _, caller = runtime
    response = client.post("/api/v1/harness/sessions", headers={"x-api-key": caller},
        json={"agent_id": "worker", "kind": "pi", "project_root": root})
    assert response.status_code == 403, response.text
    assert peers == []






def test_terminal_storage_failure_is_not_silently_accepted(runtime, monkeypatch):
    deps, _, _, _, _, _ = runtime
    session_id = open_rest(runtime).json()["data"]["session_id"]
    from okto_nexus.domain.harness import HarnessEvent
    def unavailable(*args, **kwargs):
        raise OSError("fixture storage unavailable")
    monkeypatch.setattr(deps.repos.harness_events, "append", unavailable)
    event = HarnessEvent(session_id=session_id, harness_kind="pi", kind="turn_completed",
                         native_event="agent_settled", occurred_at=deps.clock.now_iso(), payload={"text": "final"})
    # A failed projection is now durable in the ingress journal, rather than
    # pretending the event was saved in SQLite or discarding the final result.
    ingress = deps.harness_supervisor.event_ingress
    captured = deps.harness_supervisor._handle_event(session_id, event)
    assert ingress.projection_pending
    assert ingress.journal.read_after(0)[0]["event"]["event_id"] == captured.event_id
    assert ingress.journal.read_after(0)[0]["event"]["payload"] == {"text": "final"}
    assert deps.harness_supervisor.replay_events(session_id) == []
    monkeypatch.undo()
    ingress.recover()
    replay = deps.harness_supervisor.replay_events(session_id)
    assert replay[0].event_id == captured.event_id
    assert replay[0].payload == {"text": "final"}
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_results").fetchone()[0] == 1


def test_expired_relay_does_not_mint_new_root(runtime):
    deps, _, _, _, _, _ = runtime
    session_id = open_rest(runtime).json()["data"]["session_id"]
    supervisor = deps.harness_supervisor
    live = supervisor._live[session_id]
    live.relay_depth = supervisor._max_relay_depth
    live.relay_chain_id = "fixture-existing-root"
    live.relay_chain_started_at = supervisor._monotonic() - supervisor._relay_chain_max_age_s - 1
    assert supervisor._resolve_relay_depth("worker") is None


@pytest.mark.parametrize("runtime", ["unconfigured"], indirect=True)
def test_open_does_not_fabricate_credential_authentication(runtime):
    # Regression for the old D3 claim: opening an unknown identity used to be
    # treated as registration/authentication without any credential proof.
    deps, _, _, _, _, _ = runtime
    open_rest(runtime, "new-identity")
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert deps.repos.agents.get(uow, "new-identity") is None




def test_additional_adapter_is_not_rejected_by_domain_product_enum():
    from okto_nexus.domain.harness import HarnessSession, STATUS_STARTING
    peer = FakeConnector(kind="fixture.additional.v1")
    session = HarnessSession(session_id="fixture-session", harness_kind="fixture.additional.v1",
                             owning_agent_id="worker", status=STATUS_STARTING,
                             capabilities=peer.capabilities, started_at="2026-09-22T00:00:00.000000Z")
    assert session.harness_kind == "fixture.additional.v1"




@pytest.mark.parametrize("runtime", ["unconfigured"], indirect=True)
def test_p01_cached_tool_is_denied_after_disable(runtime):
    deps, client, root, peers, key, _ = runtime
    deps.config.feature_harness_integrations = False
    result = tool(client, key, "harness_open", {"agent_id": "worker", "kind": "pi", "project_root": root})
    assert result["error"]["code"] == "PERMISSION_DENIED"
    assert peers == []


@pytest.mark.parametrize("runtime", ["unconfigured"], indirect=True)
def test_p01_attach_respects_explicit_disable(runtime):
    deps, client, root, peers, key, _ = runtime
    deps.config.feature_harness_attach = False
    result = tool(client, key, "harness_open", {"agent_id": "worker", "kind": "claude_code",
        "substrate": "attach", "target_pid": 12345, "project_root": root})
    assert result["error"]["code"] == "PERMISSION_DENIED"
    assert peers == []


@pytest.mark.parametrize("runtime", ["unconfigured"], indirect=True)
def test_p01_stdio_missing_identity_has_no_operator_authority(runtime):
    deps, _, _, _, _, _ = runtime
    from okto_nexus.errors import OktoNexusError
    with pytest.raises(OktoNexusError, match="PERMISSION_DENIED"):
        harness.authorize_request(deps)






def test_p01_legacy_metadata_is_session_data_and_role_conflict_is_rejected(runtime):
    deps, client, root, peers, key, _ = runtime
    result = tool(client, key, "harness_open", {"agent_id": "worker", "kind": "pi",
        "project_root": root, "role": "admin"})
    assert result["error"]["code"] == "VALIDATION_ERROR"
    assert peers == []
    result = tool(client, key, "harness_open", {"agent_id": "worker", "kind": "pi",
        "project_root": root, "metadata": '{"connection_note":"fixture"}'})
    assert result["ok"], result
    assert result["data"]["metadata"]["connection_note"] == "fixture"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert deps.repos.agents.get(uow, "worker").metadata == {"keep": "profile"}


@pytest.mark.parametrize("runtime", ["additional"], indirect=True)
@pytest.mark.parametrize("delivery", ["administrative", "canonical_inbox"])
def test_p02_additional_adapter_through_production_mcp_and_rest(runtime, delivery, monkeypatch):
    deps, client, root, peers, key, _ = runtime
    import subprocess
    def forbidden_process(*args, **kwargs):
        raise AssertionError("Processless adapter must not spawn a local runtime")
    monkeypatch.setattr(subprocess, "Popen", forbidden_process)
    catalog = tool(client, key, "harness_list", {})
    assert {item["adapter_id"] for item in catalog["data"]["harnesses"]} == {
        "pi", "codex", "claude_code.stream", "claude_code.attach", "fixture.additional.v1"}
    rest_catalog = client.get("/api/v1/harness/kinds", headers={"x-api-key": key})
    assert rest_catalog.status_code == 200
    assert rest_catalog.json()["data"]["harnesses"] == catalog["data"]["harnesses"]
    opened = tool(client, key, "harness_open", {"agent_id": "worker",
        "kind": "fixture.additional.v1", "project_root": root})
    assert opened["ok"], opened
    sid = opened["data"]["session_id"]
    if delivery == "administrative":
        response = client.post(f"/api/v1/harness/sessions/{sid}/send", headers={"x-api-key": key},
                               json={"payload": {"text": "fixture command"}})
        assert response.status_code == 200, response.text
    else:
        from test_runtime_outbox import wait_status
        result = send_message(runtime)
        operation = wait_status(runtime, result["runtime_operations"][0], "SENT_UNCONFIRMED")
        assert operation["endpoint_id"] == "endpoint-fixture.additional.v1"
        with deps.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT * FROM message_deliveries WHERE message_id=?",
                                         (result["message_id"],)).fetchone()
            assert row["consumer_kind"] == "push" and row["status"] == "unread"
    wait_sent(peers)
    assert opened["data"]["kind"] == "fixture.additional.v1"
    assert [c.verb for p in peers for c in p.sent] == ["send_turn"]
    if delivery == "canonical_inbox":
        envelope = peers[0].sent[0].payload["envelope"]
        assert envelope["operation_id"] == operation["operation_id"]
        assert envelope["message_id"] == result["message_id"]
        assert envelope["sender_agent_id"] == "caller" and envelope["recipient_agent_id"] == "worker"
