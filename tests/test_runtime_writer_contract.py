"""A live store's transport guarantees cannot depend on the producer's flags."""
import subprocess
import json
import sys
import sqlite3
import shutil
from pathlib import Path

import pytest

from test_pr34_remediation import runtime as runtime_fixture, open_rest, stdio_environment

runtime = runtime_fixture


def test_writer_migration_trigger_failure_rolls_back_and_upgrade_repeats(tmp_path):
    from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
    from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
    from okto_nexus.config import NexusConfig
    from okto_nexus.errors import OktoNexusError
    from okto_nexus.adapters.outbound.sqlite.migrations import _default_migrations_dir
    source = _default_migrations_dir()
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    for path in source.glob("*.sql"):
        if int(path.name.split("_")[0]) <= 56:
            shutil.copy2(path, migrations / path.name)
    factory = ConnectionFactory(NexusConfig(home_dir=tmp_path / "store"))
    MigrationRunner(factory, migrations).apply()
    script = source / "057_runtime_writer_contract.sql"
    broken = migrations / script.name
    broken.write_text(script.read_text() + "\nINSERT INTO missing_fixture_table VALUES(1);\n")
    with pytest.raises(OktoNexusError, match="migration 57"):
        MigrationRunner(factory, migrations).apply()
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 56
        assert not uow.connection.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'runtime_writer_%'").fetchone()
    shutil.copy2(script, broken)
    assert MigrationRunner(factory, migrations).apply() == [57]
    assert MigrationRunner(factory, migrations).apply() == []
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT required_contract FROM runtime_writer_contract").fetchone()[0] == 0
        assert not uow.connection.execute("PRAGMA foreign_key_check").fetchall()


def test_future_writer_contract_cannot_be_downgraded_by_owner_start(tmp_path):
    from okto_nexus.adapters.inbound.mcp.server import bootstrap
    from okto_nexus.adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
    from okto_nexus.domain.base import iso_plus
    from okto_nexus.errors import OktoNexusError
    deps = bootstrap({}, ["--home", str(tmp_path / "store")])
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_writer_contract SET required_contract=2")
    with pytest.raises(OktoNexusError, match="runtime_writer_incompatible"):
        with deps.connection_factory.unit_of_work() as uow:
            now = deps.clock.now_iso()
            SqliteRuntimeOutboxRepo().acquire_owner(uow, owner_id="old-contract-fixture", now=now,
                lease_expires_at=iso_plus(now, 40))
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT required_contract FROM runtime_writer_contract").fetchone()[0] == 2
        assert not uow.connection.execute("SELECT 1 FROM runtime_dispatcher_owner").fetchone()


def test_preexisting_legacy_connection_is_fenced_only_after_activation(tmp_path):
    from okto_nexus.adapters.inbound.mcp.server import bootstrap
    from okto_nexus.adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
    from okto_nexus.domain.base import iso_plus
    deps = bootstrap({}, ["--home", str(tmp_path / "store")])
    legacy = sqlite3.connect(deps.config.db_path, isolation_level=None)
    try:
        legacy.execute("INSERT INTO agents(agent_id,created_at) VALUES('legacy-fixture','fixture')")
        legacy.execute("UPDATE agents SET role='before' WHERE agent_id='legacy-fixture'")
        deps.config.feature_harness_integrations = True
        with deps.connection_factory.unit_of_work() as uow:
            now = deps.clock.now_iso()
            epoch = SqliteRuntimeOutboxRepo().acquire_owner(uow, owner_id="fixture-owner", now=now,
                lease_expires_at=iso_plus(now, 40))
        assert epoch is not None
        for statement in ("UPDATE agents SET role='after' WHERE agent_id='legacy-fixture'",
                          "DELETE FROM agents WHERE agent_id='legacy-fixture'",
                          "INSERT INTO agents(agent_id,created_at) VALUES('intruder-fixture','fixture')"):
            with pytest.raises(sqlite3.IntegrityError, match="runtime_writer_incompatible"):
                legacy.execute(statement)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT role FROM agents WHERE agent_id='legacy-fixture'").fetchone()[0] == "before"
        # Disabling admission never erases the writer-version fence or history.
        deps.config.feature_harness_integrations = False
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agents SET role='compatible-maintenance' WHERE agent_id='legacy-fixture'")
        with pytest.raises(sqlite3.IntegrityError, match="runtime_writer_incompatible"):
            legacy.execute("UPDATE agents SET role='old-writer' WHERE agent_id='legacy-fixture'")
    finally:
        legacy.close()


