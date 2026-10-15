"""Real REST/MCP configuration boundaries for an external Nexus work channel.

This qualifies reference approval only. Claim/ACK/complete remains a separate
end-to-end gate in test_runtime_attach_work_channel.py.
"""
import json

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool, open_rest
from test_runtime_handoff_dispatch import work

runtime = runtime_fixture


def configure(runtime, surface, *, action="update", key=None, config=None, **changes):
    _, client, root, _, operator, _ = runtime
    parameters = {"public_config": config, **changes}
    if action == "create":
        parameters.update(endpoint_id="external-attach", agent_id="worker",
            adapter_id="claude_code.attach", project_root=root, enabled=True)
    else:
        parameters.setdefault("expected_revision", 1)
    if surface == "mcp":
        return tool(client, key or operator, "harness_list", {"view": "endpoints", "maintenance": {
            "action": action, **({"endpoint_id": "endpoint-claude_code.attach"} if action == "update" else {}),
            **parameters}})
    response = (client.post("/api/v1/harness/endpoints", headers={"x-api-key": key or operator}, json=parameters)
        if action == "create" else client.patch("/api/v1/harness/endpoints/endpoint-claude_code.attach",
            headers={"x-api-key": key or operator}, json=parameters))
    return response.json()


def session(runtime, *, agent="worker", workspace=None, key=None):
    deps, client, _, _, _, caller = runtime
    if key is None:
        _, key = work(runtime)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        workspace = workspace or uow.connection.execute(
            "SELECT workspace_id FROM agent_endpoints WHERE endpoint_id='endpoint-claude_code.attach'").fetchone()[0]
    result = tool(client, key if agent == "worker" else caller, "session_open",
        {"agent_id": agent, "workspace_id": workspace})
    assert result["ok"], result
    return result["data"]
