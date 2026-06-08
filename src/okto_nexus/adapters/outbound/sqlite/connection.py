"""SQLite connection factory and unit of work.

This is the ONLY place (together with the repos and migrations) allowed to
import ``sqlite3``. Every connection is configured with the three mandatory
PRAGMAs (``journal_mode=WAL``, ``foreign_keys=ON``, ``busy_timeout``) and a
``sqlite3.Row`` row factory.

The :class:`SqliteUnitOfWork` runs in the driver's autocommit mode
(``isolation_level=None``) and manages transactions EXPLICITLY via
``BEGIN``/``COMMIT``/``ROLLBACK`` so callers get deterministic boundaries.
"""

from __future__ import annotations

import sqlite3

from ....config import NexusConfig
from ....errors import ErrorCode, OktoNexusError


class SqliteUnitOfWork:
    """Explicit transactional scope over a single SQLite connection.

    Use as a context manager. On clean exit the transaction is committed; on
    exception it is rolled back. The connection is always closed on exit.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self._active = False

    def __enter__(self) -> "SqliteUnitOfWork":
        self.connection.execute("BEGIN")
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
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(f"PRAGMA busy_timeout={int(self._config.busy_timeout_ms)}")
            return conn
        except sqlite3.Error as exc:
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Failed to open SQLite connection.",
                {"db_path": str(self._config.db_path), "reason": str(exc)},
            ) from exc

    def unit_of_work(self) -> SqliteUnitOfWork:
        """Return a fresh :class:`SqliteUnitOfWork` over a new connection."""
        return SqliteUnitOfWork(self.get_connection())
