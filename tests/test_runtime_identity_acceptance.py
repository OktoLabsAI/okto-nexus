"""Exact identity acceptance stimuli through the production HTTP/MCP app."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import threading

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_commands import wait_close_result

runtime = runtime_fixture


def snapshot(runtime):
    deps = runtime[0]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return asdict(deps.repos.agents.get(uow, "worker"))


def enrich(runtime):
    _, client, _, _, operator, _ = runtime
    headers = {"x-api-key": operator}
    assert client.post("/api/v1/tags", headers=headers, json={"key": "org"}).status_code == 200
    assert client.post("/api/v1/tags/org/values", headers=headers,
                       json={"value": "fixture"}).status_code == 200
    response = client.patch("/api/v1/agents/worker", headers=headers, json={
        "tags": {"org": ["fixture"]}, "comm_scope": {"outbound": {"org": ["fixture"]}},
        "permissions": {"messages": {"send_direct": False}}})
    assert response.status_code == 200, response.text
    return snapshot(runtime)


def open_via(runtime, surface, **options):
    _, client, root, _, operator, _ = runtime
    arguments = {"agent_id": "worker", "kind": "pi", "project_root": root, **options}
    if surface == "mcp":
        return tool(client, operator, "harness_open", arguments)
    return client.post("/api/v1/harness/sessions", headers={"x-api-key": operator},
                       json=arguments).json()
