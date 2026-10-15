"""Existing intent journals survive the additive reuse migration unchanged."""
import shutil

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner, _default_migrations_dir
from okto_nexus.config import NexusConfig


def test_upgrade_088_preserves_original_intent_and_is_idempotent(tmp_path):
    migrations = _default_migrations_dir()
    old = tmp_path / "schema088"
    old.mkdir()
    for path in migrations.glob("*.sql"):
        if int(path.name.split("_", 1)[0]) <= 88:
            shutil.copyfile(path, old / path.name)
    factory = ConnectionFactory(NexusConfig(home_dir=tmp_path / "home"))
    assert MigrationRunner(factory, old).apply()[-1] == 88
    conn = factory.get_connection()
    try:
        conn.execute("INSERT INTO agents(agent_id,created_at) VALUES ('actor','2026-10-01T00:00:00Z')")
        conn.execute(
            "INSERT INTO execution_client_intents(server_id,actor_agent_id,client_intent_id,"
            "body_hash,intent_id,operation_id,resolution_revision,resolved_json,created_at,source_guard_digest)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("server", "actor", "client", "body-digest", "intent", "opening", 1,
             '{"operation_id":"opening","reuse":false}', "2026-10-01T00:00:00Z", "source-digest"),
        )
        conn.commit()
        before = dict(conn.execute("SELECT * FROM execution_client_intents").fetchone())
    finally:
        conn.close()
    assert MigrationRunner(factory).apply() == sorted(int(path.name.split("_", 1)[0])
        for path in migrations.glob("*.sql") if int(path.name.split("_", 1)[0]) > 88)
    assert MigrationRunner(factory).apply() == []
    conn = factory.get_connection()
    try:
        after = dict(conn.execute("SELECT * FROM execution_client_intents").fetchone())
        assert after == {**before, "session_selection": "explicit", "reuse_admitted_at": None, "initial_turn_json": None, "actor_guard_digest": None}
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=89").fetchone()[0] == 1
    finally:
        conn.close()
