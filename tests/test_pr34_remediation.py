"""Behavior-first PR34 regressions. No real providers or personal stores.

The HTTP fixture runs the production app on a real socket with its actual
authentication middleware and MCP mount. Only the external peer is synthetic.
"""
from __future__ import annotations

import json
import socket
import threading
from dataclasses import asdict

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
    root = tmp_path / "project"
    root.mkdir()
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    deps.config.feature_harness_integrations = getattr(request, "param", True)
    peers = []

    def factory(kind):
        def build(**kwargs):
            from test_harness_tools import _ATTACH_CAPS
            peer = FakeConnector(kind=kind, capabilities=(
                _ATTACH_CAPS if kwargs.get("substrate") == "attach" else None))
            peers.append(peer)
            return peer
        return build

    deps.harness_connector_factories = {kind: factory(kind) for kind in ("pi", "codex", "claude_code")}
    if getattr(request, "param", None) == "additional":
        from okto_nexus.application.adapter_registry import AdapterDescriptor, AdapterRegistry
        from okto_nexus.domain.endpoints import EndpointCapabilities
        registry = AdapterRegistry()
        registry.register(AdapterDescriptor("fixture.additional.v1", "fixture.additional.v1", None,
            "fixture-no-process", factory("fixture.additional.v1"), lambda _: None,
            EndpointCapabilities(conversation=True, events=True), FakeConnector().capabilities))
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
    server = Server(uvicorn.Config(build_app(deps), log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    assert ready.wait(10), "production HTTP app did not start"
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
        if deps.config.feature_harness_integrations:
            kinds = [("fixture.additional.v1", None)] if getattr(request, "param", None) == "additional" else [
                ("pi", None), ("codex", None), ("claude_code", "stream"), ("claude_code", "attach")]
            for kind, substrate in kinds:
                adapter_id = kind + ("." + substrate if substrate else "")
                profile_id = "profile-" + adapter_id
                if substrate != "attach":
                    response = client.post("/api/v1/harness/profiles", headers={"x-api-key": operator_key},
                        json={"profile_id": profile_id, "adapter_id": adapter_id, "enabled": True})
                    assert response.status_code == 200, response.text
                response = client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator_key},
                    json={"endpoint_id": "endpoint-" + adapter_id, "agent_id": "worker", "adapter_id": adapter_id,
                          "project_root": str(root), "enabled": True,
                          "profile_id": profile_id if substrate != "attach" else None,
                          "public_config": {"target_pid": 12345} if substrate == "attach" else {}})
                assert response.status_code == 200, response.text
        yield deps, client, str(root), peers, operator_key, caller_key
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


def test_profile_is_unchanged_by_open_close(runtime):
    deps, _, _, _, _, _ = runtime
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = asdict(deps.repos.agents.get(uow, "worker"))
    response = open_rest(runtime)
    assert response.status_code == 200, response.text
    deps.harness_supervisor.close(response.json()["data"]["session_id"])
    with deps.connection_factory.unit_of_work(write=False) as uow:
        after = asdict(deps.repos.agents.get(uow, "worker"))
    assert after == before


def test_unknown_agent_is_rejected_before_factory(runtime):
    _, _, _, peers, _, _ = runtime
    response = open_rest(runtime, "does-not-exist")
    assert response.status_code == 404, response.text
    assert peers == []


def test_authenticated_mcp_cannot_open_another_agent(runtime):
    _, client, root, peers, _, caller = runtime
    result = tool(client, caller, "harness_open", {
        "agent_id": "worker", "kind": "pi", "project_root": root})
    assert result["ok"] is False, result
    assert result["error"]["code"] == "PERMISSION_DENIED"
    assert peers == []


@pytest.mark.parametrize("name,args", [
    ("harness_send", {"payload": {"text": "unauthorized"}}),
    ("harness_steer", {"payload": {"text": "unauthorized"}}),
    ("harness_interrupt", {}), ("harness_close", {}),
    ("harness_get", {}), ("harness_event_list", {}),
])
def test_authenticated_mcp_cannot_control_or_read_foreign_session(runtime, name, args):
    _, client, _, peers, _, caller = runtime
    opened = open_rest(runtime).json()
    session_id = opened["data"]["session_id"]
    result = tool(client, caller, name, {"session_id": session_id, **args})
    assert result["ok"] is False, result
    assert result["error"]["code"] == "PERMISSION_DENIED"
    assert peers[0].sent == []


@pytest.mark.parametrize("runtime", [False], indirect=True)
def test_unconfigured_surface_does_not_publish_harness_tools(runtime):
    _, client, _, _, key, _ = runtime
    result = mcp_call(client, key, "tools/list", {})
    assert not [t["name"] for t in result["tools"] if t["name"].startswith("harness_")]


