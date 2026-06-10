"""Forward-only SQL migration runner.

Reads ``migrations/NNN_*.sql`` files in numeric order and applies any that are
not yet recorded in ``schema_migrations``. Concurrency/durability invariants:

* Every migration runs in its OWN ``BEGIN IMMEDIATE`` transaction, with the
  ledger re-checked AFTER the write lock is taken - concurrent bootstraps
  (N MCP servers + CLI over one WAL database) serialise instead of racing,
  and each version is applied exactly once.
* Acquiring the lock retries briefly (``_LOCK_RETRY_ATTEMPTS`` x
  ``_LOCK_RETRY_SLEEP_SECONDS``) while another process is mid-migration.
* FAIL-CLOSED: a ledger recording a version NEWER than any migration this
  package ships aborts with ``MIGRATION_ERROR`` (update the package); the
  runner never proceeds silently against an unknown schema.

The runner is idempotent (already-applied versions are skipped) and converts
any failure into :class:`OktoNexusError` with code ``MIGRATION_ERROR``.

Note: migration files are author-controlled and MUST terminate each statement
with ``;`` and must not embed ``;`` inside string/identifier literals (the
splitter is line-based, see :func:`_split_statements`).
"""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

from ....domain.base import utc_now_iso
from ....errors import ErrorCode, OktoNexusError, is_retryable_db_exception
from .connection import ConnectionFactory

_VERSION_RE = re.compile(r"^(\d+)_.*\.sql$")

# Bootstrap lock retry budget: on top of the connection's busy_timeout, each
# BEGIN IMMEDIATE is retried this many times with this sleep, bounding the wait
# for a concurrent process that is mid-migration.
_LOCK_RETRY_ATTEMPTS = 10
_LOCK_RETRY_SLEEP_SECONDS = 0.1


def _default_migrations_dir() -> Path:
    """Locate the packaged ``migrations/`` directory.

    Migrations live INSIDE the package (``okto_nexus/migrations/``) so they ship
    in the wheel (declared as ``package-data``) rather than only resolving in a
    source/editable checkout. The primary lookup is the deterministic
    package-relative path; a walk-upward fallback keeps unusual layouts working.
    Raises ``MIGRATION_ERROR`` if none is found.
    """
    here = Path(__file__).resolve()
    # Primary: this module is okto_nexus/adapters/outbound/sqlite/migrations.py,
    # so parents[3] is the okto_nexus package directory.
    package_dir = here.parents[3] / "migrations"
    if package_dir.is_dir() and any(package_dir.glob("[0-9]*_*.sql")):
        return package_dir
    # Fallback: walk upward (covers atypical/source layouts).
    for parent in here.parents:
        candidate = parent / "migrations"
        if candidate.is_dir() and any(candidate.glob("[0-9]*_*.sql")):
            return candidate
    raise OktoNexusError(
        ErrorCode.MIGRATION_ERROR,
        "Could not locate the migrations directory.",
        {"searched_from": str(here)},
    )


def _split_statements(script: str) -> list[str]:
    """Split a migration script into individual statements.

    Line-based: blank lines and full-line ``--`` comments are dropped; a
    statement boundary is a line whose stripped content ends with ``;``.
    """
    statements: list[str] = []
    buffer: list[str] = []
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(buffer).strip())
            buffer = []
    if buffer:
        statements.append("\n".join(buffer).strip())
    return [s for s in statements if s]


