"""Remaining work acceptance stimuli through production HTTP/MCP and native pipes."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import threading
import time

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_commands import wait_operation
from test_runtime_grants import issue
from test_runtime_handoff_dispatch import claim, work

runtime = runtime_fixture






def test_restricted_work_profile_keeps_qualified_conversation_useful(runtime):
    from test_runtime_effective_capabilities import open_codex
    deps, client, root, _, operator, caller = runtime
    session = open_codex(runtime, disabled=["managed_work", "approvals"])
    caps = session["compatibility_report"]["effective_capabilities"]
    assert caps["conversation"] and not caps["managed_work"] and not caps["approvals"]
    hid, _ = work(runtime)
    grant = issue(runtime, ["execute_work"], endpoint_id="endpoint-codex")
    denied = claim(runtime, hid, grant, caller)
    assert not denied["ok"] and denied["error"]["code"] == "PERMISSION_DENIED", denied
    incompatible = client.patch("/api/v1/harness/profiles/profile-codex", headers={"x-api-key": operator},
        json={"expected_revision": 2, "config": {"disabled_capabilities": ["approvals", "managed_work"],
            "required_native_requests": ["item/commandExecution/requestApproval"]}})
    assert incompatible.status_code == 422, incompatible.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[0] == "OPEN"
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 0
        assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?", (grant["grant_id"],)).fetchone()[0] == 0
    for index in range(2):
        sent = tool(client, operator, "harness_send", {"session_id": session["session_id"], "payload": {"text": f"safe conversation {index}"}})
        assert sent["ok"], sent
        result = wait_operation(runtime, sent["data"]["operation_id"], lambda row: row["result_durable"])
        assert f"safe conversation {index}" in result["result"]["output_text"]
    wire = [json.loads(line) for line in (Path(root) / "capability-wire.jsonl").read_text().splitlines()]
    assert sum(row.get("request_method") == "turn/start" for row in wire) == 2


@pytest.mark.parametrize("requirement", [{"sandbox": "read-only"}, {"approval_policy": "untrusted"}])
def test_unsupported_sandbox_profile_cannot_replace_compatible_conversation(runtime, requirement):
    from legacy_native_fixture.claude_code_stream import ClaudeCodeStreamConnector
    from test_harness_claude_code_connector import _FAKE_CLAUDE_SCRIPT
    deps, client, root, _, operator, _ = runtime
    peers = []
    def factory(**kwargs):
        peer = ClaudeCodeStreamConnector(binary=sys._base_executable, argv=["-u", "-c", _FAKE_CLAUDE_SCRIPT],
            version_argv=["-c", "print('2.1.281 (Claude Code)')"], cwd=root, env=kwargs["backend"]["env"])
        peers.append(peer)
        return peer
    deps.harness_connector_factories["claude_code"] = factory
    denied = client.patch("/api/v1/harness/profiles/profile-claude_code.stream", headers={"x-api-key": operator},
        json={"expected_revision": 1, "config": requirement})
    assert denied.status_code == 422 and denied.json()["error"]["code"] == "VALIDATION_ERROR", denied.text
    assert not peers
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT revision,config FROM runtime_profiles WHERE profile_id='profile-claude_code.stream'").fetchone()
        assert row[0] == 1 and json.loads(row[1]) == {}
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "claude_code", "substrate": "stream",
        "endpoint_id": "endpoint-claude_code.stream", "project_root": root})
    assert opened.status_code == 200, opened.text
    sid = opened.json()["data"]["session_id"]
    sent = tool(client, operator, "harness_send", {"session_id": sid, "payload": {"text": "compatible conversation"}})
    assert sent["ok"], sent
    result = wait_operation(runtime, sent["data"]["operation_id"], lambda row: row["result_durable"])
    assert "echo:compatible conversation" in result["result"]["output_text"]
    assert len(peers) == 1
