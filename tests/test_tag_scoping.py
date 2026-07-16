"""Migration 013 + persistence tests for tag-based communication scoping (F1).

Covers the storage foundation: a LEGACY database (schema up to 012, agents
already registered) migrates cleanly - pre-existing agents read back with
``tags == {}`` and ``comm_scope is None`` (default-allow, nothing changes for
them); the central catalog tables exist; ``set_tags`` / ``set_comm_scope``
are full-overwrite primitives mirroring ``set_permissions`` (``None`` resets);
and deleting an UNUSED catalog key cascades its values (in-use deletion is
blocked at the application layer, tested with the catalog service).
"""

from __future__ import annotations

import shutil

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteAgentRepo
from okto_nexus.adapters.outbound.sqlite.migrations import (
    MigrationRunner,
    _default_migrations_dir,
)
from okto_nexus.config import NexusConfig


def make_factory(tmp_path) -> ConnectionFactory:
    return ConnectionFactory(NexusConfig(home_dir=tmp_path / "home"))


def migrate_up_to(tmp_path, factory: ConnectionFactory, last_version: int) -> None:
    """Apply only migrations ``001..last_version`` (a legacy on-disk schema)."""
    real_dir = _default_migrations_dir()
    partial = tmp_path / f"partial_{last_version}"
    partial.mkdir()
    for path in real_dir.glob("[0-9]*_*.sql"):
        if int(path.name.split("_", 1)[0]) <= last_version:
            shutil.copy(path, partial)
    MigrationRunner(factory, migrations_dir=partial).apply()


def table_names(factory: ConnectionFactory) -> set[str]:
    conn = factory.get_connection()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# AC0: legacy database migrates; pre-existing agents stay default-allow
# --------------------------------------------------------------------------- #
def test_migration_013_upgrades_legacy_db_with_default_allow_agents(tmp_path):
    factory = make_factory(tmp_path)
    migrate_up_to(tmp_path, factory, 12)
    repo = SqliteAgentRepo()

    # A pre-013 agent exists BEFORE the tags schema lands (raw SQL: the repo
    # itself only ever runs against a fully-migrated schema).
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "INSERT INTO agents (agent_id, role, created_at) "
            "VALUES ('legacy', 'analyst', 't0')"
        )

    applied = MigrationRunner(factory).apply()
    assert 13 in applied
    assert {"tag_keys", "tag_values"} <= table_names(factory)

    # The legacy agent reads back untouched: no tags, unrestricted scope.
    with factory.unit_of_work() as uow:
        agent = repo.get(uow, "legacy")
    assert agent is not None
    assert agent.tags == {}
    assert agent.comm_scope is None


def test_migration_013_is_idempotent_on_a_current_db(tmp_path):
    factory = make_factory(tmp_path)
    assert 13 in MigrationRunner(factory).apply()
    assert MigrationRunner(factory).apply() == []


# --------------------------------------------------------------------------- #
# set_tags / set_comm_scope: full-overwrite persistence primitives
# --------------------------------------------------------------------------- #
def test_set_tags_roundtrip_overwrite_and_reset(migrated_factory):
    repo = SqliteAgentRepo()
    with migrated_factory.unit_of_work() as uow:
        repo.upsert(uow, agent_id="a1")
        assert repo.set_tags(uow, agent_id="a1", tags={"team": ["backend"]})
        assert repo.get(uow, "a1").tags == {"team": ["backend"]}

        # Full overwrite, not a merge.
        assert repo.set_tags(uow, agent_id="a1", tags={"env": ["prod"]})
        assert repo.get(uow, "a1").tags == {"env": ["prod"]}

        # None resets to "no tags".
        assert repo.set_tags(uow, agent_id="a1", tags=None)
        assert repo.get(uow, "a1").tags == {}

        # Unknown agent: no-op, False (mirrors set_permissions).
        assert not repo.set_tags(uow, agent_id="ghost", tags={"x": ["y"]})


def test_set_comm_scope_roundtrip_overwrite_and_reset(migrated_factory):
    repo = SqliteAgentRepo()
    scope = {"outbound": {"team": ["backend"]}}
    with migrated_factory.unit_of_work() as uow:
        repo.upsert(uow, agent_id="a1")
        assert repo.set_comm_scope(uow, agent_id="a1", comm_scope=scope)
        assert repo.get(uow, "a1").comm_scope == scope

        assert repo.set_comm_scope(uow, agent_id="a1", comm_scope=None)
        assert repo.get(uow, "a1").comm_scope is None

        assert not repo.set_comm_scope(uow, agent_id="ghost", comm_scope=scope)


def test_upsert_preserves_tags_and_comm_scope(migrated_factory):
    """Re-registration (agent_register) must never clobber operator-set data."""
    repo = SqliteAgentRepo()
    with migrated_factory.unit_of_work() as uow:
        repo.upsert(uow, agent_id="a1", role="analyst")
        repo.set_tags(uow, agent_id="a1", tags={"team": ["backend"]})
        repo.set_comm_scope(
            uow, agent_id="a1", comm_scope={"outbound": {"team": ["backend"]}}
        )
        agent = repo.upsert(uow, agent_id="a1", role="dev")
    assert agent.role == "dev"
    assert agent.tags == {"team": ["backend"]}
    assert agent.comm_scope == {"outbound": {"team": ["backend"]}}


# --------------------------------------------------------------------------- #
# Catalog tables: schema behaviour (FK cascade for UNUSED keys)
# --------------------------------------------------------------------------- #
def test_deleting_a_tag_key_cascades_its_registered_values(migrated_factory):
    conn = migrated_factory.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT INTO tag_keys (key, created_at) VALUES ('team', 't0')")
        conn.execute(
            "INSERT INTO tag_values (key, value, created_at) "
            "VALUES ('team', 'backend', 't0')"
        )
        conn.execute("DELETE FROM tag_keys WHERE key = 'team'")
        rows = conn.execute("SELECT COUNT(*) FROM tag_values").fetchone()
        conn.execute("COMMIT")
    finally:
        conn.close()
    assert rows[0] == 0


def test_tag_values_require_a_registered_key(migrated_factory):
    import sqlite3

    import pytest

    conn = migrated_factory.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO tag_values (key, value, created_at) "
                "VALUES ('unregistered', 'x', 't0')"
            )
        conn.execute("ROLLBACK")
    finally:
        conn.close()
