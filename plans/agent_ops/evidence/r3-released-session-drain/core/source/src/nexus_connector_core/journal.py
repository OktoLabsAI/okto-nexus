"""Local SQLite technical journal with honest effect uncertainty.

The journal records intention before the native side effect. An interrupted
SUBMISSION_STARTED record is never automatically replayed.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import AsyncIterator

from .models import (ClaimedSession, CoreError, EventCursor, OperationKey,
                     OwnedSlotPage, OwnedSlotReservation, OwnedSlotState,
                     OperationReceipt, ProcessBirthEvidence,
                     ProcessBirthRecord, RuntimeEvent, SessionClaimPage,
                     SessionLeaseState, SessionKey, StorageStatus)
from .offloop import (ExecutorClosed, ExecutorFull, OffLoopExecutor)
from .protocol import canonical_json
from .process_launch_storage import PROCESS_LAUNCH_SCHEMA, ProcessLaunchStorageMixin


@dataclass(frozen=True, slots=True)
class JournalLimits:
    max_storage_bytes: int = 256 * 1024 * 1024
    reserved_storage_bytes: int = 16 * 1024 * 1024
    max_wal_bytes: int = 64 * 1024 * 1024
    reserved_wal_bytes: int = 4 * 1024 * 1024
    total_event_bytes: int = 256 * 1024 * 1024
    reserved_event_bytes: int = 16 * 1024 * 1024
    server_event_bytes: int = 256 * 1024 * 1024
    server_reserved_bytes: int = 16 * 1024 * 1024
    session_event_bytes: int = 32 * 1024 * 1024
    session_reserved_bytes: int = 1024 * 1024
    total_event_rows: int = 1_000_000
    reserved_event_rows: int = 10_000
    server_event_rows: int = 1_000_000
    server_reserved_rows: int = 10_000
    session_event_rows: int = 50_000
    session_reserved_rows: int = 1_000
    # Durable source may exceed the inline wire limit. Publishers externalize
    # its payload to the artifact store before acknowledging this journal.
    max_event_body_bytes: int = 16 * 1024 * 1024 + 64 * 1024
    max_operation_rows: int = 100_000
    reserved_operation_rows: int = 1_000
    server_operation_rows: int = 50_000
    server_reserved_operation_rows: int = 500
    session_operation_rows: int = 10_000
    session_reserved_operation_rows: int = 100
    max_owned_slots: int = 8

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if type(value) is not int or value > 9223372036854775807:
                raise ValueError(f"invalid journal limit: {field.name}")
        for maximum, reserve in (
            (self.max_storage_bytes, self.reserved_storage_bytes),
            (self.max_wal_bytes, self.reserved_wal_bytes),
            (self.total_event_bytes, self.reserved_event_bytes),
            (self.server_event_bytes, self.server_reserved_bytes),
            (self.session_event_bytes, self.session_reserved_bytes),
            (self.total_event_rows, self.reserved_event_rows),
            (self.server_event_rows, self.server_reserved_rows),
            (self.session_event_rows, self.session_reserved_rows),
        ):
            if maximum <= 0 or reserve < 0 or reserve >= maximum:
                raise ValueError("invalid journal quota/reserve")
        if (self.max_event_body_bytes <= 0 or self.max_operation_rows <= 0 or
                self.reserved_operation_rows < 0 or
                self.reserved_operation_rows >= self.max_operation_rows or
                self.server_operation_rows <= 0 or
                self.server_reserved_operation_rows < 0 or
                self.server_reserved_operation_rows >= self.server_operation_rows or
                self.session_operation_rows <= 0 or
                self.session_reserved_operation_rows < 0 or
                self.session_reserved_operation_rows >= self.session_operation_rows or
                self.max_owned_slots <= 0):
            raise ValueError("invalid journal item limit")


_CRITICAL_EVENT_CATEGORIES = frozenset({
    "lifecycle", "turn_state", "approval_request", "input_request",
    "error", "system_warning", "rate_limit",
})
_REPLAY_PAGE_ROWS = 128
MAX_COMPACTION_ROWS = 4096
MAX_CLAIM_PAGE_ROWS = 4096
_TERMINAL_STAGES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED"})
_STAGE_TRANSITIONS = {
    "RECEIVED_DURABLE": {"PREPARED", "SUBMISSION_STARTED", "FAILED"},
    "PREPARED": {"SUBMISSION_STARTED", "FAILED"},
    "SUBMISSION_STARTED": {"SUBMITTED", "ACCEPTED", "RUNNING", "WAITING_INPUT",
                           "OUTCOME_UNKNOWN", *_TERMINAL_STAGES},
    "SUBMITTED": {"ACCEPTED", "RUNNING", "WAITING_INPUT", "OUTCOME_UNKNOWN",
                  *_TERMINAL_STAGES},
    "ACCEPTED": {"RUNNING", "WAITING_INPUT", "OUTCOME_UNKNOWN", *_TERMINAL_STAGES},
    "RUNNING": {"WAITING_INPUT", "OUTCOME_UNKNOWN", *_TERMINAL_STAGES},
    "WAITING_INPUT": {"RUNNING", "OUTCOME_UNKNOWN", *_TERMINAL_STAGES},
    "OUTCOME_UNKNOWN": {"SUBMITTED", "ACCEPTED", "RUNNING", "WAITING_INPUT",
                        *_TERMINAL_STAGES},
    "SUCCEEDED": set(), "FAILED": set(), "CANCELLED": set(),
}
_EARLY_STAGES = frozenset({"RECEIVED_DURABLE", "PREPARED", "SUBMISSION_STARTED",
                           "SUBMITTED", "ACCEPTED"})
_EARLY_RANK = {stage: rank for rank, stage in enumerate((
    "RECEIVED_DURABLE", "PREPARED", "SUBMISSION_STARTED", "SUBMITTED", "ACCEPTED"))}


def validate_compaction_rows(max_rows: int) -> None:
    if type(max_rows) is not int or not 1 <= max_rows <= MAX_COMPACTION_ROWS:
        raise ValueError(f"max_rows must be an integer from 1 to {MAX_COMPACTION_ROWS}")


def validate_claim_page(after_rowid: int, high_water_rowid: int | None,
                        limit: int, *, label: str = "session-claim") -> None:
    if (type(limit) is not int or not 1 <= limit <= MAX_CLAIM_PAGE_ROWS or
            type(after_rowid) is not int or not 0 <= after_rowid <= 9223372036854775807 or
            (high_water_rowid is not None and (
                type(high_water_rowid) is not int or
                not after_rowid <= high_water_rowid <= 9223372036854775807))):
        raise ValueError(f"invalid {label} page")


def validate_claim_namespace(server_id: str, executor_id: str) -> None:
    if (not isinstance(server_id, str) or not server_id or
            not isinstance(executor_id, str) or not executor_id):
        raise ValueError("invalid session-claim namespace")


def validate_process_birth(evidence: ProcessBirthEvidence) -> None:
    valid_kinds = {("win32", "windows_job"),
                   ("linux", "linux_guardian"),
                   ("darwin", "darwin_launchd_coalition")}
    if (not isinstance(evidence, ProcessBirthEvidence) or
            type(evidence.platform) is not str or
            type(evidence.containment) is not str or
            (evidence.platform, evidence.containment) not in valid_kinds or
            type(evidence.pid) is not int or not 1 <= evidence.pid <= 4294967295 or
            type(evidence.birth_token) is not str or
            not 1 <= len(evidence.birth_token) <= 160):
        raise ValueError("invalid owned process birth evidence")
    if evidence.container_id is not None:
        import re
        pattern = {'win32': r'Global\\nexus-core-[0-9a-f]{32}',
                   'linux': r'linux-guardian:[0-9a-f]{32}',
                   'darwin': r'darwin-launchd:ai\.oktolabs\.nexus-owned\.[0-9]+\.[0-9a-f]{16}'}.get(evidence.platform)
        if (pattern is None or type(evidence.container_id) is not str or
                re.fullmatch(pattern, evidence.container_id) is None):
            raise ValueError("invalid owned process container")


def _sqlite_full(error: BaseException) -> bool:
    return (isinstance(error, sqlite3.Error) and
            getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_FULL)


async def open_journal(path, *, limits: "JournalLimits | None" = None)         -> "SQLiteJournal":
    """Async construction entry for the SQLite journal (PC01.06, C2/R-§6).

    ``SQLiteJournal.__init__`` performs blocking setup (open, schema,
    worker start). Hosts running inside an event loop should construct
    through this entry, which performs the same setup off the loop; the
    resulting journal is identical. Closing stays ``aclose()``.
    """
    import asyncio
    return await asyncio.to_thread(SQLiteJournal, path, limits=limits)


class SQLiteJournal(ProcessLaunchStorageMixin):
    def __init__(self, path: str | Path, *, limits: JournalLimits | None = None):
        self.path = str(path)
        if limits is not None and not isinstance(limits, JournalLimits):
            raise TypeError("limits must be JournalLimits")
        self.limits = limits if limits is not None else JournalLimits()
        self._executor = OffLoopExecutor(name="core-journal-worker")
        self._has_legacy_operations = False
        self._storage_identity = None
        self._executor.start(self._open_database)

    def _open_database(self):
        """Worker-side setup: the connection lives on the executor thread."""
        db = sqlite3.connect(self.path, isolation_level=None, timeout=5)
        deadline = time.monotonic() + 5
        while True:
            try:
                mode = db.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            except sqlite3.OperationalError as exc:
                busy = ((getattr(exc, "sqlite_errorcode", 0) or 0) & 0xFF) in {
                    sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
                if not busy or time.monotonic() >= deadline:
                    db.close()
                    raise
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
                continue
            if mode.lower() != "wal" and self.path != ":memory:":
                db.close()
                raise CoreError("JOURNAL_UNAVAILABLE", "journal_open")
            break
        db.execute("PRAGMA synchronous=FULL")
        page_size = db.execute("PRAGMA page_size").fetchone()[0]
        max_pages = max(1, self.limits.max_storage_bytes // page_size)
        db.execute(f"PRAGMA max_page_count={max_pages}")
        db.execute(
            f"PRAGMA journal_size_limit={self.limits.reserved_storage_bytes}")
        db.execute("PRAGMA wal_autocheckpoint=256")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS operations_v2 (
                server_id TEXT NOT NULL,
                executor_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                intent_hash TEXT NOT NULL,
                session_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                possible_effect INTEGER NOT NULL,
                retry_safe INTEGER NOT NULL,
                native_id TEXT,
                error_code TEXT,
                PRIMARY KEY(server_id, executor_id, operation_id)
            );
            CREATE TABLE IF NOT EXISTS operation_actions (
                server_id TEXT NOT NULL,
                executor_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                action TEXT NOT NULL,
                terminal_event_expected INTEGER NOT NULL CHECK(terminal_event_expected IN (0,1)),
                PRIMARY KEY(server_id, executor_id, operation_id),
                FOREIGN KEY(server_id, executor_id, operation_id)
                    REFERENCES operations_v2(server_id, executor_id, operation_id)
                    ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS session_open_generations (
                server_id TEXT NOT NULL,
                executor_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                connection_generation INTEGER NOT NULL,
                owner_generation INTEGER NOT NULL,
                PRIMARY KEY(server_id, executor_id, session_id)
            );
            CREATE TABLE IF NOT EXISTS owned_slot_policy (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                max_slots INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS owned_slot_reservations (
                server_id TEXT NOT NULL,
                executor_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                released INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(server_id, executor_id, session_id)
            );
            CREATE INDEX IF NOT EXISTS active_owned_slot_reservations
                ON owned_slot_reservations(released);
            CREATE TABLE IF NOT EXISTS process_births (
                server_id TEXT NOT NULL,
                executor_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                pid INTEGER NOT NULL,
                birth_token TEXT NOT NULL,
                containment TEXT NOT NULL,
                PRIMARY KEY(server_id, executor_id, session_id)
            );
            CREATE TABLE IF NOT EXISTS session_lease_state (
                server_id TEXT NOT NULL,
                executor_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                connection_generation INTEGER NOT NULL,
                owner_generation INTEGER NOT NULL,
                authorization_revision INTEGER NOT NULL,
                configuration_revision INTEGER NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(server_id, executor_id, session_id)
            );
            CREATE TABLE IF NOT EXISTS events (
                server_id TEXT NOT NULL,
                executor_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                stream_epoch TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                body BLOB NOT NULL,
                PRIMARY KEY(server_id, executor_id, session_id, stream_epoch, sequence)
            );
            CREATE TABLE IF NOT EXISTS journal_usage (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                event_bytes INTEGER NOT NULL,
                event_rows INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS server_usage (
                server_id TEXT NOT NULL,
                executor_id TEXT NOT NULL,
                event_bytes INTEGER NOT NULL,
                event_rows INTEGER NOT NULL,
                PRIMARY KEY(server_id, executor_id)
            );
            CREATE TABLE IF NOT EXISTS session_usage (
                server_id TEXT NOT NULL,
                executor_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                event_bytes INTEGER NOT NULL,
                event_rows INTEGER NOT NULL,
                PRIMARY KEY(server_id, executor_id, session_id)
            );
            CREATE TABLE IF NOT EXISTS session_operation_usage (
                server_id TEXT NOT NULL,
                executor_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                operation_rows INTEGER NOT NULL,
                PRIMARY KEY(server_id, executor_id, session_id)
            );
            CREATE TABLE IF NOT EXISTS server_operation_usage (
                server_id TEXT NOT NULL,
                executor_id TEXT NOT NULL,
                operation_rows INTEGER NOT NULL,
                PRIMARY KEY(server_id, executor_id)
            );
            CREATE TABLE IF NOT EXISTS operation_usage (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                operation_rows INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS event_streams (
                server_id TEXT NOT NULL,
                executor_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                stream_epoch TEXT NOT NULL,
                next_sequence INTEGER NOT NULL,
                acked_sequence INTEGER NOT NULL DEFAULT 0,
                compacted_sequence INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(server_id, executor_id, session_id, stream_epoch)
            );
        """)
        db.executescript(PROCESS_LAUNCH_SCHEMA)
        if "compacted_sequence" not in {
            row[1] for row in db.execute("PRAGMA table_info(event_streams)")
        }:
            db.execute(
                "ALTER TABLE event_streams ADD COLUMN compacted_sequence INTEGER NOT NULL DEFAULT 0")
        db.execute("""
            INSERT OR IGNORE INTO event_streams
            SELECT server_id, executor_id, session_id, stream_epoch,
                   MAX(sequence) + 1, 0, 0 FROM events
            GROUP BY server_id, executor_id, session_id, stream_epoch
        """)
        # Pre-quota journals are counted conservatively; no historical event
        # is discarded or reclassified to make room.
        db.execute("""
            INSERT OR IGNORE INTO journal_usage
            SELECT 1, COALESCE(SUM(length(body)), 0), COUNT(*) FROM events
        """)
        db.execute("""
            INSERT OR IGNORE INTO server_usage
            SELECT server_id, executor_id, SUM(length(body)), COUNT(*)
            FROM events GROUP BY server_id, executor_id
        """)
        db.execute("""
            INSERT OR IGNORE INTO session_usage
            SELECT server_id, executor_id, session_id,
                   SUM(length(body)), COUNT(*)
            FROM events GROUP BY server_id, executor_id, session_id
        """)
        db.execute("""
            INSERT OR IGNORE INTO operation_usage
            SELECT 1, COUNT(*) FROM operations_v2
        """)
        db.execute("""
            INSERT OR IGNORE INTO session_operation_usage
            SELECT server_id, executor_id, session_id, COUNT(*)
            FROM operations_v2 GROUP BY server_id, executor_id, session_id
        """)
        db.execute("""
            INSERT OR IGNORE INTO server_operation_usage
            SELECT server_id, executor_id, COUNT(*)
            FROM operations_v2 GROUP BY server_id, executor_id
        """)
        # Only pre-claim journals need conservative legacy fencing. Repeating
        # the backfill on a modern journal invents ownership for pre-admission
        # refusals, which deliberately persist a receipt without a session claim.
        # Creation and backfill must commit together, including concurrent opens
        # and interrupted migrations; table existence is the migration marker.
        db.execute("BEGIN IMMEDIATE")
        try:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='session_claims'").fetchone() is None:
                db.execute("""CREATE TABLE session_claims (
                    server_id TEXT NOT NULL,
                    executor_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    reconciliation_pending INTEGER NOT NULL DEFAULT 1,
                    release_id TEXT,
                    release_digest TEXT,
                    PRIMARY KEY(server_id, executor_id, session_id)
                )""")
                db.execute("""
                    INSERT INTO session_claims(server_id,executor_id,session_id,operation_id)
                    SELECT server_id, executor_id, session_id, MIN(operation_id)
                    FROM operations_v2 GROUP BY server_id, executor_id, session_id
                """)
            claim_columns = {row[1] for row in db.execute("PRAGMA table_info(session_claims)")}
            for column, declaration in (
                ("reconciliation_pending", "INTEGER NOT NULL DEFAULT 1"),
                ("release_id", "TEXT"),
                ("release_digest", "TEXT"),
            ):
                if column not in claim_columns:
                    db.execute(f"ALTER TABLE session_claims ADD COLUMN {column} {declaration}")
            db.execute("CREATE INDEX IF NOT EXISTS pending_session_claims "
                       "ON session_claims(server_id,executor_id) WHERE reconciliation_pending=1")
            db.execute("COMMIT")
        except BaseException:
            self._rollback_if_active(db)
            db.close()
            raise
        # Development journals created before namespacing have no owner
        # evidence. Keep them intact, but never infer a Server and replay an
        # old operation under a new composite key.
        self._has_legacy_operations = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='operations'"
        ).fetchone() is not None
        self._storage_identity = None
        if self.path != ":memory:":
            try:
                info = Path(self.path).stat()
            except OSError as exc:
                db.close()
                raise CoreError("JOURNAL_FULL", "journal_open") from exc
            self._storage_identity = (info.st_dev, info.st_ino)
        return db

    def _storage_status(self, db) -> StorageStatus:
        if self.path == ":memory:":
            return StorageStatus(0, 0, 0, 0, 0, 0,
                                 self.limits.max_storage_bytes)
        base = Path(self.path)
        try:
            info = base.stat()
        except OSError as exc:
            raise CoreError("JOURNAL_FULL", "storage_probe") from exc
        if (info.st_dev, info.st_ino) != self._storage_identity:
            raise CoreError("PROFILE_DRIFT", "storage_probe")
        def size(path: Path) -> int:
            try:
                return path.stat().st_size
            except FileNotFoundError:
                return 0
            except OSError as exc:
                raise CoreError("JOURNAL_FULL", "storage_probe") from exc
        return StorageStatus(
            size(base), size(Path(self.path + "-wal")),
            size(Path(self.path + "-shm")),
            db.execute("PRAGMA page_size").fetchone()[0],
            db.execute("PRAGMA page_count").fetchone()[0],
            db.execute("PRAGMA freelist_count").fetchone()[0],
            self.limits.max_storage_bytes)

    async def storage_status(self) -> StorageStatus:
        def _worker_impl(db):
            return self._storage_status(db)
        return await self._run(_worker_impl, urgent=False)

    async def drain_snapshot(self) -> dict:
        """Bounded metadata only; unknown legacy actions remain obligations.

        SUBMITTED means dispatch returned, not turn completion. Known open and
        control dispatches have no independent turn; submit and replacement
        steer still require their terminal result. Missing metadata is never backfilled from
        names, native IDs or a later retry.
        """
        def read(db):
            queries = {
                'operations': """SELECT o.server_id,o.executor_id,o.session_id,
                    o.operation_id,o.stage,a.action FROM operations_v2 o
                    LEFT JOIN operation_actions a USING(server_id,executor_id,operation_id)
                    WHERE o.stage NOT IN ('SUCCEEDED','FAILED','CANCELLED')
                    AND NOT (o.stage='SUBMITTED' AND COALESCE(a.terminal_event_expected,1)=0)
                    ORDER BY o.server_id,o.executor_id,o.operation_id LIMIT 257""",
                'claims': """WITH selected AS (
                    SELECT server_id,executor_id,session_id,operation_id FROM session_claims
                    WHERE reconciliation_pending=1 ORDER BY server_id,executor_id,session_id LIMIT 257)
                    SELECT c.*,g.owner_generation AS session_owner_generation,
                      (SELECT stream_epoch FROM (
                         SELECT e.server_id,e.executor_id,e.session_id,e.stream_epoch FROM event_streams e
                         WHERE e.server_id=c.server_id AND e.executor_id=c.executor_id
                           AND e.session_id=c.session_id ORDER BY e.stream_epoch LIMIT 2)
                       GROUP BY server_id,executor_id,session_id HAVING COUNT(*)=1) AS stream_epoch
                    FROM selected c LEFT JOIN session_open_generations g
                      ON g.server_id=c.server_id AND g.executor_id=c.executor_id
                     AND g.session_id=c.session_id AND g.operation_id=c.operation_id
                    ORDER BY c.server_id,c.executor_id,c.session_id""",
                'streams': """SELECT server_id,executor_id,session_id,stream_epoch FROM event_streams
                    WHERE next_sequence-1>acked_sequence
                    ORDER BY server_id,executor_id,session_id,stream_epoch LIMIT 257""",
                'watermarks': """SELECT server_id,executor_id,session_id,stream_epoch,
                    next_sequence-1 AS sequence FROM event_streams
                    WHERE EXISTS (SELECT 1 FROM session_claims c WHERE
                        c.server_id=event_streams.server_id AND c.executor_id=event_streams.executor_id
                        AND c.session_id=event_streams.session_id AND c.reconciliation_pending=1)
                    ORDER BY server_id,executor_id,session_id,stream_epoch LIMIT 257""",
            }
            db.execute('BEGIN')
            try:
                result = {'truncated': False}
                for name, sql in queries.items():
                    cursor = db.execute(sql)
                    names = [column[0] for column in cursor.description]
                    rows = cursor.fetchall()
                    result['truncated'] |= len(rows) > 256
                    result[name] = [dict(zip(names, row)) for row in rows[:256]]
                return result
            finally:
                db.execute('ROLLBACK')
        return await self._run(read, urgent=False)

    async def claimed_sessions(
            self, server_id: str, executor_id: str, *, after_rowid: int = 0,
            high_water_rowid: int | None = None,
            limit: int = 128, pending_only: bool = False) -> SessionClaimPage:
        """Page durable identity history, never a live-process inventory."""
        validate_claim_page(after_rowid, high_water_rowid, limit)
        validate_claim_namespace(server_id, executor_id)
        if type(pending_only) is not bool:
            raise ValueError("invalid session-claim selection")
        def _worker_impl(db, high_water_rowid=high_water_rowid):
            pending = " AND reconciliation_pending=1" if pending_only else ""
            if high_water_rowid is None:
                high_water_rowid = db.execute(
                    "SELECT COALESCE(MAX(rowid),0) FROM session_claims WHERE server_id=? AND executor_id=?" + pending,
                    (server_id, executor_id)).fetchone()[0]
            rows = db.execute(
                """SELECT c.rowid,c.session_id,c.operation_id,
                          g.connection_generation,g.owner_generation
                   FROM session_claims AS c LEFT JOIN session_open_generations AS g
                     ON g.server_id=c.server_id AND g.executor_id=c.executor_id
                    AND g.session_id=c.session_id AND g.operation_id=c.operation_id
                   WHERE c.server_id=? AND c.executor_id=?
                     AND c.rowid>? AND c.rowid<=?""" +
                (" AND c.reconciliation_pending=1" if pending_only else "") +
                " ORDER BY c.rowid LIMIT ?",
                (server_id, executor_id, after_rowid,
                 high_water_rowid, limit + 1)).fetchall()
            page_rows = rows[:limit]
            return SessionClaimPage(
                tuple(ClaimedSession(SessionKey(server_id, executor_id, session_id),
                                     operation_id, connection_generation,
                                     owner_generation)
                      for (_, session_id, operation_id, connection_generation,
                           owner_generation) in page_rows),
                high_water_rowid,
                page_rows[-1][0] if len(rows) > limit else None)
        return await self._run(_worker_impl, urgent=False)

    async def retire_reconciliation_claim(self, session: SessionKey, *,
                                          operation_id: str, release_id: str,
                                          release_digest: str) -> None:
        """Retire only the reconciliation projection; immutable claim history remains."""
        if (not isinstance(session, SessionKey) or type(session.session_id) is not str
                or not 1 <= len(session.session_id) <= 160
                or type(operation_id) is not str or not 1 <= len(operation_id) <= 160
                or type(release_id) is not str
                or not 1 <= len(release_id) <= 160 or type(release_digest) is not str
                or len(release_digest) != 64
                or any(char not in "0123456789abcdef" for char in release_digest)):
            raise ValueError("invalid session retirement proof")
        validate_claim_namespace(session.server_id, session.executor_id)
        def retire(db):
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute("SELECT operation_id,reconciliation_pending,release_id,release_digest "
                    "FROM session_claims WHERE server_id=? AND executor_id=? AND session_id=?",
                    (session.server_id,session.executor_id,session.session_id)).fetchone()
                if row is None or row[0] != operation_id:
                    raise CoreError("SESSION_CONFLICT", "claim_retirement")
                if not row[1]:
                    if row[2:] != (release_id,release_digest):
                        raise CoreError("SESSION_CONFLICT", "claim_retirement")
                else:
                    db.execute("UPDATE session_claims SET reconciliation_pending=0,release_id=?,release_digest=? "
                        "WHERE server_id=? AND executor_id=? AND session_id=? AND reconciliation_pending=1",
                        (release_id,release_digest,session.server_id,session.executor_id,session.session_id))
                db.execute("COMMIT")
            except BaseException:
                self._rollback_if_active(db)
                raise
        await self._run(retire, urgent=False)

    async def get_session_claim(self, session: SessionKey) -> ClaimedSession | None:
        """Read one original claim without scanning unrelated session history."""
        if not isinstance(session, SessionKey):
            raise ValueError('Invalid session claim key.')
        validate_claim_namespace(session.server_id, session.executor_id)
        if type(session.session_id) is not str or not 1 <= len(session.session_id) <= 160:
            raise ValueError('Invalid session claim key.')
        def read(db):
            row = db.execute(
                'SELECT c.operation_id,g.connection_generation,g.owner_generation FROM session_claims c '
                'LEFT JOIN session_open_generations g ON g.server_id=c.server_id AND g.executor_id=c.executor_id '
                'AND g.session_id=c.session_id AND g.operation_id=c.operation_id '
                'WHERE c.server_id=? AND c.executor_id=? AND c.session_id=?',
                (session.server_id,session.executor_id,session.session_id)).fetchone()
            return ClaimedSession(session, *row) if row is not None else None
        return await self._run(read, urgent=False)

    async def record_process_birth(
            self, key: OperationKey, session_id: str,
            evidence: ProcessBirthEvidence) -> ProcessBirthRecord:
        """Persist one historical birth under the original open claim."""
        validate_process_birth(evidence)
        if not isinstance(key, OperationKey):
            raise ValueError("invalid process birth identity")
        validate_claim_namespace(key.server_id, key.executor_id)
        if type(key.operation_id) is not str or not key.operation_id or \
                type(session_id) is not str or not session_id:
            raise ValueError("invalid process birth identity")
        session = SessionKey(key.server_id, key.executor_id, session_id)
        def _worker_impl(db):
            db.execute("BEGIN IMMEDIATE")
            try:
                claim = db.execute(
                    "SELECT operation_id FROM session_claims WHERE server_id=? AND executor_id=? AND session_id=?",
                    (key.server_id, key.executor_id, session_id)).fetchone()
                if claim is None:
                    raise CoreError("SESSION_UNKNOWN", "process_birth")
                if claim[0] != key.operation_id:
                    raise CoreError("SESSION_CONFLICT", "process_birth")
                operation = db.execute(
                    "SELECT possible_effect FROM operations_v2 WHERE server_id=? AND executor_id=? AND operation_id=?",
                    (key.server_id, key.executor_id, key.operation_id)).fetchone()
                if operation is None or not operation[0]:
                    raise CoreError("VALIDATION_ERROR", "process_birth")
                self._validate_launch_birth(db, session, evidence)
                old = db.execute(
                    "SELECT platform,pid,birth_token,containment FROM process_births WHERE server_id=? AND executor_id=? AND session_id=?",
                    (key.server_id, key.executor_id, session_id)).fetchone()
                identity = (evidence.platform, evidence.pid,
                            evidence.birth_token, evidence.containment)
                db.execute('CREATE TABLE IF NOT EXISTS process_containers ('
                    'server_id TEXT, executor_id TEXT, session_id TEXT, container_id TEXT NOT NULL, '
                    'PRIMARY KEY(server_id,executor_id,session_id))')
                container = db.execute('SELECT container_id FROM process_containers '
                    'WHERE server_id=? AND executor_id=? AND session_id=?',
                    (key.server_id, key.executor_id, session_id)).fetchone()
                if old is not None and (container[0] if container else None) != evidence.container_id:
                    raise CoreError("PROCESS_BIRTH_CONFLICT", "process_birth")
                if old is not None and tuple(old) != identity:
                    raise CoreError("PROCESS_BIRTH_CONFLICT", "process_birth")
                if old is None:
                    self._require_storage_capacity(db, 512, critical=True,
                                                   stage="process_birth",
                                                   possible_effect=True,
                                                   operation_id=key.operation_id)
                    db.execute(
                        "INSERT INTO process_births VALUES (?,?,?,?,?,?,?,?)",
                        (key.server_id, key.executor_id, session_id,
                         key.operation_id, *identity))
                    if evidence.container_id is not None:
                        db.execute('INSERT INTO process_containers VALUES(?,?,?,?)',
                            (key.server_id,key.executor_id,session_id,evidence.container_id))
                db.execute("COMMIT")
            except BaseException as exc:
                self._rollback_if_active(db)
                if _sqlite_full(exc):
                    raise CoreError("JOURNAL_FULL", "process_birth",
                                    possible_effect=True,
                                    operation_id=key.operation_id) from exc
                raise
            return ProcessBirthRecord(session, key.operation_id, evidence)
        return await self._run(_worker_impl, urgent=False)

    async def get_process_birth(self, session: SessionKey) -> ProcessBirthRecord | None:
        if not isinstance(session, SessionKey):
            raise ValueError("invalid process birth session")
        def _worker_impl(db):
            row = db.execute(
                "SELECT operation_id,platform,pid,birth_token,containment FROM process_births WHERE server_id=? AND executor_id=? AND session_id=?",
                (session.server_id, session.executor_id,
                 session.session_id)).fetchone()
            if row is None:
                return None
            container = None
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='process_containers'").fetchone():
                container = db.execute('SELECT container_id FROM process_containers '
                    'WHERE server_id=? AND executor_id=? AND session_id=?',
                    (session.server_id,session.executor_id,session.session_id)).fetchone()
            return ProcessBirthRecord(
                session, row[0], ProcessBirthEvidence(*row[1:], container_id=container[0] if container else None))
        return await self._run(_worker_impl, urgent=False)

    async def get_session_lease(self, session: SessionKey) -> SessionLeaseState | None:
        """Read the durable last-known lease fence, or None for legacy claims."""
        if not isinstance(session, SessionKey):
            raise ValueError("invalid lease session")
        def _worker_impl(db):
            row = db.execute(
                """SELECT connection_generation,owner_generation,
                          authorization_revision,configuration_revision,revoked
                   FROM session_lease_state
                   WHERE server_id=? AND executor_id=? AND session_id=?""",
                (session.server_id, session.executor_id,
                 session.session_id)).fetchone()
            if row is None:
                return None
            return SessionLeaseState(session, row[0], row[1], row[2], row[3],
                                     bool(row[4]))
        return await self._run(_worker_impl, urgent=False)

    async def cas_session_lease(self, session: SessionKey, *,
                                expected_connection_generation: int,
                                connection_generation: int,
                                owner_generation: int,
                                authorization_revision: int,
                                configuration_revision: int,
                                revoked: bool) -> SessionLeaseState:
        """Atomically advance the durable lease fence for one claimed session.

        Compare-and-set on the current connection generation with monotonic
        component checks. A missing row (legacy claim without lease evidence)
        fails with SESSION_UNKNOWN rather than being silently created: a
        durable fence cannot be seeded from memory after the fact. A revoked
        row can never be un-revoked. This is CAS evidence, not process
        liveness and not takeover authority.
        """
        if not isinstance(session, SessionKey):
            raise ValueError("invalid lease session")
        integers = (expected_connection_generation, connection_generation,
                    owner_generation, authorization_revision,
                    configuration_revision)
        if (any(type(value) is not int or
                not 1 <= value <= 9223372036854775807
                for value in integers) or type(revoked) is not bool):
            raise ValueError("invalid lease fence values")
        def _worker_impl(db):
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    """SELECT connection_generation,owner_generation,
                              authorization_revision,configuration_revision,revoked
                       FROM session_lease_state
                       WHERE server_id=? AND executor_id=? AND session_id=?""",
                    (session.server_id, session.executor_id,
                     session.session_id)).fetchone()
                if row is None:
                    raise CoreError("SESSION_UNKNOWN", "lease_cas")
                if (row[4] and not revoked):
                    raise CoreError("STALE_GENERATION", "lease_cas")
                if (expected_connection_generation != row[0] or
                        connection_generation < row[0] or
                        owner_generation < row[1] or
                        authorization_revision < row[2] or
                        configuration_revision < row[3]):
                    raise CoreError("STALE_GENERATION", "lease_cas")
                db.execute(
                    """UPDATE session_lease_state
                       SET connection_generation=?,owner_generation=?,
                           authorization_revision=?,configuration_revision=?,revoked=?
                       WHERE server_id=? AND executor_id=? AND session_id=?""",
                    (connection_generation, owner_generation,
                     authorization_revision, configuration_revision,
                     int(revoked), session.server_id, session.executor_id,
                     session.session_id))
                db.execute("COMMIT")
            except BaseException:
                self._rollback_if_active(db)
                raise
            return SessionLeaseState(session, connection_generation,
                                     owner_generation, authorization_revision,
                                     configuration_revision, revoked)
        return await self._run(_worker_impl, urgent=True)

    async def reserve_owned_slot(self, key: OperationKey,
                                 session_id: str) -> None:
        """Reserve one shared-journal process slot before native launch.

        A crash retains the reservation. A different journal file is a
        different budget; this is not a host-wide ledger by itself.
        """
        if not isinstance(key, OperationKey):
            raise ValueError("invalid owned-slot identity")
        validate_claim_namespace(key.server_id, key.executor_id)
        if (type(key.operation_id) is not str or not key.operation_id or
                type(session_id) is not str or not session_id):
            raise ValueError("invalid owned-slot identity")
        def _worker_impl(db):
            db.execute("BEGIN IMMEDIATE")
            try:
                claim = db.execute(
                    """SELECT c.operation_id,o.possible_effect
                       FROM session_claims AS c JOIN operations_v2 AS o
                         ON o.server_id=c.server_id AND o.executor_id=c.executor_id
                        AND o.operation_id=c.operation_id
                       WHERE c.server_id=? AND c.executor_id=? AND c.session_id=?""",
                    (key.server_id, key.executor_id, session_id)).fetchone()
                if claim is None or claim[0] != key.operation_id or not claim[1]:
                    raise CoreError("SESSION_CONFLICT", "owned_slot")
                policy = db.execute(
                    "SELECT max_slots FROM owned_slot_policy WHERE singleton=1"
                ).fetchone()
                if policy is None:
                    db.execute(
                        "INSERT INTO owned_slot_policy VALUES (1,?)",
                        (self.limits.max_owned_slots,))
                elif policy[0] != self.limits.max_owned_slots:
                    raise CoreError("PROFILE_DRIFT", "owned_slot")
                existing = db.execute(
                    """SELECT operation_id FROM owned_slot_reservations
                       WHERE server_id=? AND executor_id=? AND session_id=?""",
                    (key.server_id, key.executor_id, session_id)).fetchone()
                if existing is not None:
                    raise CoreError("SESSION_CONFLICT", "owned_slot",
                                    possible_effect=True)
                occupied = db.execute(
                    "SELECT COUNT(*) FROM owned_slot_reservations WHERE released=0"
                ).fetchone()[0]
                if occupied >= self.limits.max_owned_slots:
                    raise CoreError("CAPACITY_EXCEEDED", "owned_slot",
                                    retry_safe=True, operation_id=key.operation_id)
                self._require_storage_capacity(db, 
                    512, critical=True, stage="owned_slot",
                    operation_id=key.operation_id)
                db.execute(
                    "INSERT INTO owned_slot_reservations VALUES (?,?,?,?,0)",
                    (key.server_id, key.executor_id, session_id,
                     key.operation_id))
                db.execute("COMMIT")
            except BaseException as exc:
                self._rollback_if_active(db)
                if _sqlite_full(exc):
                    raise CoreError("JOURNAL_FULL", "owned_slot",
                                    retry_safe=True,
                                    operation_id=key.operation_id) from exc
                raise
        return await self._run(_worker_impl, urgent=False)

    async def release_owned_slot(self, key: OperationKey,
                                 session_id: str) -> bool:
        """Release only the original reservation after proven non-effect/stop."""
        if not isinstance(key, OperationKey):
            raise ValueError("invalid owned-slot identity")
        validate_claim_namespace(key.server_id, key.executor_id)
        if (type(key.operation_id) is not str or not key.operation_id or
                type(session_id) is not str or not session_id):
            raise ValueError("invalid owned-slot identity")
        def _worker_impl(db):
            db.execute("BEGIN IMMEDIATE")
            try:
                policy = db.execute(
                    "SELECT max_slots FROM owned_slot_policy WHERE singleton=1"
                ).fetchone()
                if policy is None or policy[0] != self.limits.max_owned_slots:
                    raise CoreError("PROFILE_DRIFT", "owned_slot_release")
                row = db.execute(
                    """SELECT operation_id,released FROM owned_slot_reservations
                       WHERE server_id=? AND executor_id=? AND session_id=?""",
                    (key.server_id, key.executor_id, session_id)).fetchone()
                if row is None or row[0] != key.operation_id:
                    raise CoreError("SESSION_CONFLICT", "owned_slot_release")
                if not row[1]:
                    db.execute(
                        """UPDATE owned_slot_reservations SET released=1
                           WHERE server_id=? AND executor_id=? AND session_id=?""",
                        (key.server_id, key.executor_id, session_id))
                db.execute("COMMIT")
            except BaseException as exc:
                self._rollback_if_active(db)
                if _sqlite_full(exc):
                    raise CoreError("JOURNAL_FULL", "owned_slot_release",
                                    possible_effect=True,
                                    operation_id=key.operation_id) from exc
                raise
            return not bool(row[1])
        return await self._run(_worker_impl, urgent=True)

    async def owned_slot_state(self, session: SessionKey) -> OwnedSlotState | None:
        """Read a specific durable fact; a missing row means no known record.

        Released reservations are retained across restarts. Release can mean
        proven non-effect or observed stop, so callers must also correlate the
        original opening receipt before interpreting session history.
        """
        if not isinstance(session, SessionKey):
            raise ValueError("Invalid owned-slot session.")
        validate_claim_namespace(session.server_id, session.executor_id)
        if type(session.session_id) is not str or not session.session_id:
            raise ValueError("Invalid owned-slot session.")

        def _worker_impl(db):
            policy = db.execute(
                "SELECT max_slots FROM owned_slot_policy WHERE singleton=1").fetchone()
            if policy is not None and policy[0] != self.limits.max_owned_slots:
                raise CoreError("PROFILE_DRIFT", "owned_slot_state")
            row = db.execute(
                "SELECT operation_id,released FROM owned_slot_reservations "
                "WHERE server_id=? AND executor_id=? AND session_id=?",
                (session.server_id, session.executor_id, session.session_id)).fetchone()
            if row is None:
                return None
            if type(row[0]) is not str or not row[0] or row[1] not in (0, 1):
                raise CoreError("JOURNAL_UNAVAILABLE", "owned_slot_state")
            return OwnedSlotState(session, row[0], bool(row[1]))
        return await self._run(_worker_impl)

    async def owned_slot_page(self, *, after_rowid: int = 0,
                              high_water_rowid: int | None = None,
                              limit: int = 128) -> OwnedSlotPage:
        """Page active reservations; never infer liveness from this history."""
        validate_claim_page(after_rowid, high_water_rowid, limit,
                            label="owned-slot")
        def _worker_impl(db, high_water_rowid=high_water_rowid):
            policy = db.execute(
                "SELECT max_slots FROM owned_slot_policy WHERE singleton=1"
            ).fetchone()
            if policy is not None and policy[0] != self.limits.max_owned_slots:
                raise CoreError("PROFILE_DRIFT", "owned_slot_page")
            if high_water_rowid is None:
                high_water_rowid = db.execute(
                    "SELECT COALESCE(MAX(rowid),0) FROM owned_slot_reservations"
                ).fetchone()[0]
            rows = db.execute(
                """SELECT rowid,server_id,executor_id,session_id,operation_id
                   FROM owned_slot_reservations
                   WHERE released=0 AND rowid>? AND rowid<=?
                   ORDER BY rowid LIMIT ?""",
                (after_rowid, high_water_rowid, limit + 1)).fetchall()
            page_rows = rows[:limit]
            return OwnedSlotPage(
                tuple(OwnedSlotReservation(SessionKey(server_id, executor_id,
                                                      session_id), operation_id)
                      for _, server_id, executor_id, session_id,
                      operation_id in page_rows),
                high_water_rowid,
                page_rows[-1][0] if len(rows) > limit else None)
        return await self._run(_worker_impl, urgent=False)

    async def checkpoint_wal(self) -> tuple[int, int, int]:
        """Attempt non-waiting WAL truncation; report busy/log/checkpointed."""
        def _worker_impl(db):
            return self._checkpoint_wal_locked(db)
        return await self._run(_worker_impl, urgent=False)

    def _checkpoint_wal_locked(self, db) -> tuple[int, int, int]:
        old_timeout = db.execute("PRAGMA busy_timeout").fetchone()[0]
        db.execute("PRAGMA busy_timeout=0")
        try:
            return db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        finally:
            db.execute(f"PRAGMA busy_timeout={old_timeout}")

    def _rollback_if_active(self, db) -> None:
        # SQLITE_FULL may already have rolled back the transaction. A second
        # ROLLBACK would mask the original error and its effect attribution.
        if db.in_transaction:
            db.execute("ROLLBACK")

    def _require_storage_capacity(self, db, estimate_bytes: int, *, critical: bool,
                                  stage: str, possible_effect: bool = False,
                                  operation_id: str | None = None) -> None:
        status = self._storage_status(db)
        if status.page_size == 0:  # In-memory test journal has no disk file.
            return
        ceiling = (self.limits.max_storage_bytes if critical else min(
            self.limits.max_storage_bytes - self.limits.reserved_storage_bytes,
            self.limits.max_storage_bytes * 4 // 5))
        # SQLite can write several B-tree/WAL pages around a payload. This is
        # admission headroom, not a claim of an exact filesystem quota.
        estimate = estimate_bytes + status.page_size * 4
        if status.total_bytes + estimate > ceiling:
            raise CoreError("JOURNAL_FULL", stage,
                            possible_effect=possible_effect,
                            retry_safe=not possible_effect,
                            operation_id=operation_id)
        # Hard WAL bound: maintenance (a bounded truncate checkpoint) was
        # already attempted before this transaction; if the WAL is still
        # over its ceiling - typically a pinned reader prevents truncation -
        # admissions stop honestly instead of growing without bound. The
        # reserve stays available for critical writes only.
        wal_ceiling = (self.limits.max_wal_bytes if critical else
                       self.limits.max_wal_bytes - self.limits.reserved_wal_bytes)
        if status.wal_bytes + estimate > wal_ceiling:
            raise CoreError("JOURNAL_FULL", stage,
                            possible_effect=possible_effect,
                            retry_safe=not possible_effect,
                            operation_id=operation_id)

    def _recover_normal_storage(self, db, estimate_bytes: int, *, stage: str,
                                possible_effect: bool = False,
                                operation_id: str | None = None,
                                logical_pressure: bool = False,
                                priority_session: tuple[str, str, str] | None = None) -> None:
        """Try one bounded ACK-only recovery pass before a normal write."""
        status = self._storage_status(db)
        if not status.page_size and not logical_pressure:
            return
        normal_ceiling = min(
            self.limits.max_storage_bytes - self.limits.reserved_storage_bytes,
            self.limits.max_storage_bytes * 4 // 5,
        )
        wal_ceiling = self.limits.max_wal_bytes - self.limits.reserved_wal_bytes
        if (status.page_size and not logical_pressure and
                status.total_bytes + estimate_bytes + status.page_size * 4
                <= normal_ceiling and
                status.wal_bytes + estimate_bytes + status.page_size * 4
                <= wal_ceiling):
            return
        try:
            self._compact_acked_locked(db, 128, priority_session=priority_session)
        except sqlite3.Error as exc:
            if _sqlite_full(exc):
                raise CoreError("JOURNAL_FULL", stage,
                                possible_effect=possible_effect,
                                retry_safe=not possible_effect,
                                operation_id=operation_id) from exc
            raise
        # A pinned reader may leave the WAL large. The later admission gate
        # rechecks physical bytes; maintenance never overrides that denial.
        if status.page_size:
            try:
                self._checkpoint_wal_locked(db)
            except sqlite3.Error:
                pass

    def _receipt(self, row: tuple | None) -> OperationReceipt | None:
        if row is None:
            return None
        return OperationReceipt(row[0], row[1], row[3], bool(row[4]),
                                bool(row[5]), row[2], row[6], row[7])

    def _get(self, db, key: OperationKey) -> OperationReceipt | None:
        row = db.execute(
            "SELECT operation_id,intent_hash,session_id,stage,possible_effect,retry_safe,native_id,error_code FROM operations_v2 WHERE server_id=? AND executor_id=? AND operation_id=?",
            (key.server_id, key.executor_id, key.operation_id)).fetchone()
        if row is None and self._has_legacy_operations:
            legacy = db.execute(
                "SELECT 1 FROM operations WHERE operation_id=?",
                (key.operation_id,)).fetchone()
            if legacy is not None:
                raise CoreError("LEGACY_OPERATION_UNSCOPED", "journal_read",
                                possible_effect=True,
                                operation_id=key.operation_id)
        return self._receipt(row)

    async def admit(self, key: OperationKey, intent_hash: str,
                    session_id: str, *,
                    critical: bool = False,
                    effect_imminent: bool = False,
                    claim_session: bool = False,
                    connection_generation: int | None = None,
                    session_owner_generation: int | None = None,
                    authorization_revision: int | None = None,
                    configuration_revision: int | None = None,
                    process_launch_identity=None,
                    action: str | None = None,
                    terminal_event_expected: bool | None = None,
                    ) -> tuple[OperationReceipt, bool]:
        if not all((key.server_id, key.executor_id, key.operation_id, session_id)):
            raise CoreError("OPERATION_INVALID", "admission")
        if type(claim_session) is not bool:
            raise ValueError("claim_session must be boolean")
        if action is not None and (type(action) is not str or action not in {
                'runtime.open', 'runtime.close', 'turn.submit', 'turn.steer',
                'turn.interrupt', 'approval.decide', 'input.provide'}):
            raise CoreError('VALIDATION_ERROR', 'admission')
        if terminal_event_expected is None:
            terminal_event_expected = action in {'turn.submit', 'turn.steer'}
        if (type(terminal_event_expected) is not bool or
                (action == 'turn.submit' and not terminal_event_expected)):
            raise CoreError('VALIDATION_ERROR', 'admission')
        if process_launch_identity is not None:
            from .process_launch import validate_launch_identity
            validate_launch_identity(process_launch_identity)
            launch = process_launch_identity
            if (not claim_session or launch.key != SessionKey(key.server_id, key.executor_id, session_id)
                    or launch.opening_operation_id != key.operation_id
                    or launch.connection_generation != connection_generation
                    or launch.owner_generation != session_owner_generation):
                raise CoreError('PROCESS_LAUNCH_CONFLICT', 'admission', retry_safe=True,
                                operation_id=key.operation_id)
        admission_bytes = 1536 if process_launch_identity is not None else 512
        if ((connection_generation is None) !=
                (session_owner_generation is None)):
            raise ValueError("opening generations must be supplied together")
        if ((authorization_revision is None) !=
                (configuration_revision is None)):
            raise ValueError("lease revisions must be supplied together")
        if connection_generation is not None:
            if (not claim_session or
                    type(connection_generation) is not int or
                    type(session_owner_generation) is not int or
                    not 1 <= connection_generation <= 9223372036854775807 or
                    not 1 <= session_owner_generation <= 9223372036854775807):
                raise ValueError("invalid opening generations")
        if authorization_revision is not None:
            if (connection_generation is None or
                    type(authorization_revision) is not int or
                    type(configuration_revision) is not int or
                    not 1 <= authorization_revision <= 9223372036854775807 or
                    not 1 <= configuration_revision <= 9223372036854775807):
                raise ValueError("invalid opening lease revisions")
        def _worker_impl(db):
            # Duplicate reads must remain available even while the journal is
            # under pressure. A second read inside the write transaction still
            # fences cross-process races before any new admission.
            if not critical and self._get(db, key) is None:
                self._recover_normal_storage(db, 
                    admission_bytes, stage="admission", operation_id=key.operation_id)
            db.execute("BEGIN IMMEDIATE")
            try:
                old = self._get(db, key)
                if old is not None:
                    if old.intent_hash != intent_hash or old.session_id != session_id:
                        raise CoreError("OPERATION_CONFLICT", "admission",
                                        operation_id=key.operation_id)
                    if claim_session:
                        generations = db.execute(
                            """SELECT connection_generation,owner_generation
                               FROM session_open_generations
                               WHERE server_id=? AND executor_id=?
                                 AND session_id=? AND operation_id=?""",
                            (key.server_id, key.executor_id, session_id,
                             key.operation_id)).fetchone()
                        if (generations is not None and
                                tuple(generations) != (
                                    connection_generation,
                                    session_owner_generation)):
                            raise CoreError("OPERATION_CONFLICT", "admission",
                                            operation_id=key.operation_id)
                    db.execute("COMMIT")
                    return old, False
                self._require_storage_capacity(db, 
                    admission_bytes, critical=critical, stage="admission",
                    operation_id=key.operation_id)
                usage = db.execute(
                    "SELECT event_bytes,event_rows FROM journal_usage WHERE singleton=1"
                ).fetchone()
                server_usage = db.execute(
                    "SELECT event_bytes,event_rows FROM server_usage WHERE server_id=? AND executor_id=?",
                    (key.server_id, key.executor_id)).fetchone() or (0, 0)
                session_usage = db.execute(
                    "SELECT event_bytes,event_rows FROM session_usage WHERE server_id=? AND executor_id=? AND session_id=?",
                    (key.server_id, key.executor_id, session_id)).fetchone() or (0, 0)
                operation_count = db.execute(
                    "SELECT operation_rows FROM operation_usage WHERE singleton=1"
                ).fetchone()[0]
                server_operation_count = db.execute(
                    "SELECT operation_rows FROM server_operation_usage WHERE server_id=? AND executor_id=?",
                    (key.server_id, key.executor_id)).fetchone()
                server_operation_count = (server_operation_count[0]
                                          if server_operation_count else 0)
                session_operation_count = db.execute(
                    "SELECT operation_rows FROM session_operation_usage WHERE server_id=? AND executor_id=? AND session_id=?",
                    (key.server_id, key.executor_id, session_id)).fetchone()
                session_operation_count = (session_operation_count[0]
                                           if session_operation_count else 0)
                max_operations = (self.limits.max_operation_rows if critical else
                                  self.limits.max_operation_rows - self.limits.reserved_operation_rows)
                max_server_operations = (
                    self.limits.server_operation_rows if critical else
                    self.limits.server_operation_rows -
                    self.limits.server_reserved_operation_rows)
                max_session_operations = (
                    self.limits.session_operation_rows if critical else
                    self.limits.session_operation_rows -
                    self.limits.session_reserved_operation_rows)
                if (operation_count >= max_operations or
                    server_operation_count >= max_server_operations or
                    session_operation_count >= max_session_operations or
                    (not critical and (
                        usage[0] * 5 >= self.limits.total_event_bytes * 4 or
                        usage[1] * 5 >= self.limits.total_event_rows * 4 or
                        server_usage[0] * 5 >= self.limits.server_event_bytes * 4 or
                        server_usage[1] * 5 >= self.limits.server_event_rows * 4 or
                        session_usage[0] * 5 >= self.limits.session_event_bytes * 4 or
                        session_usage[1] * 5 >= self.limits.session_event_rows * 4))):
                    raise CoreError("JOURNAL_FULL", "admission", retry_safe=True,
                                    operation_id=key.operation_id)
                if claim_session:
                    claimed = db.execute(
                        "SELECT 1 FROM session_claims WHERE server_id=? AND executor_id=? AND session_id=?",
                        (key.server_id, key.executor_id, session_id)).fetchone()
                    if claimed is not None:
                        raise CoreError("SESSION_CONFLICT", "admission",
                                        operation_id=key.operation_id)
                    db.execute(
                        "INSERT INTO session_claims(server_id,executor_id,session_id,operation_id) VALUES (?,?,?,?)",
                        (key.server_id, key.executor_id, session_id,
                         key.operation_id))
                    if connection_generation is not None:
                        db.execute(
                            "INSERT INTO session_open_generations VALUES (?,?,?,?,?,?)",
                            (key.server_id, key.executor_id, session_id,
                             key.operation_id, connection_generation,
                             session_owner_generation))
                    if authorization_revision is not None:
                        # Durable lease fence seeded with the claim: the
                        # last CAS winner is knowable after any restart.
                        db.execute(
                            "INSERT INTO session_lease_state VALUES (?,?,?,?,?,?,?,0)",
                            (key.server_id, key.executor_id, session_id,
                             connection_generation, session_owner_generation,
                             authorization_revision, configuration_revision))
                db.execute("INSERT INTO operations_v2 VALUES (?,?,?,?,?,?,?,?,?,?)",
                                 (key.server_id, key.executor_id,
                                  key.operation_id, intent_hash, session_id,
                                  "SUBMISSION_STARTED" if effect_imminent else "RECEIVED_DURABLE",
                                  int(effect_imminent), int(not effect_imminent), None, None))
                if action is not None:
                    db.execute('INSERT INTO operation_actions VALUES (?,?,?,?,?)',
                               (key.server_id, key.executor_id, key.operation_id, action,
                                int(terminal_event_expected)))
                if process_launch_identity is not None:
                    # Persist before the possible-effect frontier, in the
                    # same transaction as the immutable opening claim.
                    self._insert_process_launch(db, process_launch_identity)
                db.execute(
                    "UPDATE operation_usage SET operation_rows=operation_rows+1 WHERE singleton=1")
                db.execute(
                    "INSERT OR IGNORE INTO server_operation_usage VALUES (?,?,0)",
                    (key.server_id, key.executor_id))
                db.execute(
                    "UPDATE server_operation_usage SET operation_rows=operation_rows+1 WHERE server_id=? AND executor_id=?",
                    (key.server_id, key.executor_id))
                db.execute(
                    "INSERT OR IGNORE INTO session_operation_usage VALUES (?,?,?,0)",
                    (key.server_id, key.executor_id, session_id))
                db.execute(
                    "UPDATE session_operation_usage SET operation_rows=operation_rows+1 WHERE server_id=? AND executor_id=? AND session_id=?",
                    (key.server_id, key.executor_id, session_id))
                db.execute("COMMIT")
                return self._get(db, key), True  # type: ignore[return-value]
            except BaseException as exc:
                self._rollback_if_active(db)
                if _sqlite_full(exc):
                    raise CoreError("JOURNAL_FULL", "admission", retry_safe=True,
                                    operation_id=key.operation_id) from exc
                raise
        return await self._run(_worker_impl, urgent=False)

    async def mark_possible_effect(self, key: OperationKey) -> OperationReceipt:
        def _worker_impl(db):
            try:
                db.execute("UPDATE operations_v2 SET stage='SUBMISSION_STARTED', possible_effect=1, retry_safe=0 WHERE server_id=? AND executor_id=? AND operation_id=? AND stage IN ('RECEIVED_DURABLE','PREPARED')",
                                 (key.server_id, key.executor_id, key.operation_id))
            except sqlite3.Error as exc:
                if _sqlite_full(exc):
                    raise CoreError("JOURNAL_FULL", "effect_mark", retry_safe=True,
                                    operation_id=key.operation_id) from exc
                raise
            receipt = self._get(db, key)
            if receipt is None:
                raise KeyError(key)
            return receipt
        return await self._run(_worker_impl, urgent=False)

    async def record_not_sent(self, key: OperationKey, error_code: str) -> OperationReceipt:
        """Clear a conservative effect marker only with adapter proof of no write."""
        def _worker_impl(db):
            db.execute("BEGIN IMMEDIATE")
            try:
                old = self._get(db, key)
                if old is None or old.stage != "SUBMISSION_STARTED":
                    raise CoreError("OPERATION_STAGE_CONFLICT", "record_not_sent",
                                    operation_id=key.operation_id)
                db.execute(
                    "UPDATE operations_v2 SET stage='FAILED',possible_effect=0,"
                    "retry_safe=1,error_code=? WHERE server_id=? AND executor_id=? "
                    "AND operation_id=?",
                    (error_code, key.server_id, key.executor_id, key.operation_id),
                )
                receipt = self._get(db, key)
                db.execute("COMMIT")
                assert receipt is not None
                return receipt
            except BaseException as exc:
                self._rollback_if_active(db)
                if _sqlite_full(exc):
                    raise CoreError("JOURNAL_FULL", "receipt_record",
                                    possible_effect=True,
                                    operation_id=key.operation_id) from exc
                raise
        return await self._run(_worker_impl, urgent=True)

    async def record_receipt(self, key: OperationKey,
                             receipt: OperationReceipt) -> OperationReceipt:
        def _worker_impl(db):
            db.execute("BEGIN IMMEDIATE")
            try:
                old = self._get(db, key)
                if (receipt.operation_id != key.operation_id or old is None or
                        old.intent_hash != receipt.intent_hash or
                        old.session_id != receipt.session_id):
                    raise CoreError("OPERATION_CONFLICT", "record",
                                    operation_id=receipt.operation_id)
                if (receipt.stage not in _STAGE_TRANSITIONS or
                    old.stage not in _STAGE_TRANSITIONS or
                    (old.native_id is not None and receipt.native_id is not None
                     and old.native_id != receipt.native_id)):
                    raise CoreError("OPERATION_STAGE_CONFLICT", "record",
                                    operation_id=receipt.operation_id)
                if receipt.stage == old.stage:
                    if (receipt.error_code != old.error_code or
                            receipt.possible_effect != old.possible_effect or
                            receipt.retry_safe != old.retry_safe):
                        raise CoreError("OPERATION_STAGE_CONFLICT", "record",
                                        operation_id=receipt.operation_id)
                    effective = replace(old, native_id=old.native_id or receipt.native_id)
                elif receipt.stage in _STAGE_TRANSITIONS[old.stage]:
                    effective = replace(receipt,
                                        possible_effect=old.possible_effect or receipt.possible_effect,
                                        retry_safe=old.retry_safe and receipt.retry_safe,
                                        native_id=old.native_id or receipt.native_id)
                elif (receipt.stage in _EARLY_STAGES and
                      (old.stage in _TERMINAL_STAGES or
                       old.stage in {"RUNNING", "WAITING_INPUT", "OUTCOME_UNKNOWN"} or
                       (old.stage in _EARLY_STAGES and
                        _EARLY_RANK[receipt.stage] < _EARLY_RANK[old.stage]))):
                    # Native evidence can race a synchronous write result.
                    # Late weaker receipts may add a native ID, never lower
                    # the durable stage or erase terminal evidence.
                    effective = replace(old, native_id=old.native_id or receipt.native_id)
                elif old.stage in _TERMINAL_STAGES and receipt.stage not in _TERMINAL_STAGES:
                    effective = replace(old, native_id=old.native_id or receipt.native_id)
                else:
                    raise CoreError("OPERATION_STAGE_CONFLICT", "record",
                                    operation_id=receipt.operation_id)
                if effective != old:
                    db.execute("UPDATE operations_v2 SET stage=?,possible_effect=?,retry_safe=?,native_id=?,error_code=? WHERE server_id=? AND executor_id=? AND operation_id=?",
                                     (effective.stage, int(effective.possible_effect),
                                      int(effective.retry_safe), effective.native_id,
                                      effective.error_code, key.server_id,
                                      key.executor_id, key.operation_id))
                db.execute("COMMIT")
                return effective
            except BaseException as exc:
                self._rollback_if_active(db)
                if _sqlite_full(exc):
                    raise CoreError("JOURNAL_FULL", "receipt_record",
                                    possible_effect=True,
                                    operation_id=key.operation_id) from exc
                raise
        return await self._run(_worker_impl, urgent=False)

    async def get_receipt(self, key: OperationKey) -> OperationReceipt | None:
        def _worker_impl(db):
            return self._get(db, key)
        return await self._run(_worker_impl, urgent=False)

    @staticmethod
    def _event_body(event: RuntimeEvent) -> bytes:
        return canonical_json({
            "server_id": event.server_id, "executor_id": event.executor_id,
            "session_id": event.session_id, "stream_epoch": event.stream_epoch,
            "sequence": event.sequence, "category": event.category,
            "native_type": event.native_type, "payload": dict(event.payload),
            "operation_id": event.operation_id,
        })

    @staticmethod
    def _validate_event(event: RuntimeEvent) -> None:
        if (not all((event.server_id, event.executor_id, event.session_id,
                     event.stream_epoch)) or type(event.sequence) is not int or
                event.sequence < 1 or event.sequence > 9007199254740991):
            raise CoreError("EVENT_INVALID", "event_append")

    def _stream(self, db, event: RuntimeEvent) -> tuple[int, int, int]:
        db.execute(
            "INSERT OR IGNORE INTO event_streams VALUES (?,?,?,?,1,0,0)",
            (event.server_id, event.executor_id, event.session_id,
             event.stream_epoch))
        return db.execute(
            "SELECT next_sequence,acked_sequence,compacted_sequence FROM event_streams WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?",
            (event.server_id, event.executor_id, event.session_id,
             event.stream_epoch)).fetchone()

    def _reserve_event(self, db, event: RuntimeEvent, body: bytes) -> None:
        """Reserve payload bytes/items inside the caller's write transaction."""
        size = len(body)
        if size > self.limits.max_event_body_bytes:
            raise CoreError("EVENT_TOO_LARGE", "event_append",
                            possible_effect=True)
        critical = event.category in _CRITICAL_EVENT_CATEGORIES
        self._require_storage_capacity(db, 
            size, critical=critical, stage="event_append",
            possible_effect=True, operation_id=event.operation_id)
        db.execute(
            "INSERT OR IGNORE INTO server_usage VALUES (?,?,0,0)",
            (event.server_id, event.executor_id))
        db.execute(
            "INSERT OR IGNORE INTO session_usage VALUES (?,?,?,0,0)",
            (event.server_id, event.executor_id, event.session_id))
        total_bytes, total_rows = db.execute(
            "SELECT event_bytes,event_rows FROM journal_usage WHERE singleton=1"
        ).fetchone()
        server_bytes, server_rows = db.execute(
            "SELECT event_bytes,event_rows FROM server_usage WHERE server_id=? AND executor_id=?",
            (event.server_id, event.executor_id)).fetchone()
        session_bytes, session_rows = db.execute(
            "SELECT event_bytes,event_rows FROM session_usage WHERE server_id=? AND executor_id=? AND session_id=?",
            (event.server_id, event.executor_id, event.session_id)).fetchone()
        for used_bytes, used_rows, max_bytes, max_rows, reserve_bytes, reserve_rows in (
            (total_bytes, total_rows, self.limits.total_event_bytes,
             self.limits.total_event_rows, self.limits.reserved_event_bytes,
             self.limits.reserved_event_rows),
            (server_bytes, server_rows, self.limits.server_event_bytes,
             self.limits.server_event_rows, self.limits.server_reserved_bytes,
             self.limits.server_reserved_rows),
            (session_bytes, session_rows, self.limits.session_event_bytes,
             self.limits.session_event_rows, self.limits.session_reserved_bytes,
             self.limits.session_reserved_rows),
        ):
            allowed_bytes = max_bytes if critical else max_bytes - reserve_bytes
            allowed_rows = max_rows if critical else max_rows - reserve_rows
            if used_bytes + size > allowed_bytes or used_rows + 1 > allowed_rows:
                raise CoreError("JOURNAL_FULL", "event_append",
                                possible_effect=True)
        db.execute(
            "UPDATE journal_usage SET event_bytes=event_bytes+?,event_rows=event_rows+1 WHERE singleton=1",
            (size,))
        db.execute(
            "UPDATE server_usage SET event_bytes=event_bytes+?,event_rows=event_rows+1 WHERE server_id=? AND executor_id=?",
            (size, event.server_id, event.executor_id))
        db.execute(
            "UPDATE session_usage SET event_bytes=event_bytes+?,event_rows=event_rows+1 WHERE server_id=? AND executor_id=? AND session_id=?",
            (size, event.server_id, event.executor_id, event.session_id))

    def _normal_event_quota_full(self, db, event: RuntimeEvent, size: int) -> bool:
        """Preflight logical budgets before eligible-only maintenance."""
        total = db.execute(
            "SELECT event_bytes,event_rows FROM journal_usage WHERE singleton=1"
        ).fetchone()
        server = db.execute(
            "SELECT event_bytes,event_rows FROM server_usage WHERE server_id=? AND executor_id=?",
            (event.server_id, event.executor_id)).fetchone() or (0, 0)
        session = db.execute(
            "SELECT event_bytes,event_rows FROM session_usage WHERE server_id=? AND executor_id=? AND session_id=?",
            (event.server_id, event.executor_id, event.session_id)).fetchone() or (0, 0)
        return any(
            used_bytes + size > max_bytes - reserve_bytes or
            used_rows + 1 > max_rows - reserve_rows
            for (used_bytes, used_rows), max_bytes, max_rows, reserve_bytes, reserve_rows in (
                (total, self.limits.total_event_bytes,
                 self.limits.total_event_rows, self.limits.reserved_event_bytes,
                 self.limits.reserved_event_rows),
                (server, self.limits.server_event_bytes,
                 self.limits.server_event_rows, self.limits.server_reserved_bytes,
                 self.limits.server_reserved_rows),
                (session, self.limits.session_event_bytes,
                 self.limits.session_event_rows, self.limits.session_reserved_bytes,
                 self.limits.session_reserved_rows),
            )
        )

    def _apply_terminal_event(self, db, event: RuntimeEvent) -> None:
        if (event.category != "turn_state" or not event.operation_id or
                event.payload.get("delivery_phase") != "terminal"):
            return
        stage = {"success": "SUCCEEDED", "failed": "FAILED",
                 "interrupted": "CANCELLED"}.get(
                     event.payload.get("delivery_outcome"))
        if stage is None:
            return
        key = OperationKey(event.server_id, event.executor_id,
                           event.operation_id)
        receipt = self._get(db, key)
        if receipt is None:
            return
        if (receipt.session_id != event.session_id or
                receipt.stage in {"RECEIVED_DURABLE", "PREPARED"}):
            raise CoreError("EVENT_OPERATION_MISMATCH", "event_append",
                            possible_effect=True,
                            operation_id=event.operation_id)
        if receipt.stage in _TERMINAL_STAGES:
            if receipt.stage != stage:
                raise CoreError("OPERATION_STAGE_CONFLICT", "event_append",
                                possible_effect=True,
                                operation_id=event.operation_id)
            return
        if stage not in _STAGE_TRANSITIONS.get(receipt.stage, ()):
            raise CoreError("OPERATION_STAGE_CONFLICT", "event_append",
                            possible_effect=True,
                            operation_id=event.operation_id)
        error_code = None
        if stage == "FAILED":
            error_code = ("PROVIDER_AUTH_REQUIRED" if
                event.payload.get("delivery_error_code") == "PROVIDER_AUTH_REQUIRED"
                else "NATIVE_OPERATION_FAILED")
        db.execute(
            "UPDATE operations_v2 SET stage=?,possible_effect=1,retry_safe=0,error_code=? WHERE server_id=? AND executor_id=? AND operation_id=?",
            (stage, error_code, key.server_id, key.executor_id, key.operation_id))

    async def append_event(self, event: RuntimeEvent) -> None:
        self._validate_event(event)
        body = self._event_body(event)
        critical = event.category in _CRITICAL_EVENT_CATEGORIES
        def _worker_impl(db):
            if (event.category not in _CRITICAL_EVENT_CATEGORIES and
                    len(body) <= self.limits.max_event_body_bytes):
                old = db.execute(
                    "SELECT 1 FROM events WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=? AND sequence=?",
                    (event.server_id, event.executor_id, event.session_id,
                     event.stream_epoch, event.sequence)).fetchone()
                if old is None:
                    self._recover_normal_storage(db, 
                        len(body), stage="event_append", possible_effect=True,
                        operation_id=event.operation_id,
                        logical_pressure=self._normal_event_quota_full(db, 
                            event, len(body)),
                        priority_session=(event.server_id, event.executor_id,
                                          event.session_id))
            db.execute("BEGIN IMMEDIATE")
            try:
                next_sequence, acked_sequence, compacted_sequence = self._stream(db, event)
                if event.sequence <= compacted_sequence:
                    raise CoreError("EVENT_GAP", "event_append")
                old = db.execute(
                    "SELECT body FROM events WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=? AND sequence=?",
                    (event.server_id, event.executor_id, event.session_id,
                     event.stream_epoch, event.sequence)).fetchone()
                if old is not None:
                    if old[0] != body:
                        raise CoreError("EVENT_CONFLICT", "event_append")
                    db.execute("COMMIT")
                    return
                if event.sequence <= acked_sequence:
                    raise CoreError("EVENT_GAP", "event_append")
                self._reserve_event(db, event, body)
                db.execute("INSERT INTO events VALUES (?,?,?,?,?,?)",
                                 (event.server_id, event.executor_id,
                                  event.session_id, event.stream_epoch,
                                  event.sequence, body))
                if event.sequence >= next_sequence:
                    db.execute(
                        "UPDATE event_streams SET next_sequence=? WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?",
                        (event.sequence + 1, event.server_id, event.executor_id,
                         event.session_id, event.stream_epoch))
                self._apply_terminal_event(db, event)
                db.execute("COMMIT")
            except BaseException as exc:
                self._rollback_if_active(db)
                if _sqlite_full(exc):
                    raise CoreError("JOURNAL_FULL", "event_append",
                                    possible_effect=True) from exc
                raise
        return await self._run(_worker_impl, urgent=critical,
                                payload_bytes=len(body))

    async def record_event(self, event: RuntimeEvent) -> RuntimeEvent:
        """Allocate a stable sequence and insert in one SQLite transaction.

        The input's sequence must be zero: callers may not guess/reuse a live
        sequence. SQLite's write transaction serializes separate Core hosts.
        """
        if (type(event.sequence) is not int or event.sequence != 0 or
                not all((event.server_id, event.executor_id,
                         event.session_id, event.stream_epoch))):
            raise CoreError("EVENT_INVALID", "event_append")
        critical = event.category in _CRITICAL_EVENT_CATEGORIES
        def _worker_impl(db):
            if not critical:
                body_size = len(self._event_body(event))
                if body_size <= self.limits.max_event_body_bytes:
                    self._recover_normal_storage(db, 
                        body_size + 16, stage="event_append",
                        possible_effect=True, operation_id=event.operation_id,
                        logical_pressure=self._normal_event_quota_full(db, 
                            event, body_size + 16),
                        priority_session=(event.server_id, event.executor_id,
                                          event.session_id))
            db.execute("BEGIN IMMEDIATE")
            try:
                next_sequence, _, _ = self._stream(db, event)
                numbered = replace(event, sequence=next_sequence)
                body = self._event_body(numbered)
                self._reserve_event(db, numbered, body)
                db.execute("INSERT INTO events VALUES (?,?,?,?,?,?)",
                                 (numbered.server_id, numbered.executor_id,
                                  numbered.session_id, numbered.stream_epoch,
                                  numbered.sequence, body))
                db.execute(
                    "UPDATE event_streams SET next_sequence=? WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?",
                    (next_sequence + 1, numbered.server_id, numbered.executor_id,
                     numbered.session_id, numbered.stream_epoch))
                self._apply_terminal_event(db, numbered)
                db.execute("COMMIT")
                return numbered
            except BaseException as exc:
                self._rollback_if_active(db)
                if _sqlite_full(exc):
                    raise CoreError("JOURNAL_FULL", "event_append",
                                    possible_effect=True) from exc
                raise
        return await self._run(_worker_impl, urgent=critical,
                                payload_bytes=len(self._event_body(event)))

    async def events(self, cursor: EventCursor) -> AsyncIterator[RuntimeEvent]:
        """Replay pages off the loop; no transaction spans a consumer yield."""
        position = cursor.after_sequence
        while True:
            compacted, rows = await self._run(
                lambda db: self._events_page(db, cursor, position))
            if compacted is not None and position < compacted:
                raise CoreError("EVENT_GAP", "event_replay")
            for sequence, body in rows:
                position = sequence
                yield RuntimeEvent(**json.loads(body))
            if len(rows) < _REPLAY_PAGE_ROWS:
                return

    def _events_page(self, db, cursor: EventCursor,
                     position: int) -> tuple[int | None, list]:
        compacted = db.execute(
            "SELECT compacted_sequence FROM event_streams WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?",
            (cursor.server_id, cursor.executor_id, cursor.session_id,
             cursor.stream_epoch)).fetchone()
        rows = db.execute(
            "SELECT sequence,body FROM events WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=? AND sequence>? ORDER BY sequence LIMIT ?",
            (cursor.server_id, cursor.executor_id, cursor.session_id,
             cursor.stream_epoch, position, _REPLAY_PAGE_ROWS)).fetchall()
        return (compacted[0] if compacted is not None else None), rows

    async def contiguous_watermark(self, cursor: EventCursor) -> int:
        def _worker_impl(db):
            stream = db.execute(
                "SELECT acked_sequence FROM event_streams WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?",
                (cursor.server_id, cursor.executor_id, cursor.session_id,
                 cursor.stream_epoch)).fetchone()
            watermark = stream[0] if stream is not None else 0
            while True:
                rows = db.execute(
                    "SELECT sequence FROM events WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=? AND sequence>? ORDER BY sequence LIMIT ?",
                    (cursor.server_id, cursor.executor_id, cursor.session_id,
                     cursor.stream_epoch, watermark,
                     _REPLAY_PAGE_ROWS)).fetchall()
                for (sequence,) in rows:
                    if sequence != watermark + 1:
                        return watermark
                    watermark = sequence
                if len(rows) < _REPLAY_PAGE_ROWS:
                    break
            return watermark
        return await self._run(_worker_impl, urgent=False)

    async def acknowledge_events(self, cursor: EventCursor,
                                 through_sequence: int) -> int:
        """Persist the Server's durable-ingress ACK for a contiguous prefix."""
        if (type(through_sequence) is not int or through_sequence < 0 or
                through_sequence > 9007199254740991):
            raise CoreError("EVENT_INVALID", "event_ack")
        def _worker_impl(db):
            db.execute("BEGIN IMMEDIATE")
            try:
                key = (cursor.server_id, cursor.executor_id,
                       cursor.session_id, cursor.stream_epoch)
                row = db.execute(
                    "SELECT acked_sequence,next_sequence FROM event_streams WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?",
                    key).fetchone()
                if row is None:
                    if through_sequence:
                        raise CoreError("EVENT_GAP", "event_ack")
                    db.execute("COMMIT")
                    return 0
                acked, next_sequence = row
                if through_sequence <= acked:
                    db.execute("COMMIT")
                    return acked
                if through_sequence >= next_sequence:
                    raise CoreError("EVENT_GAP", "event_ack")
                count = db.execute(
                    "SELECT COUNT(*) FROM events WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=? AND sequence>? AND sequence<=?",
                    (*key, acked, through_sequence)).fetchone()[0]
                if count != through_sequence - acked:
                    raise CoreError("EVENT_GAP", "event_ack")
                db.execute(
                    "UPDATE event_streams SET acked_sequence=? WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?",
                    (through_sequence, *key))
                db.execute("COMMIT")
                return through_sequence
            except BaseException:
                self._rollback_if_active(db)
                raise
        return await self._run(_worker_impl, urgent=False)

    async def compact_acked(self, *, max_rows: int = 128) -> tuple[int, int]:
        """Delete only ACKed event bodies; retain sequence and receipts."""
        validate_compaction_rows(max_rows)
        def _worker_impl(db):
            return self._compact_acked_locked(db, max_rows)
        return await self._run(_worker_impl, urgent=False)

    def _compact_acked_locked(self, db,
            max_rows: int, *,
            priority_session: tuple[str, str, str] | None = None) -> tuple[int, int]:
        db.execute("BEGIN IMMEDIATE")
        try:
            priority_order = ""
            parameters: tuple[object, ...] = (max_rows,)
            if priority_session is not None:
                priority_order = """CASE
                    WHEN e.server_id=? AND e.executor_id=? AND e.session_id=? THEN 0
                    WHEN e.server_id=? AND e.executor_id=? THEN 1
                    ELSE 2 END,"""
                parameters = (*priority_session, *priority_session[:2], max_rows)
            rows = db.execute(f"""
                SELECT e.server_id,e.executor_id,e.session_id,e.stream_epoch,
                       e.sequence,length(e.body)
                FROM events AS e JOIN event_streams AS s
                ON e.server_id=s.server_id AND e.executor_id=s.executor_id
                AND e.session_id=s.session_id AND e.stream_epoch=s.stream_epoch
                WHERE e.sequence<=s.acked_sequence
                ORDER BY {priority_order} e.server_id,e.executor_id,e.session_id,e.stream_epoch,e.sequence
                LIMIT ?
            """, parameters).fetchall()
            if not rows:
                db.execute("COMMIT")
                return 0, 0
            compacted: dict[tuple[str, str, str, str], int] = {}
            for server_id, executor_id, session_id, stream_epoch, sequence, _ in rows:
                stream = (server_id, executor_id, session_id, stream_epoch)
                previous = compacted.get(stream)
                if previous is None:
                    previous = db.execute(
                        "SELECT compacted_sequence FROM event_streams WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?",
                        stream).fetchone()[0]
                if sequence != previous + 1:
                    raise CoreError("EVENT_GAP", "event_compact")
                compacted[stream] = sequence
            db.executemany(
                "DELETE FROM events WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=? AND sequence=?",
                [row[:5] for row in rows])
            total_bytes = sum(row[5] for row in rows)
            db.execute(
                "UPDATE journal_usage SET event_bytes=event_bytes-?,event_rows=event_rows-? WHERE singleton=1",
                (total_bytes, len(rows)))
            usage: dict[tuple[str, str], tuple[int, int]] = {}
            for server_id, executor_id, _, _, _, size in rows:
                key = (server_id, executor_id)
                used_bytes, used_rows = usage.get(key, (0, 0))
                usage[key] = used_bytes + size, used_rows + 1
            for (server_id, executor_id), (size, count) in usage.items():
                db.execute(
                    "UPDATE server_usage SET event_bytes=event_bytes-?,event_rows=event_rows-? WHERE server_id=? AND executor_id=?",
                    (size, count, server_id, executor_id))
            sessions: dict[tuple[str, str, str], tuple[int, int]] = {}
            for server_id, executor_id, session_id, _, _, size in rows:
                key = (server_id, executor_id, session_id)
                used_bytes, used_rows = sessions.get(key, (0, 0))
                sessions[key] = used_bytes + size, used_rows + 1
            for (server_id, executor_id, session_id), (size, count) in sessions.items():
                db.execute(
                    "UPDATE session_usage SET event_bytes=event_bytes-?,event_rows=event_rows-? WHERE server_id=? AND executor_id=? AND session_id=?",
                    (size, count, server_id, executor_id, session_id))
            db.execute(
                "DELETE FROM session_usage WHERE event_rows=0 AND event_bytes=0")
            for stream, sequence in compacted.items():
                db.execute(
                    "UPDATE event_streams SET compacted_sequence=? WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?",
                    (sequence, *stream))
            db.execute("COMMIT")
            return len(rows), total_bytes
        except BaseException:
            self._rollback_if_active(db)
            raise

    def close(self) -> None:
        """Transitional synchronous bridge (PC01 transition notes).

        Prefer ``aclose`` from a running loop. This bridge exists for the
        synchronous test/teardown paths; a close timeout raises instead of
        claiming the database is closed.
        """
        self._executor.close(timeout=15.0)

    async def _run(self, impl, *, urgent: bool = False,
                    payload_bytes: int = 0):
        """Submit one complete worker unit and await its durable result."""
        try:
            future = self._executor.submit(
                impl, urgent=urgent, payload_bytes=payload_bytes)
        except ExecutorFull as exc:
            raise CoreError("JOURNAL_BUSY", "journal",
                            retry_safe=True) from exc
        except ExecutorClosed as exc:
            raise CoreError("JOURNAL_CLOSED", "journal",
                            retry_safe=True) from exc
        return await future

    def _run_sync(self, work, *, timeout: float = 30.0):
        """Test/control bridge: run one unit on the worker, blocking here."""
        return self._executor.run_sync(work, timeout=timeout)

    def worker_metrics(self) -> dict[str, object]:
        """Bounded off-loop worker counters (PC01.07); no payloads/secrets."""
        return self._executor.metrics()

    async def aclose(self, *, timeout: float = 10.0) -> str:
        """Drain accepted work and close the worker off the event loop."""
        return await self._executor.aclose(timeout=timeout)
