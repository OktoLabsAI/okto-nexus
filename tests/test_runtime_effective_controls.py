"""Control admission must use session evidence, not the adapter declaration."""
import json
import sys

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_effective_requirements import install_versioned_codex
from test_runtime_commands import wait_operation

runtime = runtime_fixture


@pytest.mark.parametrize("verb", ["steer", "interrupt"])
def test_unknown_version_cannot_admit_native_control(runtime, tmp_path, verb):
    deps, client, root, _, operator, _ = runtime
    install_versioned_codex(runtime, tmp_path, "99.0.0")
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root,
        "metadata": {"compatibility_report": {"compatible_controls": ["steer", "interrupt"]}}})
    assert opened.status_code == 200, opened.text
    sid = opened.json()["data"]["session_id"]
    sent = tool(client, operator, "harness_send", {"session_id": sid, "payload": {"text": "TRIGGER_HOLD"}})
    assert sent["ok"], sent
    op = sent["data"]["operation_id"]
    wait_operation(runtime, op, lambda row: row["external_acceptance"] == "harness_accepted")
    request = {"session_id": sid, "expected_operation_id": op,
        **({"payload": {"text": "unsupported-control"}} if verb == "steer" else {})}
    result = tool(client, operator, "harness_" + verb, request)
    assert not result["ok"], result
    assert "native_control_unverified" in result["error"]["message"], result
    rest_body = {key: value for key, value in request.items() if key != "session_id"}
    response = client.post(f"/api/v1/harness/sessions/{sid}/{verb}", headers={"x-api-key": operator}, json=rest_body)
    assert response.status_code >= 400 and "native_control_unverified" in response.text
    from okto_nexus.errors import OktoNexusError
    with pytest.raises(OktoNexusError, match="native_control_unverified"):
        deps.harness_supervisor.send(sid, verb, request.get("payload", {}))
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute("SELECT 1 FROM runtime_commands WHERE verb IN ('steer','interrupt')").fetchone()
    wire = [json.loads(line) for line in (tmp_path / "wire.jsonl").read_text().splitlines()]
    assert not any(row.get("method") == "turn/" + verb for row in wire)


def test_effective_control_is_revalidated_before_dispatch(runtime, tmp_path, monkeypatch):
    deps, client, root, _, operator, _ = runtime
    install_versioned_codex(runtime, tmp_path, "0.156.1")
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert opened.status_code == 200, opened.text
    sid = opened.json()["data"]["session_id"]
    sent = tool(client, operator, "harness_send", {"session_id": sid, "payload": {"text": "TRIGGER_HOLD"}})
    op = sent["data"]["operation_id"]
    wait_operation(runtime, op, lambda row: row["external_acceptance"] == "harness_accepted")
    runner = deps.runtime_dispatcher.command_dispatcher
    scan = runner.scan_once
    monkeypatch.setattr(runner, "scan_once", lambda: None)
    control = tool(client, operator, "harness_interrupt", {"session_id": sid, "expected_operation_id": op})
    assert control["ok"], control
    # Controlled invalidation of server evidence while the command is pending.
    deps.harness_supervisor.get(sid).compatibility_report["compatible_controls"] = []
    monkeypatch.setattr(runner, "scan_once", scan)
    deps.runtime_dispatcher.wake()
    wait_operation(runtime, control["data"]["operation_id"], lambda row: row["state"] == "REJECTED")
    wire = [json.loads(line) for line in (tmp_path / "wire.jsonl").read_text().splitlines()]
    assert not any(row.get("method") == "turn/interrupt" for row in wire)


@pytest.mark.parametrize("version,controls", [("0.85.1", ["steer", "interrupt"]), ("99.0.0", [])])
def test_pi_reports_controls_from_real_owned_version_probe(tmp_path, version, controls):
    from okto_nexus.adapters.outbound.harness.pi import PiRpcConnector
    from test_harness_pi_connector import _FAKE_SERVER_SOURCE
    peer = PiRpcConnector(command=[sys.executable, "-u", "-c", _FAKE_SERVER_SOURCE],
        version_command=[sys.executable, "-c", "print('" + version + "')"], cwd=str(tmp_path))
    try:
        session = peer.start(owning_agent_id="fixture")
        assert session.compatibility_report["native_version"] == version
        assert session.compatibility_report["compatible_controls"] == controls
        assert session.compatibility_report["capabilities_verified"] is False
    finally:
        peer.close()
