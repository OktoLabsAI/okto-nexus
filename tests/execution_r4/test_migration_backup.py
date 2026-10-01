"""M0 public backup captures WAL state and never bootstraps or changes policy."""
import io
import json
import sqlite3

import pytest

from okto_nexus.adapters.inbound.cli.admin import run_admin
from okto_nexus.adapters.outbound.sqlite.migration_backup import snapshot_inventory


def test_backup_cli_preserves_committed_wal_snapshot_without_bootstrap(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    connection = sqlite3.connect(source)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript("""
        CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,applied_at TEXT);
        INSERT INTO schema_migrations VALUES(65,'2026-10-01');
        CREATE TABLE agents(agent_id TEXT PRIMARY KEY,api_key_hash TEXT,permissions TEXT);
        INSERT INTO agents VALUES('unchanged-agent','hash-private-marker','{"denied":true}');
        CREATE TABLE agent_endpoints(endpoint_id TEXT PRIMARY KEY,enabled INTEGER,activation_state TEXT);
        INSERT INTO agent_endpoints VALUES('unchanged-endpoint',0,'denied');
        CREATE TABLE agent_connection_methods(agent_id TEXT,method TEXT,enabled INTEGER);
        INSERT INTO agent_connection_methods VALUES('unchanged-agent','send',0);
        CREATE TABLE messages(message_id TEXT PRIMARY KEY,body BLOB);
        INSERT INTO messages VALUES('historical',X'001122FF');
        PRAGMA user_version=65;
    """)
    connection.commit()
    assert source.with_name(source.name+"-wal").stat().st_size > 0
    before = snapshot_inventory(connection)
    def forbidden(*args, **kwargs):
        raise AssertionError("Backup must not bootstrap or spawn a runtime.")
    monkeypatch.setattr("subprocess.Popen", forbidden)
    output = io.StringIO()
    destination = tmp_path / "backup"
    try:
        assert run_admin(["backup","--db-path",str(source),"--output",str(destination)],
                         out=output, deps_factory=forbidden) == 0
        report = json.loads(output.getvalue())
        assert report["status"] == "BACKUP_READY" and report["latest_migration"] == 65
        manifest = json.loads((destination/"manifest.json").read_text())
        assert manifest["source_header"] == {key: before[key] for key in ("schema_version", "user_version")}
        # SQLite backup replaces the destination schema cookie, not its DDL.
        expected = {**before, "schema_version": manifest["inventory"]["schema_version"]}
        assert manifest["inventory"] == expected
        assert "hash-private-marker" not in (destination/"manifest.json").read_text()
        assert "hash-private-marker" not in output.getvalue()
        assert snapshot_inventory(connection) == before
        restored = sqlite3.connect(destination/"nexus.db")
        try:
            assert snapshot_inventory(restored) == expected
            assert restored.execute("SELECT body FROM messages").fetchone()[0] == bytes.fromhex("001122ff")
        finally:
            restored.close()
        # Reusing a destination must fail without replacing the completed backup.
        saved = (destination/"manifest.json").read_bytes()
        assert run_admin(["backup","--db-path",str(source),"--output",str(destination)],out=io.StringIO()) == 1
        assert (destination/"manifest.json").read_bytes() == saved
    finally:
        connection.close()


@pytest.mark.parametrize("kind", ["missing", "invalid"])
def test_backup_cli_refuses_missing_or_invalid_source(tmp_path, kind, capsys):
    source = tmp_path/"source.db"
    if kind == "invalid":
        source.write_bytes(b"Not a database")
    assert run_admin(["backup","--db-path",str(source),"--output",str(tmp_path/"backup")],
                     out=io.StringIO()) == 1
    assert "BACKUP_FAILED" in capsys.readouterr().err
    assert not (tmp_path/"backup"/"manifest.json").exists()
    if kind == "missing":
        assert not source.exists()


def test_installed_cli_backs_up_complete_current_schema(tmp_path):
    import hashlib
    import subprocess
    import sys
    from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
    from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
    from okto_nexus.config import NexusConfig
    config = NexusConfig(home_dir=tmp_path/"home")
    factory = ConnectionFactory(config)
    versions = MigrationRunner(factory).apply()
    result = subprocess.run([sys.executable, "-I", "-m", "okto_nexus.adapters.inbound.cli.main", "admin", "backup",
        "--db-path", str(config.db_path), "--output", str(tmp_path/"backup")],
        cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["latest_migration"] == max(versions)
    manifest = json.loads((tmp_path/"backup"/"manifest.json").read_text())
    assert manifest["database_sha256"] == hashlib.sha256((tmp_path/"backup"/"nexus.db").read_bytes()).hexdigest()
    assert "execution_migration_map" in manifest["inventory"]["tables"]
    assert manifest["inventory"]["tables"]["execution_operations"]["rows"] == 0
