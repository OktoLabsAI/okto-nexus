"""Operator recovery preserves uncertain transport facts and canonical inbox."""
from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, tool
from test_runtime_commands import wait_close_result
from test_runtime_outbox import wait_status
from okto_nexus.application.auth import AgentKeyAuthService
import pytest
import threading
from concurrent.futures import ThreadPoolExecutor
import time

runtime = runtime_fixture


def uncertain_delivery(runtime):
    _, client, _, _, operator, _ = runtime
    session = open_rest(runtime).json()["data"]["session_id"]
    sent = send_message(runtime, body="Exactly one logical fixture delivery")
    operation = sent["runtime_operations"][0]
    wait_status(runtime, operation, "SENT_UNCONFIRMED")
    wait_close_result(client, operator, tool(client, operator, "harness_close", {"session_id": session}))
    return sent, wait_status(runtime, operation, "OUTCOME_UNKNOWN")


def recovery(row, **changes):
    return {"action": "release_to_inbox", "operation_id": row["operation_id"],
            "expected_state": row["status"], "expected_attempt_id": row["attempt_id"],
            "expected_owner_epoch": row["owner_epoch"], "idempotency_key": "fixture-takeover",
            "reason": "Operator reviewed isolated uncertain fixture", "acknowledge_duplicate_risk": True, **changes}


























def test_reconciliation_migration_is_additive_and_repeatable(tmp_path):
    import shutil
    from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner, _default_migrations_dir
    from test_migrations import make_factory
    old = tmp_path / "schema53"
    old.mkdir()
    for migration in _default_migrations_dir().glob("*.sql"):
        if int(migration.name.split("_", 1)[0]) <= 53:
            shutil.copy(migration, old)
    factory = make_factory(tmp_path)
    MigrationRunner(factory, migrations_dir=old).apply()
    with factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO runtime_access_audit(request_id,action,decision,created_at) VALUES('previous','read','deny','2026-09-23T00:00:00Z')")
    expected = sorted(int(p.name.split('_', 1)[0]) for p in _default_migrations_dir().glob('*.sql') if int(p.name.split('_', 1)[0]) > 53)
    assert MigrationRunner(factory).apply() == expected
    assert MigrationRunner(factory).apply() == []
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT decision FROM runtime_access_audit WHERE request_id='previous'").fetchone()[0] == "deny"
        for table in ("delivery_outbox", "runtime_commands"):
            assert "reconciliation_id" in {row["name"] for row in uow.connection.execute(f"PRAGMA table_info({table})")}
        assert uow.connection.execute("SELECT count(*) FROM runtime_operation_reconciliations").fetchone()[0] == 0
        assert uow.connection.execute("PRAGMA foreign_key_check").fetchall() == []
