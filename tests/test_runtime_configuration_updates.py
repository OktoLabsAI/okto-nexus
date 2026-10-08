"""Operator changes invalidate prior execution authority without losing history."""
from concurrent.futures import ThreadPoolExecutor
import pytest

from test_pr34_remediation import runtime as runtime_fixture, open_rest, tool
from test_runtime_grants import issue
from test_runtime_commands import wait_close_result

runtime = runtime_fixture
















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