class MigrationRunner:
    """Applies pending SQL migrations atomically."""

    def __init__(
        self,
        connection_factory: ConnectionFactory,
        migrations_dir: Path | None = None,
    ) -> None:
        self._factory = connection_factory
        self._migrations_dir = migrations_dir or _default_migrations_dir()

    @property
    def migrations_dir(self) -> Path:
        return self._migrations_dir

    def _discover(self) -> list[tuple[int, Path]]:
        if not self._migrations_dir.is_dir():
            raise OktoNexusError(
                ErrorCode.MIGRATION_ERROR,
                "Migrations directory does not exist.",
                {"migrations_dir": str(self._migrations_dir)},
            )
        found: list[tuple[int, Path]] = []
        for path in self._migrations_dir.glob("*.sql"):
            match = _VERSION_RE.match(path.name)
            if match is None:
                continue
            found.append((int(match.group(1)), path))
        found.sort(key=lambda item: item[0])
        return found

    def apply(self) -> list[int]:
        """Apply all pending migrations; return the list of versions applied now.

        Idempotent: returns an empty list when the schema is already current.
        Concurrent-safe: each migration commits in its own ``BEGIN IMMEDIATE``
        transaction with the ledger re-checked under the write lock, and the
        lock acquisition retries briefly while another process is migrating.
        Fail-closed: raises ``MIGRATION_ERROR`` when the ledger contains a
        version newer than this package knows. Raises ``MIGRATION_ERROR`` on
        any other failure (rolling back only the failing migration; earlier
        ones stay committed).
        """
        files = self._discover()
        conn = self._factory.get_connection()
        newly_applied: list[int] = []
        try:
            self._ensure_ledger(conn)
            applied = self._applied_versions(conn)
            self._guard_unknown_versions(applied, [v for v, _ in files])
            for version, path in files:
                if version in applied:
                    continue
                if self._apply_one(conn, version, path):
                    newly_applied.append(version)
            return newly_applied
        except Exception as exc:  # noqa: BLE001 - normalised to MIGRATION_ERROR
            if isinstance(exc, OktoNexusError):
                raise
            if is_retryable_db_exception(exc):
                raise OktoNexusError(
                    ErrorCode.MIGRATION_ERROR,
                    "Could not acquire the migration lock: another process held "
                    "it beyond the retry budget. Retry the bootstrap once that "
                    "process finishes migrating.",
                    {"reason": str(exc), "migrations_dir": str(self._migrations_dir)},
                ) from exc
            raise OktoNexusError(
                ErrorCode.MIGRATION_ERROR,
                "Failed to apply migrations.",
                {"reason": str(exc), "migrations_dir": str(self._migrations_dir)},
            ) from exc
        finally:
            conn.close()

    def _ensure_ledger(self, conn: sqlite3.Connection) -> None:
        """Create ``schema_migrations`` if missing, in its own IMMEDIATE txn."""
        self._begin_immediate(conn)
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            conn.execute("COMMIT")
        except Exception:
            _rollback_quietly(conn)
            raise

    @staticmethod
    def _applied_versions(conn: sqlite3.Connection) -> set[int]:
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        return {row[0] for row in rows}

    def _guard_unknown_versions(
        self, applied: set[int], known: list[int]
    ) -> None:
        """Fail closed when the ledger is AHEAD of the code.

        A recorded version greater than every migration this package ships
        means the database was migrated by a NEWER okto-nexus. Running old
        code against that schema risks silent corruption, so abort and tell
        the operator to upgrade - never proceed silently.
        """
        if not applied:
            return
        max_applied = max(applied)
        max_known = max(known) if known else 0
        if max_applied > max_known:
            raise OktoNexusError(
                ErrorCode.MIGRATION_ERROR,
                "The database schema is NEWER than this okto-nexus package "
                f"knows (ledger records migration {max_applied}; this code "
                f"ships up to {max_known}). Update the okto-nexus package "
                "before connecting to this database; refusing to run against "
                "an unknown schema.",
                {
                    "max_applied_version": max_applied,
                    "max_known_version": max_known,
                    "migrations_dir": str(self._migrations_dir),
                },
            )

    @staticmethod
    def _begin_immediate(conn: sqlite3.Connection) -> None:
        """``BEGIN IMMEDIATE`` with a short retry while another process migrates.

        Only transient lock/busy errors are retried (bounded by the module
        retry budget); any other failure propagates immediately. Exhausting
        the budget re-raises the last lock error (normalised by ``apply``).
        """
        for attempt in range(_LOCK_RETRY_ATTEMPTS):
            try:
                conn.execute("BEGIN IMMEDIATE")
                return
            except sqlite3.OperationalError as exc:
                last_attempt = attempt >= _LOCK_RETRY_ATTEMPTS - 1
                if not is_retryable_db_exception(exc) or last_attempt:
                    raise
                time.sleep(_LOCK_RETRY_SLEEP_SECONDS)

    def _apply_one(self, conn: sqlite3.Connection, version: int, path: Path) -> bool:
        """Apply ONE migration inside its own ``BEGIN IMMEDIATE`` transaction.

        Re-checks the ledger AFTER taking the write lock (a concurrent
        bootstrap may have applied this version meanwhile) and returns whether
        THIS process applied it. On failure only this migration rolls back;
        previously committed migrations remain durable.
        """
        script = path.read_text(encoding="utf-8")
        self._begin_immediate(conn)
        try:
            row = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version = ?", (version,)
            ).fetchone()
            if row is not None:
                conn.execute("COMMIT")
                return False
            for statement in _split_statements(script):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, utc_now_iso()),
            )
            conn.execute("COMMIT")
            return True
        except Exception as exc:  # noqa: BLE001 - normalised to MIGRATION_ERROR
            _rollback_quietly(conn)
            if isinstance(exc, OktoNexusError):
                raise  # pragma: no cover - defensive (no nested runner errors)
            raise OktoNexusError(
                ErrorCode.MIGRATION_ERROR,
                f"Failed to apply migration {version} ({path.name}).",
                {
                    "version": version,
                    "file": path.name,
                    "reason": str(exc),
                    "migrations_dir": str(self._migrations_dir),
                },
            ) from exc


def _rollback_quietly(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("ROLLBACK")
    except sqlite3.Error:  # pragma: no cover - rollback best-effort
        pass
