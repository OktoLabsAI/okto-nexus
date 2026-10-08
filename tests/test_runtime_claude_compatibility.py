"""Observe the approved Claude executable without starting a model turn."""
import sys
import time

import pytest

from legacy_native_fixture.claude_code_stream import ClaudeCodeStreamConnector
from legacy_native_fixture.compatibility import claude_version_observation
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
    from legacy_native_fixture import compatibility
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
