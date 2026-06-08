"""Forward-only SQL migration runner.

Reads ``migrations/NNN_*.sql`` files in numeric order, applies any that are not
yet recorded in ``schema_migrations``, and does so inside a single explicit
transaction. The runner is idempotent (already-applied versions are skipped)
and converts any failure into :class:`OktoNexusError` with code
``MIGRATION_ERROR``.

Note: migration files are author-controlled and MUST terminate each statement
with ``;`` and must not embed ``;`` inside string/identifier literals (the
splitter is line-based, see :func:`_split_statements`).
"""

from __future__ import annotations

import re
from pathlib import Path

from ....domain.base import utc_now_iso
from ....errors import ErrorCode, OktoNexusError
from .connection import ConnectionFactory

_VERSION_RE = re.compile(r"^(\d+)_.*\.sql$")


def _default_migrations_dir() -> Path:
    """Locate the project ``migrations/`` directory robustly.

    Walks upward from this file looking for a ``migrations`` directory that
    contains at least one ``NNN_*.sql`` file. Raises ``MIGRATION_ERROR`` if
    none is found.
    """
    here = Path(__file__).resolve()
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
        Raises ``MIGRATION_ERROR`` on any failure (after rolling back).
        """
        files = self._discover()
        conn = self._factory.get_connection()
        newly_applied: list[int] = []
        try:
            conn.execute("BEGIN")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
            applied = {row[0] for row in rows}

            for version, path in files:
                if version in applied:
                    continue
                script = path.read_text(encoding="utf-8")
                for statement in _split_statements(script):
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) "
                    "VALUES (?, ?)",
                    (version, utc_now_iso()),
                )
                newly_applied.append(version)

            conn.execute("COMMIT")
            return newly_applied
        except Exception as exc:  # noqa: BLE001 - normalised to MIGRATION_ERROR
            try:
                conn.execute("ROLLBACK")
            except Exception:  # pragma: no cover - rollback best-effort
                pass
            if isinstance(exc, OktoNexusError):
                raise
            raise OktoNexusError(
                ErrorCode.MIGRATION_ERROR,
                "Failed to apply migrations.",
                {"reason": str(exc), "migrations_dir": str(self._migrations_dir)},
            ) from exc
        finally:
            conn.close()
