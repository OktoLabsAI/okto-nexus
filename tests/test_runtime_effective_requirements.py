"""Required native contracts must match runtime evidence, not descriptor claims."""
import json
import sys

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from legacy_native_fixture.codex import CodexAppServerConnector

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
