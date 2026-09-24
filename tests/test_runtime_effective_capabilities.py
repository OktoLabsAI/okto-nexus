"""Unknown native contracts cannot inherit execution from adapter declarations."""
import sys
import json
from pathlib import Path

import pytest

from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from test_pr34_remediation import runtime as runtime_fixture, send_message, tool

runtime = runtime_fixture


@pytest.mark.parametrize("runtime", ["additional_unverified"], indirect=True)
def test_extension_without_trusted_probe_cannot_execute(runtime):
    _, client, root, peers, operator, _ = runtime
    opened = tool(client, operator, "harness_open", {"agent_id": "worker",
        "kind": "fixture.additional.v1", "endpoint_id": "endpoint-fixture.additional.v1", "project_root": root})
    assert opened["ok"], opened
    session = opened["data"]
    assert session["compatibility_report"]["effective_capability_basis"] == "unverified"
    denied = tool(client, operator, "harness_send", {"session_id": session["session_id"], "payload": {"text": "blocked"}})
    assert not denied["ok"] and denied["error"]["code"] == "CONFIG_ERROR"
    assert all(not peer.sent for peer in peers)


@pytest.mark.parametrize("disabled", [["interrupt_requires_settle"], ["conversation", "conversation"], ["invented"], "conversation"])
def test_profile_rejects_invalid_capability_restrictions(runtime, disabled):
    _, client, _, _, operator, _ = runtime
    response = client.patch("/api/v1/harness/profiles/profile-codex", headers={"x-api-key": operator},
        json={"expected_revision": 1, "config": {"disabled_capabilities": disabled}})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def configure_codex(runtime, version="0.156.1", disabled=()):
    deps, client, root, _, operator, _ = runtime
    result = {"userAgent": "okto-nexus/" + version} if version else {}
    source = _FAKE_SERVER_SOURCE.replace('"result": {"userAgent": "okto-nexus/0.156.1"}', '"result": ' + repr(result), 1)
    source = source.replace('method = msg.get("method")', 'method = msg.get("method"); log({"request_method": method})')
    deps.harness_connector_factories["codex"] = lambda **options: CodexAppServerConnector(
        command=[sys._base_executable, "-u", "-c", source, str(Path(root) / "capability-wire.jsonl")], cwd=root, env=options["backend"]["env"])
    if disabled:
        changed = client.patch("/api/v1/harness/profiles/profile-codex", headers={"x-api-key": operator},
            json={"expected_revision": 1, "config": {"disabled_capabilities": list(disabled)}})
        assert changed.status_code == 200, changed.text
    return {"agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root}


def open_codex(runtime, **options):
    _, client, _, _, operator, _ = runtime
    body = configure_codex(runtime, **options)
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        **body, "metadata": {"effective_capabilities": {"conversation": True, "native_deduplication": True}}})
    assert opened.status_code == 200, opened.text
    return opened.json()["data"]


@pytest.mark.parametrize("version", ["99.0.0", None])
def test_unknown_codex_contract_cannot_admit_a_direct_turn(runtime, version):
    deps, client, _, _, operator, _ = runtime
    session = open_codex(runtime, version=version)
    sid = session["session_id"]
    assert session["compatibility_report"]["effective_capabilities"]["conversation"] is False
    response = client.post(f"/api/v1/harness/sessions/{sid}/send", headers={"x-api-key": operator},
        json={"payload": {"text": "must not execute"}})
    assert response.status_code == 500, "Unknown native contract inherited conversation from the adapter declaration: " + response.text
    assert response.json()["error"]["code"] == "CONFIG_ERROR"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute("SELECT 1 FROM runtime_commands WHERE runtime_session_id=?", (sid,)).fetchone()


