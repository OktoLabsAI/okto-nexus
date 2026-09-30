"""Offline, operator-run recovery procedure; never starts Nexus or a native peer.

Requires a quiesced schema-057 store and explicit acknowledgement that all its
writers/native owners have stopped. Copies only the DB, journal and artifacts.
The backup contains private store data; protect it like the original home.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3

from okto_nexus.adapters.outbound.harness.event_journal import FileRuntimeEventJournal


def safe_path(root):
    root = Path(root).absolute()
    for parent in (root, *root.parents):
        if parent.is_symlink() or (parent.exists() and getattr(parent.lstat(), "st_file_attributes", 0) & 0x400):
            raise ValueError("Recovery paths cannot redirect through links or reparse points")
    return root


def regular_tree(root):
    root = safe_path(root)
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
            raise ValueError("Recovery tree contains a redirected path")
        if path.is_file():
            FileRuntimeEventJournal._regular(path)
            yield path
        elif not path.is_dir():
            raise ValueError("Recovery tree contains a nonregular entry")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(root):
    return {p.relative_to(root).as_posix(): {"bytes": p.stat().st_size, "sha256": digest(p)}
            for p in regular_tree(root) if p.relative_to(root).as_posix() not in
            {"runtime-journal-v1/writer.lock", "backup-manifest.json"}}


def sync_tree(root):
    for path in regular_tree(root):
        with path.open("r+b") as stream:
            os.fsync(stream.fileno())
    if os.name == "posix":
        for path in [*sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True), root, root.parent]:
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)


@contextmanager
def journal_lock(home):
    path = home / "runtime-journal-v1" / "writer.lock"
    FileRuntimeEventJournal._regular(path)
    with path.open("r+b", buffering=0) as stream:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def database_report(db):
    if [row[0] for row in db.execute("PRAGMA integrity_check")] != ["ok"]:
        raise ValueError("SQLite integrity check failed")
    if db.execute("PRAGMA foreign_key_check").fetchone():
        raise ValueError("SQLite foreign key check failed")
    checkpoint = db.execute("SELECT store_id,ordinal FROM runtime_journal_checkpoint WHERE singleton=1").fetchone()
    agents = [tuple(row) for row in db.execute("SELECT * FROM agents ORDER BY agent_id")]
    return {"checkpoint": list(checkpoint) if checkpoint else None,
            "schema_versions": [row[0] for row in db.execute("SELECT version FROM schema_migrations ORDER BY version")],
            "agent_profile_sha256": hashlib.sha256(json.dumps(agents, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest(),
            "counts": {table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                       for table in ("agents", "agent_endpoints", "harness_sessions", "messages", "message_deliveries",
                                     "handoffs", "delivery_outbox", "runtime_commands", "runtime_results", "artifacts")}}


def validate(snapshot):
    snapshot = safe_path(snapshot)
    list(regular_tree(snapshot))
    manifest = json.loads((snapshot / "backup-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != 1 or inventory(snapshot) != manifest["files"]:
        raise ValueError("Backup inventory/checksum mismatch")
    with sqlite3.connect((snapshot / "nexus.db").as_uri() + "?mode=ro", uri=True) as db:
        if database_report(db) != manifest["database"]:
            raise ValueError("Backup database metadata mismatch")
        for storage_path, size in db.execute("SELECT storage_path,size_bytes FROM artifacts WHERE storage_path IS NOT NULL"):
            payload = snapshot / "artifacts" / storage_path
            if not payload.resolve().is_relative_to((snapshot / "artifacts").resolve()) or not payload.is_file():
                raise ValueError("Referenced artifact is missing or outside the snapshot")
            if payload.stat().st_size != size or not (payload.parent / "manifest.json").is_file():
                raise ValueError("Referenced artifact bytes/manifest mismatch")
    journal = FileRuntimeEventJournal(snapshot)
    try:
        journal.start(repair_tail=False)
        checkpoint = manifest["database"]["checkpoint"]
        state = journal.diagnostics()
        if state["tail_repairs"] or state["store_id"] != manifest["journal"]["store_id"]:
            raise ValueError("Journal snapshot required repair or changed identity")
        if state["watermark"] != manifest["journal"]["watermark"]:
            raise ValueError("Journal watermark mismatch")
        ordinal = checkpoint[1] if checkpoint else 0
        if checkpoint and checkpoint[0] != state["store_id"]:
            raise ValueError("Database/journal identity mismatch")
        if not state["retained_after"] <= ordinal <= state["watermark"]:
            raise ValueError("Database checkpoint is outside the retained journal")
    finally:
        journal.close()
    if inventory(snapshot) != manifest["files"]:
        raise ValueError("Snapshot changed during validation")
    return manifest


def backup(home, destination, *, stopped=False, db_path=None):
    if not stopped:
        raise ValueError("Explicit acknowledgement of stopped writers and native owners is required")
    home, destination = safe_path(home), safe_path(destination)
    database = safe_path(db_path) if db_path is not None else home / "nexus.db"
    FileRuntimeEventJournal._regular(database)
    if destination.resolve().is_relative_to(home.resolve()):
        raise ValueError("Backup destination must be outside the source home")
    list(regular_tree(home))
    if destination.exists():
        raise FileExistsError("Backup destination already exists; refusing overwrite")
    # These are exclusion locks, not permission to stop another process. The
    # operator must first stop every writer, including artifact maintenance.
    with journal_lock(home), sqlite3.connect(database.as_uri() + "?mode=rw", uri=True, timeout=1) as fence:
        fence.execute("BEGIN IMMEDIATE")
        owner = fence.execute("SELECT lease_expires_at FROM runtime_dispatcher_owner WHERE owner_key='dispatcher'").fetchone()
        if owner and datetime.fromisoformat(owner[0].replace("Z", "+00:00")) > datetime.now(timezone.utc):
            raise ValueError("Runtime owner lease is still live; stop the owner before backup")
        destination.mkdir(mode=0o700, parents=False)
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as reader:
            with sqlite3.connect(destination / "nexus.db") as target:
                reader.backup(target)
                report = database_report(target)
        for name in ("runtime-journal-v1", "artifacts"):
            if (home / name).exists():
                shutil.copytree(home / name, destination / name,
                    ignore=shutil.ignore_patterns("writer.lock") if name == "runtime-journal-v1" else None)
        # Release no source lock until every referenced file has been copied.
        fence.rollback()
    journal = FileRuntimeEventJournal(destination)
    try:
        journal.start(repair_tail=False)
        state = journal.diagnostics()
        if state["tail_repairs"]:
            raise ValueError("Source journal has an incomplete tail; preserve and reconcile it before backup")
    finally:
        journal.close()
    manifest = {"version": 1, "database": report, "journal": state, "files": inventory(destination)}
    sync_tree(destination)
    (destination / "backup-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    validate(destination)
    sync_tree(destination)
    return manifest


def restore(snapshot, destination, *, stopped=False):
    if not stopped:
        raise ValueError("Confirm the original writers/native owners have stopped before restoring")
    snapshot, destination = safe_path(snapshot), safe_path(destination)
    validate(snapshot)
    if destination.exists() or destination.resolve().is_relative_to(snapshot.resolve()):
        raise FileExistsError("Restore requires a new directory outside the backup")
    shutil.copytree(snapshot, destination)
    validate(destination)
    sync_tree(destination)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("backup", "validate", "restore"))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path, nargs="?")
    parser.add_argument("--all-writers-and-native-owners-stopped", action="store_true")
    parser.add_argument("--db-path", type=Path, help="Explicit source DB override for backup; restored DB is always nexus.db")
    args = parser.parse_args()
    if args.action == "validate":
        validate(args.source)
    else:
        if args.destination is None:
            parser.error("destination is required")
        if args.action == "backup":
            backup(args.source, args.destination, stopped=args.all_writers_and_native_owners_stopped, db_path=args.db_path)
        else:
            if args.db_path is not None:
                parser.error("--db-path applies only to backup")
            restore(args.source, args.destination, stopped=args.all_writers_and_native_owners_stopped)
    print(json.dumps({"status": "PASS", "action": args.action, "native_processes_started": 0}))
