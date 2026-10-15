"""Canonical workspace isolation and continuation affinity across selection changes."""
import json
import time

import pytest

from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, tool
from test_runtime_outbox import wait_status
from test_runtime_commands import wait_operation

runtime = runtime_fixture


def add_endpoint(runtime, *, endpoint, root, priority=0):
    _, client, _, _, operator, _ = runtime
    response = client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator}, json={
        "endpoint_id": endpoint, "agent_id": "worker", "adapter_id": "pi", "project_root": root,
        "profile_id": "profile-pi", "enabled": True, "response_policy": "conversation", "priority": priority})
    assert response.status_code == 200, response.text
    opened = tool(client, operator, "harness_open", {"agent_id": "worker", "kind": "pi",
        "project_root": root, "endpoint_id": endpoint})
    assert opened["ok"], opened
    return opened["data"]
