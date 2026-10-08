"""Authenticated conversational canonical input, without payload authority."""
import json

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool, wait_sent

runtime = runtime_fixture


def request(runtime, surface, sid, payload, key="canonical-fixture"):
    _, client, _, _, operator, _ = runtime
    arguments = {"session_id": sid, "payload": payload, "idempotency_key": key}
    if surface == "mcp":
        return tool(client, operator, "harness_send", arguments)
    response = client.post(f"/api/v1/harness/sessions/{sid}/send",
        headers={"x-api-key": operator}, json={k: v for k, v in arguments.items() if k != "session_id"})
    assert response.status_code in {200, 422}, response.text
    return {"ok": response.status_code == 200, **response.json()}
