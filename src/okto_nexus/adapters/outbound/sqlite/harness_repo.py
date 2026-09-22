"""SQLite repositories for harness-connector session/event durability (D10).

Concrete implementations of :class:`~okto_nexus.application.ports.HarnessSessionRepo`
and :class:`~okto_nexus.application.ports.HarnessEventRepo` (migration 029).
Both operate purely on ``uow.connection`` like every other repo in this
package; neither is ever consulted by the supervisor to decide whether a
session is currently LIVE (that is the supervisor's in-memory registry, D1) -
these are the durability-only writes made ALONGSIDE the in-memory push, never
gating it.

Round-trips a stored row straight back into the FROZEN
:class:`~okto_nexus.domain.harness.HarnessSession` /
:class:`~okto_nexus.domain.harness.HarnessEvent` dataclasses, so callers never
see a persistence-only shape distinct from the domain type the connector port
already speaks.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from ....application.ports import Clock, UnitOfWork
from ....domain.harness import HarnessCapabilities, HarnessEvent, HarnessSession
from ....errors import db_error_from_exception


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loads(text: str | None, default: Any) -> Any:
    if text is None:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def _db_error(action: str, exc: sqlite3.Error) -> Exception:
    return db_error_from_exception(action, exc)


def _capabilities_to_dict(caps: HarnessCapabilities) -> dict[str, Any]:
    return {
        "send_only": caps.send_only,
        "steer_timing": caps.steer_timing,
        "interrupt_requires_settle_wait": caps.interrupt_requires_settle_wait,
        "multiplexes_sessions": caps.multiplexes_sessions,
        "observes_session_end": caps.observes_session_end,
    }


class SqliteHarnessSessionRepo:
    """Persistence for ``harness_sessions`` rows."""

    _COLUMNS = (
        "session_id, kind, owning_agent_id, status, capabilities, metadata, "
        "started_at, ended_at, created_at, updated_at, endpoint_id, workspace_id, presence_session_id, lifecycle_state"
    )

    def __init__(self, clock: Optional[Clock] = None) -> None:
        # Accepted for constructor-shape parity with every sibling
        # Sqlite*Repo (`build_repos()` wires them all as ``SqliteXRepo(clock)``
        # uniformly) - unused here because every timestamp this repo writes
        # is a REQUIRED argument on the port (``create``/``update_status``
        # never fall back to "now"), unlike the optional-``created_at``
        # repos elsewhere in this package.
        self._clock = clock

    def create(
        self, uow: UnitOfWork, *, session: HarnessSession, created_at: str
    ) -> None:
        try:
            uow.connection.execute(
                """
                INSERT INTO harness_sessions
                    (session_id, kind, owning_agent_id, status, capabilities,
                     metadata, started_at, ended_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.harness_kind,
                    session.owning_agent_id,
                    session.status,
                    _dumps(_capabilities_to_dict(session.capabilities)),
                    _dumps(dict(session.metadata)) if session.metadata else None,
                    session.started_at,
                    session.ended_at,
                    created_at,
                    created_at,
                ),
            )
        except sqlite3.Error as exc:
            raise _db_error("creating harness session", exc) from exc

    def update_status(
        self,
        uow: UnitOfWork,
        *,
        session_id: str,
        status: str,
        updated_at: str,
        ended_at: str | None = None,
    ) -> bool:
        try:
            cur = uow.connection.execute(
                """
                UPDATE harness_sessions
                SET status = ?, ended_at = COALESCE(?, ended_at), updated_at = ?
                WHERE session_id = ?
                """,
                (status, ended_at, updated_at, session_id),
            )
        except sqlite3.Error as exc:
            raise _db_error("updating harness session status", exc) from exc
        return cur.rowcount > 0

    def get(self, uow: UnitOfWork, *, session_id: str) -> HarnessSession | None:
        try:
            row = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM harness_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise _db_error("reading harness session", exc) from exc
        return self._row(row) if row is not None else None

    def list(
        self, uow: UnitOfWork, *, status: str | None = None
    ) -> list[HarnessSession]:
        try:
            if status is not None:
                rows = uow.connection.execute(
                    f"SELECT {self._COLUMNS} FROM harness_sessions "
                    "WHERE status = ? ORDER BY started_at DESC, session_id DESC",
                    (status,),
                ).fetchall()
            else:
                rows = uow.connection.execute(
                    f"SELECT {self._COLUMNS} FROM harness_sessions "
                    "ORDER BY started_at DESC, session_id DESC"
                ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing harness sessions", exc) from exc
        return [self._row(row) for row in rows]

    @staticmethod
    def _row(row: Any) -> HarnessSession:
        caps = _loads(row["capabilities"], {})
        return HarnessSession(
            session_id=row["session_id"],
            harness_kind=row["kind"],
            owning_agent_id=row["owning_agent_id"],
            status=row["status"],
            capabilities=HarnessCapabilities(**caps),
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            metadata=_loads(row["metadata"], {}),
            endpoint_id=row["endpoint_id"], workspace_id=row["workspace_id"],
            presence_session_id=row["presence_session_id"], lifecycle_state=row["lifecycle_state"],
        )


class SqliteHarnessEventRepo:
    """Persistence for ``harness_events`` rows (append-only)."""

    _COLUMNS = (
        "session_id, harness_kind, kind, native_event, payload, thread_id, "
        "turn_id, occurred_at, event_id, sequence"
    )

    def __init__(self, clock: Optional[Clock] = None) -> None:
        # See SqliteHarnessSessionRepo.__init__ - kept for constructor-shape
        # parity only; every timestamp here is a required argument too.
        self._clock = clock

    def append(
        self, uow: UnitOfWork, *, event_id: str, event: HarnessEvent, created_at: str
    ) -> int:
        """Insert ``event``; return the assigned per-session ``sequence``.

        ``sequence`` is computed as ``MAX(sequence) + 1`` for this
        ``session_id`` INSIDE the same call, under the WAL single-writer
        transaction the active ``uow`` already holds - concurrent appends to
        the SAME session serialise (as every other write in this store
        does), so no race can assign the same sequence twice, and the
        ``UNIQUE(session_id, sequence)`` constraint on the table is the
        structural backstop if that invariant is ever violated.
        """
        try:
            existing = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM harness_events WHERE event_id=?", (event_id,)
            ).fetchone()
            if existing is not None:
                stored = self._row(existing)
                from dataclasses import replace
                if replace(stored, event_id=None, sequence=None) != replace(event, event_id=None, sequence=None):
                    raise ValueError("Harness event identity collision")
                if event.sequence is not None and stored.sequence != event.sequence:
                    raise ValueError("Harness event sequence collision")
                return int(existing["sequence"])
            row = uow.connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM harness_events "
                "WHERE session_id = ?",
                (event.session_id,),
            ).fetchone()
            sequence = event.sequence if event.sequence is not None else int(row[0])
            uow.connection.execute(
                """
                INSERT INTO harness_events
                    (event_id, session_id, harness_kind, kind, native_event,
                     payload, thread_id, turn_id, occurred_at, sequence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    event.session_id,
                    event.harness_kind,
                    event.kind,
                    event.native_event,
                    _dumps(dict(event.payload)) if event.payload else None,
                    event.thread_id,
                    event.turn_id,
                    event.occurred_at,
                    sequence,
                    created_at,
                ),
            )
        except sqlite3.Error as exc:
            raise _db_error("appending harness event", exc) from exc
        return sequence

    def list_for_session(
        self,
        uow: UnitOfWork,
        *,
        session_id: str,
        after_sequence: int = 0,
        limit: int = 200,
    ) -> list[HarnessEvent]:
        try:
            rows = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM harness_events "
                "WHERE session_id = ? AND sequence > ? "
                "ORDER BY sequence ASC LIMIT ?",
                (session_id, int(after_sequence), int(limit)),
            ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing harness events", exc) from exc
        return [self._row(row) for row in rows]

    @staticmethod
    def _row(row: Any) -> HarnessEvent:
        return HarnessEvent(
            session_id=row["session_id"],
            harness_kind=row["harness_kind"],
            kind=row["kind"],
            native_event=row["native_event"],
            occurred_at=row["occurred_at"],
            payload=_loads(row["payload"], {}),
            thread_id=row["thread_id"],
            turn_id=row["turn_id"],
            event_id=row["event_id"],
            sequence=row["sequence"],
        )
