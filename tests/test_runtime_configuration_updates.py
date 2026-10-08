"""Operator changes invalidate prior execution authority without losing history."""
from concurrent.futures import ThreadPoolExecutor
import pytest

from test_pr34_remediation import runtime as runtime_fixture, open_rest, tool
from test_runtime_grants import issue
from test_runtime_commands import wait_close_result

runtime = runtime_fixture


def test_profile_disable_fences_send_preserves_session_and_allows_operator_close(runtime):
    deps, client, _, peers, operator, caller = runtime
    session = open_rest(runtime).json()["data"]["session_id"]
    grant = issue(runtime, ["send", "open"])
    headers = {"x-api-key": operator}
    before = client.get("/api/v1/agents/worker", headers=headers).json()
    updated = client.patch("/api/v1/harness/profiles/profile-pi", headers=headers,
        json={"expected_revision": 1, "enabled": False})
    assert updated.status_code == 200, updated.text
    for key in (caller, operator):
        denied = tool(client, key, "harness_send", {"session_id": session, "payload": {"text": "must not execute"}})
        assert not denied["ok"] and denied["error"]["code"] == "PERMISSION_DENIED", denied
    assert not peers[0].sent
    assert client.get("/api/v1/agents/worker", headers=headers).json() == before
    closed = tool(client, operator, "harness_close", {"session_id": session})
    assert closed["ok"], closed
    wait_close_result(client, operator, closed)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT revoked_at FROM runtime_execution_grants WHERE grant_id=?", (grant["grant_id"],)).fetchone()[0]
        assert uow.connection.execute("SELECT count(*) FROM harness_sessions WHERE session_id=?", (session,)).fetchone()[0] == 1














def test_configuration_audit_upgrade_preserves_old_access_rows(tmp_path):
    import shutil
    from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner, _default_migrations_dir
    from test_migrations import make_factory
    old = tmp_path / "schema52"
    old.mkdir()
    for migration in _default_migrations_dir().glob("*.sql"):
        if int(migration.name.split("_", 1)[0]) <= 52:
            shutil.copy(migration, old)
    factory = make_factory(tmp_path)
    MigrationRunner(factory, migrations_dir=old).apply()
    with factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO runtime_access_audit(request_id,action,decision,created_at) VALUES('legacy-audit','read','deny','2026-09-23T00:00:00Z')")
    assert MigrationRunner(factory).apply()[0] == 53
    assert MigrationRunner(factory).apply() == []
    with factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT * FROM runtime_access_audit WHERE request_id='legacy-audit'").fetchone()
        assert row["action"] == "read" and row["decision"] == "deny"
        assert row["resource_kind"] is None and row["old_revision"] is None
        assert not uow.connection.execute("SELECT 1 FROM delivery_outbox").fetchone()
        assert uow.connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_profile_disable_preserves_late_native_terminal_without_publishing(runtime):
    from test_pr34_remediation import send_message
    from test_runtime_commands import codex_session, wait_operation
    from test_runtime_result_publication import result
    deps, client, _, _, operator, _ = runtime
    session = codex_session(runtime)
    source = send_message(runtime, body="TRIGGER_HOLD")
    operation = source["runtime_operations"][0]
    wait_operation(runtime, operation, lambda row: row["external_acceptance"] == "observed")
    response = client.patch("/api/v1/harness/profiles/profile-codex", headers={"x-api-key": operator},
        json={"expected_revision": 1, "enabled": False})
    assert response.status_code == 200, response.text
    interrupted = tool(client, operator, "harness_interrupt", {"session_id": session, "expected_operation_id": operation})
    assert interrupted["ok"], interrupted
    wait_operation(runtime, operation, lambda row: row["result_durable"])
    captured = result(runtime, operation, "BLOCKED")
    assert captured["delivery_outcome"] == "interrupted" and not captured["publication_message_id"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
        assert uow.connection.execute("SELECT count(*) FROM harness_events WHERE operation_id=? AND delivery_phase='terminal'", (operation,)).fetchone()[0] == 1
