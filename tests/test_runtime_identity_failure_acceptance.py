"""Canonical catalogue gates and owned-process cleanup after partial startup."""
import sqlite3
import sys

import pytest

from legacy_native_fixture.codex import CodexAppServerConnector
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
