"""SQLite outbound adapter for the Event Log slice.

Concrete implementations of :class:`EventRepo` (append-only persistence with a
global, monotonic ``event_id``) and :class:`EventEmitter` (the thin facade other
slices use to emit an event INSIDE their active unit of work). Both operate on
``uow.connection`` so the audit event and the state change of the calling slice
commit atomically.

This is an outbound adapter, so it MAY import ``sqlite3`` and the domain
dataclasses. ``event_id`` is the table's ``INTEGER PRIMARY KEY AUTOINCREMENT``:
the WAL single-writer serialises concurrent appends, so every committed event
receives a strictly greater id assigned inside its transaction, never reused and
never modified (the log is append-only - no UPDATE/DELETE paths exist here).
JSON-ish columns (``payload`` / ``target``) are (de)serialised here; timestamps
default to the injected clock (falling back to :func:`utc_now_iso`).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Mapping, Optional

from ....application.ports import Clock, UnitOfWork
from ....domain.base import utc_now_iso
from ....domain.models import Event
from ....errors import ErrorCode, OktoNexusError

_COLUMNS = (
    "event_id, workspace_id, stream, type, actor_agent_id, "
    "payload, visibility, target, created_at"
)


def _dumps(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _loads(text: str | None) -> Any:
    if text is None:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _db_error(action: str, exc: sqlite3.Error) -> OktoNexusError:
    return OktoNexusError(
        ErrorCode.DB_ERROR,
        f"SQLite failure while {action}.",
        {"reason": str(exc)},
    )


class SqliteEventRepo:
    """Append-only persistence for the ``events`` table."""

    def __init__(self, clock: Optional[Clock] = None) -> None:
        self._clock = clock

    def _now(self) -> str:
        if self._clock is not None:
            return self._clock.now_iso()
        return utc_now_iso()

    def append(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        stream: str,
        type: str,
        payload: Mapping[str, Any] | None = None,
        actor_agent_id: str | None = None,
        visibility: str | None = None,
        target: str | None = None,
    ) -> int:
        """Append one event INSIDE ``uow``'s transaction; return its ``event_id``.

        ``event_id`` is assigned by SQLite (AUTOINCREMENT) within the active
        transaction, so under the WAL single-writer it is globally monotonic and
        never reused.
        """
        created_at = self._now()
        try:
            cur = uow.connection.execute(
                """
                INSERT INTO events
                    (workspace_id, stream, type, actor_agent_id,
                     payload, visibility, target, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workspace_id,
                    stream,
                    type,
                    actor_agent_id,
                    _dumps(payload),
                    visibility,
                    _dumps(target),
                    created_at,
                ),
            )
        except sqlite3.Error as exc:
            raise _db_error("appending event", exc) from exc
        event_id = cur.lastrowid
        if event_id is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "event_id was not assigned on append.",
                {"workspace_id": workspace_id, "stream": stream},
            )
        return int(event_id)

    def list_after(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        stream: str,
        cursor: int = 0,
        limit: int = 100,
        filters: Mapping[str, Any] | None = None,
    ) -> list[Event]:
        """Return events with ``event_id > cursor`` for ``(workspace, stream)``.

        Strictly ascending by ``event_id`` (the only ordering, per the spec),
        bounded by ``limit``. Optional column-level ``filters`` (``type`` and
        ``agent_id`` -> ``actor_agent_id``) are honoured for port fidelity; the
        application service passes ``filters=None`` and applies all filtering
        itself so ``next_cursor`` can advance past every discarded event.
        """
        sql = (
            f"SELECT {_COLUMNS} FROM events "
            "WHERE workspace_id = ? AND stream = ? AND event_id > ?"
        )
        params: list[Any] = [workspace_id, stream, int(cursor)]
        if filters:
            if filters.get("type") is not None:
                sql += " AND type = ?"
                params.append(str(filters["type"]))
            if filters.get("agent_id") is not None:
                sql += " AND actor_agent_id = ?"
                params.append(str(filters["agent_id"]))
        sql += " ORDER BY event_id ASC LIMIT ?"
        params.append(int(limit))
        try:
            cur = uow.connection.execute(sql, tuple(params))
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing events", exc) from exc
        return [self._row_to_event(row) for row in rows]

    @staticmethod
    def _row_to_event(row: Any) -> Event:
        return Event(
            event_id=int(row["event_id"]),
            workspace_id=row["workspace_id"],
            stream=row["stream"],
            type=row["type"],
            created_at=row["created_at"],
            actor_agent_id=row["actor_agent_id"],
            payload=_loads(row["payload"]),
            visibility=row["visibility"],
            target=row["target"],
        )


class SqliteEventEmitter:
    """Facade so any slice emits within the SAME unit of work (``emit`` -> append).

    Holds an :class:`SqliteEventRepo`; emitting an event is exactly an append,
    keeping the audit event atomic with the caller's state mutation.
    """

    def __init__(self, repo: SqliteEventRepo) -> None:
        self._repo = repo

    def emit(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        stream: str,
        type: str,
        payload: Mapping[str, Any] | None = None,
        actor_agent_id: str | None = None,
        visibility: str | None = None,
        target: str | None = None,
    ) -> int:
        """Emit an event inside ``uow``; return the assigned ``event_id``."""
        return self._repo.append(
            uow,
            workspace_id=workspace_id,
            stream=stream,
            type=type,
            payload=payload,
            actor_agent_id=actor_agent_id,
            visibility=visibility,
            target=target,
        )
