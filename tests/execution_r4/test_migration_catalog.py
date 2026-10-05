"""Interrupted catalog batches preserve legacy policy, identifiers and history."""
import io
import json
import shutil

import pytest

from okto_nexus.adapters.inbound.cli.admin import run_admin
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner, _default_migrations_dir
from okto_nexus.adapters.outbound.sqlite.migration_backup import create_migration_backup
from okto_nexus.config import NexusConfig


@pytest.fixture
def legacy(tmp_path):
    old = tmp_path/"old-schema"
    old.mkdir()
    for path in _default_migrations_dir().glob("*.sql"):
        if int(path.name.split("_",1)[0]) <= 65:
            shutil.copy2(path, old/path.name)
    config = NexusConfig(home_dir=tmp_path/"home")
    factory = ConnectionFactory(config)
    MigrationRunner(factory, old).apply()
    with factory.unit_of_work() as uow:
        c = uow.connection
        c.execute("INSERT INTO agents(agent_id,created_at,api_key_hash) VALUES ('agent','2026-10-01','retained-hash')")
        c.execute("INSERT INTO workspaces(workspace_id,created_at) VALUES ('workspace','2026-10-01')")
        for index, adapter in enumerate(("codex","pi","claude_code.stream","claude_code.attach","mcp","unknown-native")):
            c.execute("INSERT INTO runtime_profiles(profile_id,adapter_id,config,created_at,updated_at) VALUES (?,?,?,? ,?)",
                      (str(index),adapter,'{"command":"untrusted legacy command"}',"2026-10-01","2026-10-01"))
            c.execute("INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,adapter_id,protocol,profile_id,"
                      "enabled,activation_state,created_at,updated_at) VALUES (?,'agent','workspace',?,'legacy',?,0,'denied','2026-10-01','2026-10-01')",
                      (str(index),adapter,str(index)))
        c.execute("INSERT INTO agent_connection_methods VALUES ('agent','codex',0)")
    backup = tmp_path/"backup"
    create_migration_backup(config.db_path, backup)
    return config, factory, backup


def migrate(legacy, batch_size=3):
    config, _, backup = legacy
    output = io.StringIO()
    code = run_admin(["migrate-execution","--db-path",str(config.db_path),
                      "--backup",str(backup),"--batch-size",str(batch_size)], out=output)
    return code, json.loads(output.getvalue()) if output.getvalue() else None


def test_catalog_batches_resume_twice_without_mutating_legacy_rows(legacy, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Migration must not spawn processes.")
    monkeypatch.setattr("subprocess.Popen", forbidden)
    assert migrate(legacy)[1]["processed"] == 3
    assert migrate(legacy)[1]["processed"] == 3
    assert migrate(legacy)[1]["processed"] == 3
    code, report = migrate(legacy, 100)
    assert code == 0 and report["status"] == "CATALOG_BACKFILL_COMPLETE"
    config, factory, _ = legacy
    with factory.unit_of_work(write=False) as uow:
        before = [dict(r) for r in uow.connection.execute("SELECT * FROM execution_migration_map ORDER BY source_type,legacy_id")]
        assert len(before) == 13
        states = {r["legacy_id"]: r["state"] for r in before if r["source_type"] == "agent_endpoints"}
        assert states == {"0":"REDISCOVERY_REQUIRED","1":"REDISCOVERY_REQUIRED",
            "2":"REDISCOVERY_REQUIRED","3":"REDISCOVERY_REQUIRED","4":"TOOLS_ONLY","5":"MIGRATION_REVIEW_REQUIRED"}
        refs = [json.loads(r["canonical_ref"]) for r in before if r["source_type"] == "agent_endpoints"]
        assert all(r["workspace_id"] == "workspace" and r["agent_id"] == "agent" for r in refs)
        assert {r["canonical_adapter_id"] for r in refs} == {"codex_app_server","pi_rpc","claude_stream","claude_attach",None}
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_bindings").fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM agent_endpoints WHERE enabled=0 AND activation_state='denied'").fetchone()[0] == 6
        assert uow.connection.execute("SELECT api_key_hash FROM agents").fetchone()[0] == "retained-hash"
    for _ in range(2):
        assert migrate(legacy)[1]["processed"] == 0
    with factory.unit_of_work(write=False) as uow:
        assert [dict(r) for r in uow.connection.execute("SELECT * FROM execution_migration_map ORDER BY source_type,legacy_id")] == before