def test_qualified_codex_remains_multiturn_and_discovery_matches_mcp(runtime):
    from test_runtime_commands import wait_operation
    _, client, _, _, operator, _ = runtime
    session = open_codex(runtime)
    capabilities = session["compatibility_report"]["effective_capabilities"]
    assert capabilities["conversation"] and capabilities["managed_work"] and capabilities["multiplexing"]
    assert not capabilities["native_deduplication"] and not capabilities["native_replay"]
    assert not capabilities["approvals"], "HITL is disabled in this profile configuration"
    for text in ("qualified first", "qualified second"):
        response = tool(client, operator, "harness_send", {"session_id": session["session_id"], "payload": {"text": text}})
        assert response["ok"], response
        result = wait_operation(runtime, response["data"]["operation_id"], lambda row: row["result_durable"])
        assert text in result["result"]["output_text"]
    rest = client.get("/api/v1/harness/bindings", headers={"x-api-key": operator}).json()["data"]
    mcp = tool(client, operator, "harness_list", {"view": "bindings"})
    assert mcp["ok"] and mcp["data"] == rest
    actual = next(s for a in rest["agents"] for e in a["endpoints"] for s in e["sessions"] if s["session_id"] == session["session_id"])
    assert actual["effective_capabilities"] == capabilities


@pytest.mark.parametrize("disabled", ["conversation", "managed_work", "events", "multiplexing", "approvals"])
def test_profile_can_only_remove_qualified_capabilities(runtime, disabled):
    session = open_codex(runtime, disabled=[disabled])
    caps = session["compatibility_report"]["effective_capabilities"]
    assert caps[disabled] is False
    if disabled == "events":
        assert caps["managed_work"] is False
    assert not caps["native_deduplication"]
    if disabled == "conversation":
        _, client, _, _, operator, _ = runtime
        denied = tool(client, operator, "harness_send", {"session_id": session["session_id"], "payload": {"text": "blocked"}})
        assert not denied["ok"] and denied["error"]["code"] == "CONFIG_ERROR"


def test_unknown_on_demand_contract_is_rejected_without_native_write_or_uncertain_receipt(runtime):
    from test_runtime_outbox import wait_status
    deps, client, root, _, operator, _ = runtime
    configure_codex(runtime, version="99.0.0")
    for adapter in ("pi", "claude_code.stream", "claude_code.attach"):
        response = client.patch(f"/api/v1/harness/endpoints/endpoint-{adapter}", headers={"x-api-key": operator},
            json={"expected_revision": 1, "enabled": False})
        assert response.status_code == 200, response.text
    operation_id = send_message(runtime)["runtime_operations"][0]
    row = wait_status(runtime, operation_id, "REJECTED")
    assert row["ack_level"] == "NONE" and row["reason"] == "native_write_not_started"
    wire = [json.loads(line) for line in (Path(root) / "capability-wire.jsonl").read_text().splitlines()]
    assert "thread/start" in [line.get("request_method") for line in wire]
    assert "turn/start" not in [line.get("request_method") for line in wire]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        delivery = uow.connection.execute("SELECT status,consumer_kind FROM message_deliveries WHERE delivery_id=?", (row["delivery_id"],)).fetchone()
        assert tuple(delivery) == ("unread", "push"), "Uncertainty/rejection must not silently donate executor authority"


def test_unknown_contract_cannot_share_an_explicitly_reused_native_connection(runtime):
    deps, client, root, _, operator, _ = runtime
    body = configure_codex(runtime, version="99.0.0")
    original = deps.harness_connector_factories["codex"]
    peers = []
    def shared(**options):
        if not peers:
            peers.append(original(**options))
        return peers[0]
    deps.harness_connector_factories["codex"] = shared
    first = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json=body)
    assert first.status_code == 200, first.text
    endpoint = client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator}, json={
        "endpoint_id": "unqualified-sibling", "agent_id": "worker", "adapter_id": "codex", "project_root": root,
        "profile_id": "profile-codex", "enabled": True})
    assert endpoint.status_code == 200, endpoint.text
    second = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator},
        json=body | {"endpoint_id": "unqualified-sibling"})
    assert second.status_code == 409, "Factory reuse bypassed effective multiplexing=False: " + second.text
    wire = [json.loads(line) for line in (Path(root) / "capability-wire.jsonl").read_text().splitlines()]
    assert sum(row.get("request_method") == "thread/start" for row in wire) == 1
    assert deps.harness_supervisor.get(first.json()["data"]["session_id"]) is not None