def test_backend_diagnostics_do_not_echo_credentials():
    result = harness.describe_backend("codex", None, {"env": {"API_TOKEN": "fixture-secret"}})
    assert "fixture-secret" not in json.dumps(result)


def test_replay_keeps_event_id_and_sequence(runtime):
    deps, _, _, _, _, _ = runtime
    opened = open_rest(runtime).json()
    session_id = opened["data"]["session_id"]
    from okto_nexus.domain.harness import HarnessEvent
    event = HarnessEvent(session_id=session_id, harness_kind="pi", kind="turn_completed",
                         native_event="agent_settled", occurred_at=deps.clock.now_iso(), payload={})
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.harness_events.append(uow, event_id="event-fixture", event=event,
                                        created_at=deps.clock.now_iso())
    replay = deps.harness_supervisor.replay_events(session_id)
    serialized = harness.event_to_dict(replay[0])
    assert serialized.get("sequence") == 1
    assert serialized.get("event_id") == "event-fixture"


def test_keyed_loopback_rest_does_not_upgrade_caller_to_operator(runtime):
    _, client, root, peers, _, caller = runtime
    response = client.post("/api/v1/harness/sessions", headers={"x-api-key": caller},
        json={"agent_id": "worker", "kind": "pi", "project_root": root})
    assert response.status_code == 403, response.text
    assert peers == []


def test_one_delivery_does_not_execute_on_two_sessions(runtime):
    deps, _, root, peers, _, _ = runtime
    for _ in range(2):
        assert open_rest(runtime).status_code == 200
    from okto_nexus.adapters.inbound.mcp.tools.messages import build_service
    messages = build_service(deps)
    messages.create_message(project_root=root, from_agent_id="caller", subject="conversation",
                            body="one logical delivery", target={"strategy": "direct", "agent_id": "worker"})
    assert sum(len(peer.sent) for peer in peers) <= 1


def test_forward_preserves_sender_subject_and_message_identity(runtime):
    deps, _, root, peers, _, _ = runtime
    assert open_rest(runtime).status_code == 200
    from okto_nexus.adapters.inbound.mcp.tools.messages import build_service
    result = build_service(deps).create_message(project_root=root, from_agent_id="caller",
        subject="correlation-subject", body="body-only", target={"strategy": "direct", "agent_id": "worker"})
    wire = json.dumps(peers[0].sent[0].payload)
    assert "caller" in wire and "correlation-subject" in wire and result["message_id"] in wire


def test_terminal_storage_failure_is_not_silently_accepted(runtime, monkeypatch):
    deps, _, _, _, _, _ = runtime
    session_id = open_rest(runtime).json()["data"]["session_id"]
    from okto_nexus.domain.harness import HarnessEvent
    def unavailable(*args, **kwargs):
        raise OSError("fixture storage unavailable")
    monkeypatch.setattr(deps.repos.harness_events, "append", unavailable)
    event = HarnessEvent(session_id=session_id, harness_kind="pi", kind="turn_completed",
                         native_event="agent_settled", occurred_at=deps.clock.now_iso(), payload={"text": "final"})
    # Before a durable journal exists, storage failure must at least fail loudly.
    with pytest.raises(Exception):
        deps.harness_supervisor._handle_event(session_id, event)


def test_expired_relay_does_not_mint_new_root(runtime):
    deps, _, _, _, _, _ = runtime
    session_id = open_rest(runtime).json()["data"]["session_id"]
    supervisor = deps.harness_supervisor
    live = supervisor._live[session_id]
    live.relay_depth = supervisor._max_relay_depth
    live.relay_chain_id = "fixture-existing-root"
    live.relay_chain_started_at = supervisor._monotonic() - supervisor._relay_chain_max_age_s - 1
    assert supervisor._resolve_relay_depth("worker") is None


def test_open_does_not_fabricate_credential_authentication(runtime):
    # Regression for the old D3 claim: opening an unknown identity used to be
    # treated as registration/authentication without any credential proof.
    deps, _, _, _, _, _ = runtime
    open_rest(runtime, "new-identity")
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert deps.repos.agents.get(uow, "new-identity") is None


