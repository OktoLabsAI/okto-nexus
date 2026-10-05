"""Adapter declarations constrain dispatch even when a connector can write bytes."""
import pytest

from test_pr34_remediation import runtime as runtime_fixture, send_message, tool

runtime = runtime_fixture


def readonly_session(runtime):
    _, client, root, _, operator, _ = runtime
    for adapter in ("pi", "codex", "claude_code.stream", "claude_code.attach"):
        response = client.patch(f"/api/v1/harness/endpoints/endpoint-{adapter}",
            headers={"x-api-key": operator}, json={"expected_revision": 1, "enabled": False})
        assert response.status_code == 200, response.text
    opened = tool(client, operator, "harness_open", {"agent_id": "worker",
        "kind": "fixture.additional.v1", "project_root": root})
    assert opened["ok"], opened
    return opened["data"]["session_id"]


@pytest.mark.parametrize("runtime", ["additional_readonly"], indirect=True)
def test_nonconversational_adapter_preserves_logical_inbox_without_transport_intent(runtime):
    deps, _, _, peers, _, _ = runtime
    readonly_session(runtime)
    message = send_message(runtime)
    assert not message.get("runtime_operations"), "Nonconversational adapter acquired an executor reservation"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        delivery = uow.connection.execute("SELECT status,consumer_kind FROM message_deliveries WHERE message_id=?",
            (message["message_id"],)).fetchone()
        assert tuple(delivery) == ("unread", None)
        assert not uow.connection.execute("SELECT 1 FROM delivery_outbox WHERE message_id=?", (message["message_id"],)).fetchone()
    assert not peers[0].sent


@pytest.mark.parametrize("runtime", ["additional"], indirect=True)
def test_pending_delivery_revalidates_descriptor_after_owner_restart(runtime):
    from dataclasses import replace
    from fastapi.testclient import TestClient
    from okto_nexus.adapters.inbound.http.app import build_app
    from okto_nexus.adapters.inbound.mcp.server import bootstrap
    from okto_nexus.adapters.inbound.mcp.tools.harness import build_connector_factories
    from okto_nexus.application.runtime_shutdown import shutdown_runtime
    from test_runtime_outbox import wait_status
    deps, _, _, peers, _, _ = runtime
    readonly_session(runtime)
    deps.runtime_dispatcher.quiesce()
    operation_id = send_message(runtime)["runtime_operations"][0]
    wait_status(runtime, operation_id, "PENDING")
    assert shutdown_runtime(deps.runtime_dispatcher, deps.harness_supervisor)["state"] == "drained"
    recovered = bootstrap({}, ["--home", str(deps.config.home_dir), "--feature-harness-integrations", "true"])
    registry = build_connector_factories(recovered)
    old = deps.harness_adapter_registry.get("fixture.additional.v1")
    constructed = []
    def forbidden(**kwargs):
        constructed.append(kwargs)
        raise AssertionError("Incompatible pending delivery must be rejected before constructing its connector")
    registry.register(replace(old, capabilities=replace(old.capabilities, conversation=False), factory=forbidden))
    with TestClient(build_app(recovered)):
        row = wait_status(runtime, operation_id, "REJECTED")
        assert row["ack_level"] == "NONE" and row["terminal_event_id"] is None
        assert not constructed
        assert not [command for peer in peers for command in peer.sent if command.verb == "send_turn"]


@pytest.mark.parametrize("runtime", ["additional_readonly"], indirect=True)
@pytest.mark.parametrize("surface", ["rest", "mcp"])
def test_nonconversational_adapter_rejects_direct_turn_before_durable_intent(runtime, surface):
    deps, client, _, peers, operator, _ = runtime
    sid = readonly_session(runtime)
    if surface == "rest":
        response = client.post(f"/api/v1/harness/sessions/{sid}/send", headers={"x-api-key": operator},
            json={"payload": {"text": "must not execute"}})
        body = response.json()
    else:
        body = tool(client, operator, "harness_send", {"session_id": sid, "payload": {"text": "must not execute"}})
    assert not body["ok"], body
    assert body["error"]["code"] == "CONFIG_ERROR", body
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute("SELECT 1 FROM runtime_commands WHERE runtime_session_id=?", (sid,)).fetchone()
    assert not peers[0].sent
