"""Observe the approved Claude executable without starting a model turn."""
import sys
import time

import pytest

from okto_nexus.adapters.outbound.harness.claude_code_stream import ClaudeCodeStreamConnector
from okto_nexus.adapters.outbound.harness.compatibility import claude_version_observation
from okto_nexus.errors import OktoNexusError
from test_pr34_remediation import runtime as runtime_fixture, tool

runtime = runtime_fixture


def test_claude_start_records_observed_version_without_granting_capabilities(tmp_path):
    connector = ClaudeCodeStreamConnector(binary=sys.executable,
        argv=["-u", "-c", "import sys; sys.stdin.read()"], cwd=str(tmp_path))
    try:
        session = connector.start(owning_agent_id="fixture")
        # Python's --version is deliberately not a Claude protocol contract.
        assert session.compatibility_report.get("observation") == "version_not_observed"
        assert session.compatibility_report["native_request_basis"] == "unverified"
        assert session.compatibility_report["compatible_native_requests"] == []
        assert session.compatibility_report["capabilities_verified"] is False
    finally:
        connector.close()


@pytest.mark.parametrize("output,version,verified", [
    ("2.1.280 (Claude Code)", "2.1.280", True),
    ("2.1.281 (Claude Code)", "2.1.281", True),
    ("99.0.0 (Claude Code)", "99.0.0", False),
    ("2.1.280-preview (Claude Code)", None, False),
    ("2.1.280 (Claude Code)\nprivate-extra-data", None, False),
    ("x" * 1100, None, False),
])
def test_version_probe_accepts_only_exact_contract(tmp_path, output, version, verified):
    report = claude_version_observation([sys.executable, "-c", "print(" + repr(output) + ")"],
        cwd=str(tmp_path), env=None)
    assert report["native_version"] == version
    assert (report["native_request_basis"] == "tested_version_contract") is verified
    assert bool(report["compatible_native_requests"]) is verified
    assert report["capabilities_verified"] is False
    assert "private-extra-data" not in str(report)
    if version == "2.1.281":
        assert report["compatible_native_requests"] == [
            "control_request:can_use_tool/Write", "control_request:can_use_tool/AskUserQuestion"]


@pytest.mark.parametrize("source", ["import time; time.sleep(60)",
    "import os;\nwhile True: os.write(1, b'x' * 4096)"])
def test_probe_hang_and_output_flood_are_bounded_and_reaped(tmp_path, monkeypatch, source):
    from okto_nexus.adapters.outbound.harness import compatibility
    spawn = compatibility.spawn_owned_process
    processes = []
    def capture(*args, **kwargs):
        proc = spawn(*args, **kwargs)
        processes.append(proc)
        return proc
    monkeypatch.setattr(compatibility, "spawn_owned_process", capture)
    started = time.monotonic()
    with pytest.raises(OktoNexusError, match="deadline"):
        claude_version_observation([sys.executable, "-c", source], cwd=str(tmp_path), env=None, timeout=.2)
    assert time.monotonic() - started < 6
    assert compatibility.observe_owned_process(processes[0])["stop_observed"]
    assert processes[0].stdout.closed


@pytest.mark.parametrize("version,accepted", [("2.1.280", True), ("99.0.0", False)])
def test_required_claude_contract_uses_probe_in_authenticated_composition(runtime, tmp_path, version, accepted):
    deps, client, root, _, operator, _ = runtime
    deps.config.feature_hitl = True
    peers = []
    def factory(**options):
        native = ClaudeCodeStreamConnector(binary=sys.executable,
            argv=["-u", "-c", "import sys; sys.stdin.read()"],
            version_argv=["-c", "print('" + version + " (Claude Code)')"],
            cwd=root, env=options["backend"]["env"])
        peers.append(native)
        return native
    deps.harness_connector_factories["claude_code"] = factory
    for path, body in [("profiles", {"profile_id": "required", "adapter_id": "claude_code.stream", "enabled": True,
            "config": {"required_native_requests": ["control_request:can_use_tool/Write"]}}),
        ("endpoints", {"endpoint_id": "required", "agent_id": "worker", "adapter_id": "claude_code.stream",
            "profile_id": "required", "enabled": True, "project_root": root})]:
        response = client.post("/api/v1/harness/" + path, headers={"x-api-key": operator}, json=body)
        assert response.status_code == 200, response.text
    body = {"agent_id": "worker", "kind": "claude_code", "endpoint_id": "required",
        "project_root": root, "idempotency_key": "claude-required-open",
        "metadata": {"compatibility_report": {"native_version": "2.1.280", "capabilities_verified": True}}}
    response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json=body)
    if accepted:
        assert response.status_code == 200, response.text
        report = response.json()["data"]["compatibility_report"]
        assert report["native_version"] == version and report["observation"] == "executable_version"
        assert report["capabilities_verified"] is False
        session_id = response.json()["data"]["session_id"]
        assert tool(client, operator, "harness_get", {"session_id": session_id})["data"]["compatibility_report"] == report
    else:
        assert response.status_code >= 400, response.text
        assert "native_requirements_unverified" in response.text
        assert peers[0]._proc.wait(timeout=5) is not None
        retry = tool(client, operator, "harness_open", body)
        assert not retry["ok"] and len(peers) == 1
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert not uow.connection.execute("SELECT 1 FROM harness_sessions WHERE endpoint_id='required'").fetchone()
            assert uow.connection.execute("SELECT health FROM agent_endpoints WHERE endpoint_id='required'").fetchone()[0] == "quarantined"