def test_committed_delivery_survives_lost_notification(runtime, monkeypatch):
    deps, _, root, _, _, _ = runtime
    open_rest(runtime)
    from okto_nexus.adapters.inbound.mcp.tools.messages import build_service
    messages = build_service(deps)
    monkeypatch.setattr(messages, "_maybe_notify_inbox_subscribers", lambda **kwargs: None)
    result = messages.create_message(project_root=root, from_agent_id="caller", subject="recovery",
        body="lost wake fixture", target={"strategy": "direct", "agent_id": "worker"})
    with deps.connection_factory.unit_of_work(write=False) as uow:
        # Inspect durable transport state, not the existence of a proposed
        # Python module. The baseline only has the logical inbox delivery.
        tables = {row[0] for row in uow.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "delivery_outbox" in tables, f"No durable attempt/intent for committed {result['message_id']}"
        row = uow.connection.execute("SELECT operation_id FROM delivery_outbox WHERE message_id=?",
                                     (result["message_id"],)).fetchone()
        assert row is not None


def test_additional_adapter_is_not_rejected_by_domain_product_enum():
    from okto_nexus.domain.harness import HarnessSession, STATUS_STARTING
    peer = FakeConnector(kind="fixture.additional.v1")
    session = HarnessSession(session_id="fixture-session", harness_kind="fixture.additional.v1",
                             owning_agent_id="worker", status=STATUS_STARTING,
                             capabilities=peer.capabilities, started_at="2026-09-22T00:00:00.000000Z")
    assert session.harness_kind == "fixture.additional.v1"


@pytest.mark.parametrize("kind,substrate", [("pi", None), ("codex", None),
    ("claude_code", "stream"), ("claude_code", "attach")])
def test_p01_enabled_authorized_connectors_remain_usable(runtime, kind, substrate):
    deps, client, root, peers, key, _ = runtime
    deps.config.feature_harness_attach = True
    args = {"agent_id": "worker", "kind": kind, "project_root": root}
    if substrate:
        args["substrate"] = substrate
    if substrate == "attach":
        args["target_pid"] = 12345  # synthetic peer only; never opens a real session
    opened = tool(client, key, "harness_open", args)
    assert opened["ok"], opened
    sid = opened["data"]["session_id"]
    sent = tool(client, key, "harness_send", {"session_id": sid,
                "payload": {"text": "test", "content": "test"}})
    assert sent["ok"], sent
    assert len(peers[0].sent) == 1
    assert tool(client, key, "harness_close", {"session_id": sid})["ok"]


def test_p01_cached_tool_is_denied_after_disable(runtime):
    deps, client, root, peers, key, _ = runtime
    deps.config.feature_harness_integrations = False
    result = tool(client, key, "harness_open", {"agent_id": "worker", "kind": "pi", "project_root": root})
    assert result["error"]["code"] == "PERMISSION_DENIED"
    assert peers == []


def test_p01_attach_requires_separate_opt_in(runtime):
    _, client, root, peers, key, _ = runtime
    result = tool(client, key, "harness_open", {"agent_id": "worker", "kind": "claude_code",
        "substrate": "attach", "target_pid": 12345, "project_root": root})
    assert result["error"]["code"] == "PERMISSION_DENIED"
    assert peers == []


def test_p01_stdio_missing_identity_has_no_operator_authority(runtime):
    deps, _, _, _, _, _ = runtime
    from okto_nexus.errors import OktoNexusError
    with pytest.raises(OktoNexusError, match="PERMISSION_DENIED"):
        harness.authorize_request(deps)


def test_p01_duplicate_executor_is_rejected(runtime):
    assert open_rest(runtime).status_code == 200
    second = open_rest(runtime)
    assert second.status_code == 409, second.text
    assert sum(peer.session is not None for peer in runtime[3]) == 1


@pytest.mark.parametrize("verb", ["send", "steer", "interrupt", "close", "get", "events"])
def test_p01_rest_foreign_session_matches_mcp_denial(runtime, verb):
    _, client, _, peers, _, caller = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    path = f"/api/v1/harness/sessions/{sid}"
    if verb in {"get", "events"}:
        response = client.get(path + ("/events" if verb == "events" else ""),
                              headers={"x-api-key": caller})
    else:
        response = client.post(path + "/" + verb, headers={"x-api-key": caller},
                               json={"payload": {"text": "must not send"}})
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"
    assert peers[0].sent == []


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
def test_p02_additional_adapter_through_production_mcp_and_rest(runtime):
    _, client, root, peers, key, _ = runtime
    catalog = tool(client, key, "harness_list", {})
    assert catalog["data"]["harnesses"][0]["adapter_id"] == "fixture.additional.v1"
    opened = tool(client, key, "harness_open", {"agent_id": "worker",
        "kind": "fixture.additional.v1", "project_root": root})
    assert opened["ok"], opened
    sid = opened["data"]["session_id"]
    response = client.post(f"/api/v1/harness/sessions/{sid}/send", headers={"x-api-key": key},
                           json={"payload": {"text": "fixture command"}})
    assert response.status_code == 200, response.text
    assert len(peers[0].sent) == 1