def test_source_drift_refuses_next_batch_without_recording_more_rows(legacy):
    assert migrate(legacy)[0] == 0
    _, factory, _ = legacy
    with factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_profiles SET config='{}' WHERE profile_id='0'")
    assert migrate(legacy)[0] == 1
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_migration_map").fetchone()[0] == 3


def test_tampered_backup_refuses_schema_expansion(legacy):
    _, factory, backup = legacy
    with (backup/"nexus.db").open("ab") as stream:
        stream.write(b"tampered")
    assert migrate(legacy)[0] == 1
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 65


def test_interrupted_batch_rolls_back_and_resumes(legacy):
    _, factory, _ = legacy
    MigrationRunner(factory).apply()
    with factory.unit_of_work() as uow:
        uow.connection.execute("""CREATE TRIGGER fail_migration_batch BEFORE INSERT ON execution_migration_map
            WHEN NEW.legacy_id='1' BEGIN SELECT RAISE(ABORT,'injected batch failure'); END""")
    assert migrate(legacy)[0] == 1
    with factory.unit_of_work() as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_migration_map").fetchone()[0] == 0
        uow.connection.execute("DROP TRIGGER fail_migration_batch")
    assert migrate(legacy)[1]["processed"] == 3
    assert migrate(legacy)[1]["processed"] == 3
    assert migrate(legacy,100)[1]["status"] == "CATALOG_BACKFILL_COMPLETE"


def test_legacy_denial_is_materialized_in_canonical_binding_policy(legacy):
    from okto_nexus.application.execution_binding_proposals import _require_binding_method
    from okto_nexus.errors import OktoNexusError
    assert migrate(legacy, 1)[1]["processed"] == 1
    _, factory, _ = legacy
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT enabled FROM agent_connection_methods WHERE method='codex'").fetchone()[0] == 0
        with pytest.raises(OktoNexusError, match="Connection method is disabled"):
            _require_binding_method(uow.connection, subject_agent_id="agent", adapter_id="codex_app_server")
    assert migrate(legacy, 100)[1]["status"] == "CATALOG_BACKFILL_COMPLETE"
    with factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_connection_methods SET enabled=1 WHERE method='codex_app_server'")
    assert migrate(legacy, 100)[0] == 1


def test_conflicting_canonical_allow_requires_review(legacy, tmp_path):
    config, factory, _ = legacy
    with factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO agent_connection_methods VALUES ('agent','codex_app_server',1)")
    backup = tmp_path/"with-conflict"
    create_migration_backup(config.db_path, backup)
    assert migrate((config,factory,backup),100)[0] == 1
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_migration_map").fetchone()[0] == 0
        assert uow.connection.execute("SELECT enabled FROM agent_connection_methods WHERE method='codex_app_server'").fetchone()[0] == 1


def test_policy_backfill_refuses_live_runtime_owner(legacy, tmp_path):
    from datetime import datetime, timedelta, timezone
    config, factory, _ = legacy
    with factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO runtime_dispatcher_owner(owner_key,epoch,owner_id,lease_expires_at) VALUES('dispatcher',1,'live-owner',?)",
                               ((datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),))
    backup = tmp_path/"live-backup"
    create_migration_backup(config.db_path, backup)
    assert migrate((config,factory,backup),100)[0] == 1
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 65
        assert uow.connection.execute("SELECT COUNT(*) FROM agent_connection_methods").fetchone()[0] == 1
