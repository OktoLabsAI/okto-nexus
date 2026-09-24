"""A live store's transport guarantees cannot depend on the producer's flags."""
import asyncio
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
    source = Path(__file__).resolve().parents[1] / "src/okto_nexus/migrations"
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


def stdio_create(runtime, *, enabled):
    deps, _, root, _, _, _ = runtime
    async def create():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params = StdioServerParameters(command=sys.executable,
            args=["-m", "okto_nexus.adapters.inbound.mcp.server", "--home", str(deps.config.home_dir),
                  "--feature-harness-integrations", "true" if enabled else "false"], env=stdio_environment(runtime))
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                response = await session.call_tool("message_create", {"project_root": root,
                    "from_agent_id": "caller", "subject": "writer fence fixture", "body": "isolated fixture",
                    "target": {"strategy": "direct", "agent_id": "worker"}})
                return response.structuredContent or json.loads(response.content[0].text)

    return asyncio.run(asyncio.wait_for(create(), timeout=30))


def test_feature_off_stdio_cannot_commit_unreserved_delivery_to_active_store(runtime):
    deps, _, _, peers, _, _ = runtime
    assert open_rest(runtime).status_code == 200
    response = stdio_create(runtime, enabled=False)
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
    assert open_rest(runtime).status_code == 200
    changed = client.patch("/api/v1/settings", headers={"x-api-key": operator},
        json={"feature_harness_integrations": False})
    assert changed.status_code == 200, changed.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        contract = dict(uow.connection.execute("SELECT * FROM runtime_writer_contract").fetchone())
    assert contract["required_contract"] == 1 and contract["admission_enabled"] == 0
    stale = stdio_create(runtime, enabled=True)
    assert not stale["ok"], "Cached ON producer admitted runtime work after operator disable"
    assert "runtime_writer_mode_mismatch" in json.dumps(stale), stale
    compatible = stdio_create(runtime, enabled=False)
    assert compatible["ok"], compatible
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM messages WHERE subject='writer fence fixture'").fetchone()[0] == 1
        assert not uow.connection.execute("SELECT 1 FROM delivery_outbox").fetchone()
    assert all(not peer.sent for peer in peers)


def test_compatible_stdio_still_enqueues_the_canonical_delivery(runtime):
    from test_pr34_remediation import wait_sent
    deps, _, _, peers, _, _ = runtime
    assert open_rest(runtime).status_code == 200
    response = stdio_create(runtime, enabled=True)
    assert response["ok"], response
    assert len(response["data"]["runtime_operations"]) == 1
    wait_sent(peers)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT consumer_kind FROM message_deliveries").fetchone()
        assert row["consumer_kind"] == "push"
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1


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
