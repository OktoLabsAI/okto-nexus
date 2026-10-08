"""Explicit relay admission through real HTTP/MCP composition and native frames."""
import time
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_pr34_remediation import runtime as runtime_fixture, send_message
from test_runtime_commands import codex_session

runtime = runtime_fixture


def configure(runtime, *, depth=2, outcome="completed", kind="codex"):
    deps, client, root, _, operator, _ = runtime
    deps.config.max_relay_depth = depth
    adapter = "claude_code.stream" if kind == "claude_code" else kind
    # Create a separate explicitly approved endpoint; existing defaults remain
    # non-relaying. No policy inserted behind the production service.
    for agent in ("worker", "caller"):
        response = client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator}, json={
            "endpoint_id": "relay-" + agent, "agent_id": agent, "adapter_id": adapter, "project_root": root,
            "profile_id": "profile-" + adapter, "enabled": True, "priority": 10,
            "response_policy": "conversation", "public_config": {"relay_results": True}})
        assert response.status_code == 200, response.text
    # Register the actual JSON-RPC fixture adapter through existing composition.
    codex_session(runtime, outcome=outcome)
    if kind == "claude_code":
        from legacy_native_fixture.claude_code_stream import ClaudeCodeStreamConnector
        from test_harness_claude_code_connector import _FAKE_CLAUDE_SCRIPT
        deps.harness_connector_factories[kind] = lambda **kwargs: ClaudeCodeStreamConnector(
            binary=sys._base_executable, argv=["-u", "-c", _FAKE_CLAUDE_SCRIPT], cwd=root, env=kwargs["backend"]["env"],
            version_argv=["-c", "print('2.1.281 (Claude Code)')"])
    elif kind == "pi":
        from legacy_native_fixture.pi import PiRpcConnector
        from test_harness_pi_connector import _FAKE_SERVER_SOURCE
        from pathlib import Path
        import itertools
        sequence = itertools.count()
        deps.harness_connector_factories[kind] = lambda **kwargs: PiRpcConnector(
            command=[sys._base_executable, "-u", "-c", _FAKE_SERVER_SOURCE, str(Path(root) / f"pi-{next(sequence)}.jsonl")],
            version_command=[sys._base_executable, "-c", "print('0.85.1')"],
            cwd=root, env=kwargs["backend"]["env"])
    for agent in ("worker", "caller"):
        response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
            "agent_id": agent, "kind": kind, "endpoint_id": "relay-" + agent, "project_root": root})
        assert response.status_code == 200, response.text


def wait_blocked(runtime, count=1):
    deps = runtime[0]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            rows = [dict(r) for r in uow.connection.execute("SELECT * FROM runtime_results ORDER BY captured_at,result_id")]
        if sum(r["relay_state"] == "BLOCKED" for r in rows) >= count:
            return rows
        time.sleep(.01)
    raise AssertionError(rows)




















@pytest.mark.parametrize("agent_key,status", [(True, 403), (False, 422)])
def test_relay_configuration_cannot_be_self_authorized_or_attached_without_results(runtime, agent_key, status):
    _, client, root, _, operator, caller = runtime
    response = client.post("/api/v1/harness/endpoints", headers={"x-api-key": caller if agent_key else operator}, json={
        "endpoint_id": "untrusted-relay", "agent_id": "caller", "adapter_id": "claude_code.attach",
        "project_root": root, "enabled": True, "response_policy": "conversation",
        "public_config": {"relay_results": True, "target_pid": 12345}})
    assert response.status_code == status, response.text




@pytest.mark.parametrize("kind,native,payload,expected", [
    ("pi", "message_end", {"role": "assistant", "stopReason": "aborted"}, "interrupted"),
    ("pi", "message_end", {"message": {"role": "assistant", "stopReason": "error"}}, "failed"),
    ("pi", "agent_settled", {"delivery_outcome": "success"}, None),
    ("claude_code", "result:success", {"interrupted_by_connector": True}, "interrupted"),
    ("claude_code", "result:success", {"is_error": True}, "failed"),
    ("claude_code", "result:error_during_execution", {}, "failed"),
])
def test_adapter_outcome_mapping_does_not_promote_errors_or_payload_claims(kind, native, payload, expected):
    from legacy_native_fixture.pi import PiRpcConnector
    from legacy_native_fixture.claude_code_stream import ClaudeCodeStreamConnector
    from okto_nexus.domain.harness import HarnessEvent
    event = HarnessEvent(session_id="fixture", harness_kind=kind, kind="turn_completed",
        native_event=native, payload=payload, occurred_at="2026-09-23T00:00:00.000Z")
    adapter = PiRpcConnector if kind == "pi" else ClaudeCodeStreamConnector
    assert adapter.delivery_outcome(event) == expected
