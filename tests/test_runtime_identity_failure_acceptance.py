"""Canonical catalogue gates and owned-process cleanup after partial startup."""
import sqlite3
import sys

import pytest

from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_commands import wait_close_result

runtime = runtime_fixture


def identities(deps):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        # Authentication updates caller activity independently of runtime start.
        # Compare all identity/profile fields except this observation timestamp.
        return [{key: row[key] for key in row.keys() if key != "last_seen_at"}
            for row in uow.connection.execute("SELECT * FROM agents ORDER BY agent_id")]


def test_canonical_catalogue_gates_rest_and_mcp_and_runtime_open_cannot_change_it(runtime):
    deps, client, root, peers, operator, caller = runtime
    headers = {"x-api-key": operator}
    assert client.post("/api/v1/capabilities", headers=headers, json={"name": "catalogue-fixture"}).status_code == 200
    before = identities(deps)
    unknown = ["catalogue-fixture", "not-registered"]
    rest = client.patch("/api/v1/agents/caller", headers=headers, json={"capabilities": unknown})
    mcp = tool(client, caller, "agent_register", {"agent_id": "caller", "capabilities": unknown})
    assert rest.status_code == 422 and not mcp["ok"]
    assert rest.json()["error"]["code"] == mcp["error"]["code"] == "VALIDATION_ERROR"
    assert identities(deps) == before
    assert client.patch("/api/v1/agents/caller", headers=headers, json={"capabilities": ["catalogue-fixture"]}).status_code == 200
    assert tool(client, caller, "agent_register", {"agent_id": "caller", "capabilities": ["catalogue-fixture"]})["ok"]
    before = identities(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        catalogue = [dict(row) for row in uow.connection.execute("SELECT * FROM capability_names ORDER BY name")]
    endpoint = client.post("/api/v1/harness/endpoints", headers=headers, json={
        "endpoint_id": "catalogue-caller", "agent_id": "caller", "adapter_id": "pi", "project_root": root,
        "profile_id": "profile-pi", "enabled": True})
    assert endpoint.status_code == 200, endpoint.text
    opened = tool(client, operator, "harness_open", {"agent_id": "caller", "kind": "pi",
        "project_root": root, "endpoint_id": "catalogue-caller"})
    assert opened["ok"], opened
    assert identities(deps) == before and len(peers) == 1
    closed = tool(client, operator, "harness_close", {"session_id": opened["data"]["session_id"]})
    assert closed["ok"], closed
    wait_close_result(client, operator, closed)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert [dict(row) for row in uow.connection.execute("SELECT * FROM capability_names ORDER BY name")] == catalogue
        assert not uow.connection.execute("SELECT 1 FROM capability_names WHERE name='not-registered'").fetchone()
    assert identities(deps) == before


@pytest.mark.parametrize("failure", ["session_validation", "persistence"])
@pytest.mark.parametrize("surface", ["rest", "mcp"])
def test_failure_after_native_start_preserves_identity_and_reaps_exact_owned_process(runtime, monkeypatch, failure, surface):
    deps, client, root, _, operator, _ = runtime
    before = identities(deps)
    processes = []

    def factory(**options):
        peer = CodexAppServerConnector(command=[sys._base_executable, "-u", "-c", _FAKE_SERVER_SOURCE],
            cwd=root, env=options["backend"]["env"])
        start = peer.start

        def after_start(**kwargs):
            session = start(**kwargs)
            process = peer._transport._proc
            assert process.poll() is None  # actual successful owned spawn/handshake
            processes.append(process)
            if failure == "session_validation":
                session.status = "ENDED"
            return session

        peer.start = after_start
        return peer

    deps.harness_connector_factories["codex"] = factory
    if failure == "persistence":
        original = deps.harness_supervisor._sessions.create

        def after_insert(uow, **kwargs):
            original(uow, **kwargs)
            assert uow.connection.execute("SELECT count(*) FROM harness_sessions").fetchone()[0] == 1
            raise sqlite3.OperationalError("fixture cut after actual session insert")

        monkeypatch.setattr(deps.harness_supervisor._sessions, "create", after_insert)
    arguments = {"agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex",
        "project_root": root, "idempotency_key": "failed-start-fixture"}
    if surface == "rest":
        response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json=arguments)
        assert response.status_code >= 400, response.text
    else:
        response = tool(client, operator, "harness_open", arguments)
        assert not response["ok"], response
    assert len(processes) == 1
    assert processes[0].wait(timeout=5) is not None
    assert not deps.harness_supervisor.list_live()
    assert identities(deps) == before
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute("SELECT 1 FROM harness_sessions").fetchone()
        assert not uow.connection.execute("SELECT 1 FROM sessions WHERE agent_id='worker'").fetchone()
        assert not uow.connection.execute("PRAGMA foreign_key_check").fetchall()
    # A lost/failed open reply cannot turn into an automatic second startup.
    repeated = tool(client, operator, "harness_open", arguments)
    assert not repeated["ok"], repeated
    assert len(processes) == 1