def independent_writer_create(runtime, *, enabled):
    # Exercise the retained store fence independently of any removed transport.
    deps, _, root, _, _, caller = runtime
    response = subprocess.run([sys.executable, '-I',
        str(Path(__file__).with_name('runtime_writer_process.py').resolve())],
        input=json.dumps(dict(home=str(deps.config.home_dir), root=root, key=caller, enabled=enabled)),
        cwd=root, env=stdio_environment(runtime), capture_output=True, text=True, timeout=30)
    assert response.returncode == 0, response.stderr
    return json.loads(response.stdout)


def test_feature_off_writer_cannot_commit_unreserved_delivery_to_active_store(runtime):
    deps, _, _, peers, _, _ = runtime
    response = independent_writer_create(runtime, enabled=False)
    assert not response["ok"], "Feature-OFF producer committed outside the active store's runtime admission"
    assert "runtime_writer_mode_mismatch" in json.dumps(response), response
    assert response["error"]["code"] == "CONFIG_ERROR" and not response["error"].get("retryable", False)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute("SELECT 1 FROM messages WHERE subject='writer fence fixture'").fetchone()
        assert not uow.connection.execute("SELECT 1 FROM message_deliveries").fetchone()
        assert not uow.connection.execute("SELECT 1 FROM delivery_outbox").fetchone()
    assert all(not peer.sent for peer in peers)


@pytest.mark.parametrize("runtime", ["stored_runtime"], indirect=True)
def test_operator_disable_changes_writer_mode_atomically_and_retains_fences(runtime):
    deps, client, _, peers, operator, _ = runtime
    changed = client.patch("/api/v1/settings", headers={"x-api-key": operator},
        json={"feature_harness_integrations": False})
    assert changed.status_code == 200, changed.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        contract = dict(uow.connection.execute("SELECT * FROM runtime_writer_contract").fetchone())
    assert contract["required_contract"] == 1 and contract["admission_enabled"] == 0
    stale = independent_writer_create(runtime, enabled=True)
    assert not stale["ok"], "Cached ON producer admitted runtime work after operator disable"
    assert "runtime_writer_mode_mismatch" in json.dumps(stale), stale
    compatible = independent_writer_create(runtime, enabled=False)
    assert compatible["ok"], compatible
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM messages WHERE subject='writer fence fixture'").fetchone()[0] == 1
        assert not uow.connection.execute("SELECT 1 FROM delivery_outbox").fetchone()
    assert all(not peer.sent for peer in peers)




def test_writer_contract_diagnostics_are_operator_only(runtime):
    from test_pr34_remediation import tool
    deps, client, _, _, operator, caller = runtime
    response = client.get("/api/v1/harness/diagnostics", headers={"x-api-key": operator})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["writer_contract"] == {"required_contract": 1, "admission_enabled": 1}
    assert client.get("/api/v1/harness/diagnostics", headers={"x-api-key": caller}).status_code == 403
    mcp = tool(client, operator, "harness_list", {"view": "diagnostics"})
    assert mcp["ok"] and mcp["data"] == response.json()["data"], mcp
    denied = tool(client, caller, "harness_list", {"view": "diagnostics"})
    assert not denied["ok"] and denied["error"]["code"] == "PERMISSION_DENIED", denied
