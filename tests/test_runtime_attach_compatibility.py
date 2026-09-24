"""Real disposable Unix peer; unknown wire formats must never receive a token."""
import json
import os

import pytest

from test_claude_code_attach_connector import fake_server as attach_server_fixture, _write_registry, _write_key
from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_commands import wait_operation, wait_close_result
from okto_nexus.adapters.outbound.harness.claude_code_attach import ClaudeCodeAttachConnector
from okto_nexus.domain.harness import HarnessCommand
from okto_nexus.errors import OktoNexusError

pytestmark = pytest.mark.skipif(os.name != "posix", reason="NOT_RUN: attach requires POSIX ownership")
fake_server = attach_server_fixture
runtime = runtime_fixture


@pytest.mark.parametrize("protocol", [None, True, 1.0, "1", 2])
def test_unverified_attach_protocol_refuses_before_socket_or_token(tmp_path, fake_server, protocol):
    pid = os.getpid()
    _write_registry(tmp_path, pid, socket_path=str(fake_server.sock_path), peer_protocol=protocol)
    _write_key(tmp_path, pid)
    connector = ClaudeCodeAttachConnector(pid, sessions_dir=tmp_path)
    probe = connector.probe()
    assert not probe.ok and probe.reason == "protocol_mismatch"
    with pytest.raises(OktoNexusError) as exc:
        connector.start(owning_agent_id="fixture")
    assert exc.value.details["reason"] == "protocol_mismatch"
    assert fake_server.connections == []


@pytest.mark.parametrize("protocol", [1, None])
def test_attach_contract_and_ackless_delivery_through_authenticated_surfaces(runtime, tmp_path, fake_server, protocol):
    deps, client, root, _, operator, _ = runtime
    deps.config.feature_harness_attach = True
    pid = os.getpid()
    _write_registry(tmp_path, pid, socket_path=str(fake_server.sock_path), peer_protocol=protocol)
    _write_key(tmp_path, pid)
    deps.harness_connector_factories["claude_code"] = lambda **kw: ClaudeCodeAttachConnector(
        kw["target_pid"], sessions_dir=tmp_path)
    response = client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator}, json={
        "endpoint_id": "attach-qualified", "agent_id": "worker", "adapter_id": "claude_code.attach",
        "project_root": root, "enabled": True, "response_policy": "conversation", "public_config": {"target_pid": pid}})
    assert response.status_code == 200, response.text
    body = {"agent_id": "worker", "kind": "claude_code", "substrate": "attach",
        "endpoint_id": "attach-qualified", "project_root": root, "idempotency_key": "attach-open"}
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json=body)
    if protocol is None:
        assert opened.status_code >= 400, opened.text
        assert not tool(client, operator, "harness_open", body)["ok"]
        assert fake_server.connections == []
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert not uow.connection.execute("SELECT 1 FROM harness_sessions WHERE endpoint_id='attach-qualified'").fetchone()
        return
    assert opened.status_code == 200, opened.text
    sid = opened.json()["data"]["session_id"]
    report = opened.json()["data"]["compatibility_report"]
    assert report["peer_protocol"] == 1 and report["transport_contract"] == "cc_socks_peer_1"
    assert report["ack_level"] == "NONE" and report["capabilities_verified"] is False
    assert report["compatible_native_requests"] == []
    assert tool(client, operator, "harness_get", {"session_id": sid})["data"]["compatibility_report"] == report
    sent = tool(client, operator, "harness_send", {"session_id": sid,
        "payload": {"text": "fixture attach content"}, "idempotency_key": "attach-send"})
    assert sent["ok"], sent
    operation = wait_operation(runtime, sent["data"]["operation_id"], lambda row: row["state"] == "SENT_UNCONFIRMED")
    assert not operation["result_durable"]
    fake_server.wait_for_connections(2)
    assert fake_server.connections[0] == []
    assert fake_server.connections[1][1]["type"] == "user"
    assert "fixture attach content" in fake_server.connections[1][1]["message"]["content"]
    for verb in ("steer", "interrupt"):
        denied = tool(client, operator, "harness_" + verb, {"session_id": sid,
            **({"payload": {"text": "unsupported"}} if verb == "steer" else {})})
        assert not denied["ok"], denied
    closed = tool(client, operator, "harness_close", {"session_id": sid})
    assert closed["ok"], closed
    assert wait_close_result(client, operator, closed)["lifecycle_state"] == "detached"
    assert len(fake_server.connections) == 2


def test_attach_protocol_drift_after_open_prevents_any_send(tmp_path, fake_server):
    pid = os.getpid()
    _write_registry(tmp_path, pid, socket_path=str(fake_server.sock_path))
    _write_key(tmp_path, pid)
    connector = ClaudeCodeAttachConnector(pid, sessions_dir=tmp_path)
    session = connector.start(owning_agent_id="fixture")
    fake_server.wait_for_connections(1)
    _write_registry(tmp_path, pid, socket_path=str(fake_server.sock_path), peer_protocol=2)
    with pytest.raises(OktoNexusError) as exc:
        connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn", payload={"content": "must not write"}))
    assert exc.value.details["reason"] == "protocol_mismatch"
    assert fake_server.connections == [[]]


def test_attach_missing_protocol_field_is_not_a_compatible_default(tmp_path, fake_server):
    pid = os.getpid()
    _write_registry(tmp_path, pid, socket_path=str(fake_server.sock_path))
    path = tmp_path / f"{pid}.json"
    registry = json.loads(path.read_text())
    del registry["peerProtocol"]
    path.write_text(json.dumps(registry))
    _write_key(tmp_path, pid)
    probe = ClaudeCodeAttachConnector(pid, sessions_dir=tmp_path).probe()
    assert not probe.ok and probe.reason == "protocol_mismatch"
