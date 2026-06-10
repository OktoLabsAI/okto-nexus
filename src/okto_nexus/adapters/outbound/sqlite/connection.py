"""SQLite connection factory and unit of work.

This is the ONLY place (together with the repos and migrations) allowed to
import ``sqlite3``. Every connection is configured with the three mandatory
PRAGMAs (``journal_mode=WAL``, ``foreign_keys=ON``, ``busy_timeout``) and a
``sqlite3.Row`` row factory.

The :class:`SqliteUnitOfWork` runs in the driver's autocommit mode
(``isolation_level=None``) and manages transactions EXPLICITLY via
``BEGIN``/``COMMIT``/``ROLLBACK`` so callers get deterministic boundaries.

Write scopes (the default) open with ``BEGIN IMMEDIATE``: the WAL write lock
is acquired up front, so ``busy_timeout`` applies at the single blocking point
(``BEGIN``) and a read-then-write sequence inside the transaction can never
hit ``SQLITE_BUSY_SNAPSHOT`` mid-way - the failure mode ``busy_timeout`` does
NOT cover. Read-only scopes (``write=False``) keep the deferred ``BEGIN`` so
WAL readers never queue behind writers.
"""

from __future__ import annotations

import sqlite3
import threading
import time

from ....config import NexusConfig
from ....errors import (
    ErrorCode,
    OktoNexusError,
    db_error_from_exception,
    is_retryable_db_exception,
)
from ..waiter import SleepPollWaiter

# Retry budget for the one-time WAL conversion of a fresh database (see
# ConnectionFactory._enable_wal): attempts x sleep bounds the wait to ~1s.
_WAL_RETRY_ATTEMPTS = 20
_WAL_RETRY_SLEEP_SECONDS = 0.05


class SqliteUnitOfWork:
    """Explicit transactional scope over a single SQLite connection.

    Use as a context manager. On clean exit the transaction is committed; on
    exception it is rolled back. The connection is always closed on exit.
    ``write=True`` (the default) opens with ``BEGIN IMMEDIATE``; ``write=False``
    opens a deferred read snapshot.
    """

    def __init__(self, connection: sqlite3.Connection, write: bool = True) -> None:
        self.connection = connection
        self._write = write
        self._active = False

    def __enter__(self) -> "SqliteUnitOfWork":
        statement = "BEGIN IMMEDIATE" if self._write else "BEGIN"
        try:
            self.connection.execute(statement)
        except sqlite3.Error as exc:
            # __exit__ never runs when __enter__ raises: close the connection
            # here. Lock/busy contention surfaces as a retryable DB_ERROR.
            self.connection.close()
            raise db_error_from_exception("starting a transaction", exc) from exc
        self._active = True
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        try:
            if exc_type is not None:
                self.rollback()
            else:
                self.commit()
        finally:
            self.connection.close()
        # Do not suppress exceptions raised inside the with-block.
        return False

    def commit(self) -> None:
        if self._active:
            self.connection.execute("COMMIT")
            self._active = False

    def rollback(self) -> None:
        if self._active:
            self.connection.execute("ROLLBACK")
            self._active = False


