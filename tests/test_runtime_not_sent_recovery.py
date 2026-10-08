"""Proven pre-write rejection can return the original delivery to canonical pull."""
import json
from pathlib import Path

import pytest

from okto_nexus.application.auth import AgentKeyAuthService
from test_pr34_remediation import runtime as runtime_fixture, send_message, tool
from test_runtime_effective_capabilities import configure_codex
from test_runtime_operation_reconciliation import recovery
from test_runtime_outbox import wait_status

runtime = runtime_fixture


def rejected_before_write(runtime):
    _, client, _, _, operator, _ = runtime
    configure_codex(runtime, version="99.0.0")
    for adapter in ("pi", "claude_code.stream", "claude_code.attach"):
        response = client.patch(f"/api/v1/harness/endpoints/endpoint-{adapter}",
            headers={"x-api-key": operator}, json={"expected_revision": 1, "enabled": False})
        assert response.status_code == 200, response.text
    sent = send_message(runtime)
    return sent, wait_status(runtime, sent["runtime_operations"][0], "REJECTED")
