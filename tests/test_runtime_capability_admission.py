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
