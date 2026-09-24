"""Required native contracts must match runtime evidence, not descriptor claims."""
import json
import sys

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector

runtime = runtime_fixture


def install_versioned_codex(runtime, tmp_path, version):
    deps = runtime[0]
    peer = tmp_path / "required-peer.py"
    source = _FAKE_SERVER_SOURCE.replace('"result": {"userAgent": "okto-nexus/0.156.1"}',
        '"result": {"userAgent": "okto-nexus/' + version + ' fixture"}', 1)
    source = source.replace('method = msg.get("method")', 'method = msg.get("method"); log({"method": method})')
    peer.write_text(source, encoding="utf-8")
    peers = []
    def factory(**options):
        native = CodexAppServerConnector(command=[sys.executable, "-u", str(peer), str(tmp_path / "wire.jsonl")],
                                         env=options["backend"]["env"])
        peers.append(native)
        return native
    deps.harness_connector_factories["codex"] = factory
    return peers


def configure_required(runtime, tmp_path, version):
    deps, client, root, _, operator, _ = runtime
    deps.config.feature_hitl = True
    peers = install_versioned_codex(runtime, tmp_path, version)
    for path, body in [("profiles", {"profile_id": "required", "adapter_id": "codex", "enabled": True,
            "config": {"required_native_requests": ["item/commandExecution/requestApproval"]}}),
        ("endpoints", {"endpoint_id": "required", "agent_id": "worker", "adapter_id": "codex",
            "profile_id": "required", "enabled": True, "project_root": root})]:
        response = client.post("/api/v1/harness/" + path, headers={"x-api-key": operator}, json=body)
        assert response.status_code == 200, response.text
    return peers, {"agent_id": "worker", "kind": "codex", "endpoint_id": "required",
        "project_root": root, "idempotency_key": "required-open"}


def test_unknown_runtime_contract_cannot_satisfy_required_native_requests(runtime, tmp_path):
    deps, client, _, _, operator, _ = runtime
    peers, body = configure_required(runtime, tmp_path, "99.0.0")
    body["metadata"] = {"compatibility_report": {"native_version": "0.156.1",
        "native_request_basis": "tested_version_contract",
        "compatible_native_requests": ["item/commandExecution/requestApproval"]}}
    response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json=body)
    assert response.status_code >= 400, response.text
    assert "native_requirements_unverified" in response.text
    assert peers[0]._transport._proc.wait(timeout=5) is not None
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute("SELECT 1 FROM harness_sessions WHERE endpoint_id='required'").fetchone()
        assert uow.connection.execute("SELECT health FROM agent_endpoints WHERE endpoint_id='required'").fetchone()[0] == "quarantined"
    retry = tool(client, operator, "harness_open", body)
    assert not retry["ok"] and len(peers) == 1, retry
    records = [json.loads(line) for line in (tmp_path / "wire.jsonl").read_text(encoding="utf-8").splitlines()]
    assert not any(row.get("method") == "turn/start" for row in records)


def test_known_native_contract_can_satisfy_explicit_profile_requirement(runtime, tmp_path):
    _, client, _, _, operator, _ = runtime
    _, body = configure_required(runtime, tmp_path, "0.156.1")
    response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json=body)
    assert response.status_code == 200, response.text
    report = response.json()["data"]["compatibility_report"]
    assert "item/commandExecution/requestApproval" in report["compatible_native_requests"]
    assert report["capabilities_verified"] is False
