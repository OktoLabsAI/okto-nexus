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


@pytest.mark.parametrize("surface", ["rest", "mcp"])
def test_open_close_reopen_preserves_every_canonical_profile_field(runtime, surface):
    before = enrich(runtime)
    sessions = []
    for index in range(2):
        opened = open_via(runtime, surface, idempotency_key=f"identity-open-{index}")
        assert opened["ok"], opened
        session = opened["data"]
        sessions.append(session["session_id"])
        assert session["owning_agent_id"] == "worker"
        assert snapshot(runtime) == before
        closed = tool(runtime[1], runtime[4], "harness_close", {"session_id": session["session_id"]})
        assert closed["ok"], closed
        wait_close_result(runtime[1], runtime[4], closed)
        assert snapshot(runtime) == before
    assert len(set(sessions)) == 2
    assert len(runtime[3]) == 2


@pytest.mark.parametrize("surface", ["rest", "mcp"])
def test_unknown_identity_is_rejected_without_factory_or_registration(runtime, surface):
    before = snapshot(runtime)
    result = open_via(runtime, surface, agent_id="identity-does-not-exist")
    assert not result["ok"] and result["error"]["code"] == "NOT_FOUND", result
    assert result["error"]["message"]
    assert not runtime[3]
    deps = runtime[0]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert deps.repos.agents.get(uow, "identity-does-not-exist") is None
        assert uow.connection.execute("SELECT count(*) FROM harness_sessions").fetchone()[0] == 0
    assert snapshot(runtime) == before


@pytest.mark.parametrize("same_request", [False, True])
def test_concurrent_same_agent_bindings_preserve_identity_and_deduplicate(runtime, same_request):
    before = enrich(runtime)
    barrier = threading.Barrier(2)
    requests = [{"kind": "pi", "endpoint_id": "endpoint-pi", "idempotency_key": "identity-concurrent"}]
    requests.append(dict(requests[0]) if same_request else {
        "kind": "codex", "endpoint_id": "endpoint-codex", "idempotency_key": "identity-distinct"})

    def open_one(arguments):
        barrier.wait(timeout=5)
        return open_via(runtime, "rest", **arguments)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(open_one, requests))
    assert any(result["ok"] for result in results), results
    if same_request:
        # A concurrent in-progress request may return CONFLICT. After the first
        # completes, repeating its key must resolve the exact existing binding.
        for result in results:
            assert result["ok"] or result["error"]["code"] == "CONFLICT", result
        results = [open_via(runtime, "mcp", **arguments) for arguments in requests]
    assert all(result["ok"] for result in results), results
    sessions = [result["data"] for result in results]
    expected = 1 if same_request else 2
    assert len({session["session_id"] for session in sessions}) == expected
    assert len({session["endpoint_id"] for session in sessions}) == expected
    assert all(session["owning_agent_id"] == "worker" for session in sessions)
    assert len(runtime[3]) == expected
    deps = runtime[0]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM harness_sessions").fetchone()[0] == expected
        for session in sessions:
            presence = deps.repos.sessions.get(uow, session["presence_session_id"])
            assert presence.agent_id == "worker" and presence.status == "active"
            assert presence.workspace_id == session["workspace_id"]
    assert snapshot(runtime) == before