class ConnectionFactory:
    """Creates configured SQLite connections and units of work.

    Ensures ``home_dir`` exists (idempotently) at construction time.
    """

    def __init__(self, config: NexusConfig) -> None:
        self._config = config
        # Cached probe connection for ``data_version`` (lazily opened). Guarded
        # by a lock because FastMCP may run tool calls on multiple threads.
        self._probe_conn: sqlite3.Connection | None = None
        self._probe_lock = threading.Lock()
        self.ensure_home_dir()

    @property
    def config(self) -> NexusConfig:
        return self._config

    def ensure_home_dir(self) -> None:
        """Create the home directory if missing (idempotent)."""
        self._config.home_dir.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """Return a connection with the three mandatory PRAGMAs applied.

        Raises ``DB_ERROR`` if the connection cannot be opened/configured.
        """
        try:
            conn = sqlite3.connect(
                str(self._config.db_path),
                isolation_level=None,  # explicit transaction control
            )
            conn.row_factory = sqlite3.Row
            # busy_timeout FIRST: on a fresh database the WAL conversion needs
            # an exclusive lock, and concurrent bootstraps would otherwise race
            # it with the driver's default timeout of 0 ("database is locked").
            conn.execute(f"PRAGMA busy_timeout={int(self._config.busy_timeout_ms)}")
            self._enable_wal(conn)
            conn.execute("PRAGMA foreign_keys=ON")
            return conn
        except sqlite3.Error as exc:
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Failed to open SQLite connection.",
                {"db_path": str(self._config.db_path), "reason": str(exc)},
                retryable=is_retryable_db_exception(exc),
            ) from exc

    @staticmethod
    def _enable_wal(conn: sqlite3.Connection) -> None:
        """``PRAGMA journal_mode=WAL`` with a short bounded retry.

        The one-time conversion of a fresh database to WAL needs an exclusive
        lock, and SQLite can return SQLITE_BUSY on this path WITHOUT consulting
        ``busy_timeout`` (deadlock avoidance) - so N processes bootstrapping
        the same new database would race. An already-WAL database answers the
        pragma lock-free, making this a no-op on every later connection.
        """
        for attempt in range(_WAL_RETRY_ATTEMPTS):
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                return
            except sqlite3.OperationalError as exc:
                last_attempt = attempt >= _WAL_RETRY_ATTEMPTS - 1
                if not is_retryable_db_exception(exc) or last_attempt:
                    raise
                time.sleep(_WAL_RETRY_SLEEP_SECONDS)

    def data_version(self) -> int:
        """Cheap cross-process change probe: ``PRAGMA data_version``.

        Two values returned by THIS method differ iff some OTHER connection
        (any process) committed a change to the database in between - exactly
        the "did anything write?" question the long-poll waiter asks between
        sleeps. The probe runs on ONE cached connection because the pragma is
        connection-local (a fresh connection per call would always report the
        same baseline); the connection is pinned read-only via
        ``PRAGMA query_only=ON`` and never opens a transaction, so probing N
        waiters costs N pragma reads and never touches the WAL writer lock.

        Raises ``DB_ERROR`` (retryable when the underlying error is) only when
        the probe cannot answer even after the cached connection is reopened
        once - callers (``SleepPollWaiter``) degrade to scan-per-interval
        rather than failing the wait.
        """
        with self._probe_lock:
            try:
                return self._probe_data_version()
            except sqlite3.Error:
                self._close_probe_conn()
                try:
                    return self._probe_data_version()
                except sqlite3.Error as exc:
                    self._close_probe_conn()
                    raise OktoNexusError(
                        ErrorCode.DB_ERROR,
                        "PRAGMA data_version probe failed; the change-gating "
                        "connection could not be (re)opened.",
                        {"db_path": str(self._config.db_path), "reason": str(exc)},
                        retryable=is_retryable_db_exception(exc),
                    ) from exc

    def _probe_data_version(self) -> int:
        """Read the pragma on the cached probe connection (open it if needed).

        Caller holds ``_probe_lock``. The connection is shared across threads
        (``check_same_thread=False``) - safe because every use is serialised by
        the lock and consists of a single autocommit pragma read.
        """
        if self._probe_conn is None:
            conn = sqlite3.connect(
                str(self._config.db_path),
                isolation_level=None,
                check_same_thread=False,
            )
            try:
                conn.execute(
                    f"PRAGMA busy_timeout={int(self._config.busy_timeout_ms)}"
                )
                conn.execute("PRAGMA query_only=ON")  # enforced read-only
            except sqlite3.Error:
                conn.close()
                raise
            self._probe_conn = conn
        row = self._probe_conn.execute("PRAGMA data_version").fetchone()
        return int(row[0])

    def _close_probe_conn(self) -> None:
        """Drop the cached probe connection (best-effort close)."""
        if self._probe_conn is not None:
            try:
                self._probe_conn.close()
            except sqlite3.Error:  # pragma: no cover - close never matters
                pass
            self._probe_conn = None

    def change_waiter(self) -> SleepPollWaiter:
        """Build the V1 :class:`Waiter` for this store (see the application port).

        A sleep-poll waiter whose re-scan gate is :meth:`data_version`: the
        long-poll services re-run their SELECT only when a commit happened
        somewhere, instead of once per poll interval. The poll cadence is the
        configured ``poll_interval_ms`` - the same knob the in-service loops
        used before the waiter existed.
        """
        return SleepPollWaiter(
            self.data_version,
            poll_interval_s=self._config.poll_interval_ms / 1000.0,
        )

    def unit_of_work(self, write: bool = True) -> SqliteUnitOfWork:
        """Return a fresh :class:`SqliteUnitOfWork` over a new connection.

        ``write=True`` (default) opens with ``BEGIN IMMEDIATE`` so the scope is
        safe for read-then-write sequences under concurrency; pass
        ``write=False`` ONLY for scopes that never write (deferred snapshot
        read that does not queue behind writers).
        """
        return SqliteUnitOfWork(self.get_connection(), write=write)

    def vacuum(self) -> None:
        """Run ``VACUUM`` to rebuild the database and return freed pages.

        Deleting rows (retention pruning) leaves free pages inside the file;
        only ``VACUUM`` shrinks it on disk. It cannot run inside a transaction,
        so it executes on its own autocommit connection (never via a unit of
        work) and briefly takes an exclusive lock - ``busy_timeout`` applies.
        Raises ``DB_ERROR`` (retryable for lock/busy contention) on failure.
        """
        conn = self.get_connection()
        try:
            conn.execute("VACUUM")
        except sqlite3.Error as exc:
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "VACUUM failed; the store was not compacted. If the error is "
                "retryable the database was briefly busy - retry once writers "
                "quiesce.",
                {"db_path": str(self._config.db_path), "reason": str(exc)},
                retryable=is_retryable_db_exception(exc),
            ) from exc
        finally:
            conn.close()
