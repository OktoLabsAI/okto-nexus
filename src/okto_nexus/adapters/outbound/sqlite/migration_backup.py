"""Consistent pre-migration snapshots without opening a runtime or migrating."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time


def _quoted(name):
    return '"' + name.replace('"', '""') + '"'


def _encoded(values):
    return json.dumps([{"blob_hex": value.hex()} if isinstance(value, bytes) else value
                       for value in values], ensure_ascii=True, separators=(",", ":")).encode()


def snapshot_inventory(connection):
    """Inspect the snapshot, never a changing source, with streaming row digests."""
    schema = connection.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
    tables = {}
    for kind, name, _, sql in schema:
        if kind != "table" or name.startswith("sqlite_"):
            continue
        columns = [row[1] for row in connection.execute("PRAGMA table_info(" + _quoted(name) + ")")]
        digest, count = hashlib.sha256(), 0
        query = "SELECT * FROM " + _quoted(name)
        if columns:
            query += " ORDER BY " + ",".join(_quoted(column) for column in columns)
        for row in connection.execute(query):
            encoded = _encoded(row)
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
            count += 1
        tables[name] = {"rows": count, "sha256": digest.hexdigest(), "columns": columns}
    migrations = []
    if "schema_migrations" in tables:
        migrations = [list(row) for row in connection.execute(
            "SELECT version,applied_at FROM schema_migrations ORDER BY version")]
    denials = {}
    if "agent_endpoints" in tables:
        denials["disabled_endpoints"] = connection.execute(
            "SELECT COUNT(*) FROM agent_endpoints WHERE enabled=0").fetchone()[0]
        denials["unapproved_endpoints"] = connection.execute(
            "SELECT COUNT(*) FROM agent_endpoints WHERE activation_state<>'approved'").fetchone()[0]
    if "agent_connection_methods" in tables:
        denials["disabled_connection_methods"] = connection.execute(
            "SELECT COUNT(*) FROM agent_connection_methods WHERE enabled=0").fetchone()[0]
    return {"user_version": connection.execute("PRAGMA user_version").fetchone()[0],
            "schema_version": connection.execute("PRAGMA schema_version").fetchone()[0],
            "schema_sha256": hashlib.sha256(_encoded(schema)).hexdigest(),
            "migration_log": migrations, "tables": tables, "denials": denials,
            "indexes": [name for kind, name, _, _ in schema if kind == "index"]}


def create_migration_backup(source, destination, *, timeout_seconds=60.0):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise ValueError("The source database must be an existing file.")
    if destination.exists():
        raise ValueError("The backup destination must not already exist.")
    if not destination.parent.is_dir():
        raise ValueError("The backup parent directory must already exist.")
    if not 0 < timeout_seconds <= 3600:
        raise ValueError("The backup timeout must be between 0 and 3600 seconds.")
    deadline = time.monotonic() + timeout_seconds
    def progress(status, remaining, total):
        if time.monotonic() >= deadline:
            raise TimeoutError("The database backup exceeded its time limit.")
    # Incomplete artifacts remain in a unique staging directory on failure.
    # Nothing replaces an operator file or reports an incomplete backup as ready.
    staging = Path(tempfile.mkdtemp(prefix=".nexus-backup-", dir=destination.parent))
    backup = staging / "nexus.db"
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as origin:
            origin.execute("BEGIN")
            source_header = {name: origin.execute("PRAGMA " + name).fetchone()[0]
                             for name in ("schema_version", "user_version")}
            with closing(sqlite3.connect(backup)) as target:
                origin.backup(target, pages=256, progress=progress, sleep=.01)
                if target.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise ValueError("The database backup failed its integrity check.")
                inventory = snapshot_inventory(target)
        sha = hashlib.sha256()
        with backup.open("r+b") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                sha.update(block)
            os.fsync(stream.fileno())
        manifest = {"format": "nexus-migration-backup-v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database": "nexus.db", "database_sha256": sha.hexdigest(),
            "source_header": source_header,
            "inventory": inventory}
        with (staging / "manifest.json").open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Exclusive directory creation prevents replacing an existing backup.
        # Publish the manifest last: a directory without it is incomplete.
        destination.mkdir()
        backup.rename(destination / "nexus.db")
        (staging / "manifest.json").rename(destination / "manifest.json")
        staging.rmdir()
        return {"status": "BACKUP_READY", "directory": str(destination),
                "database_sha256": sha.hexdigest(),
                "tables": len(inventory["tables"]),
                "latest_migration": max((row[0] for row in inventory["migration_log"]), default=0)}
    except sqlite3.Error as error:
        raise ValueError("The database backup could not be read or written.") from error
