"""SQLite outbound adapters for the Channels & Messages slice.

Concrete implementations of :class:`ChannelRepo` and :class:`MessageRepo` (from
:mod:`okto_nexus.application.ports`). Every method operates on ``uow.connection``
inside the caller's active transaction, so the message row and its
``message.created`` event commit atomically within a single unit of work.

This is an outbound adapter, so it MAY import ``sqlite3`` and the domain
dataclasses. JSON-ish columns (``artifacts``) are (de)serialised here; the
routing ``target`` is stored as opaque TEXT (already serialised by the domain
layer). Messages are ordered by ``rowid`` ASC, which - because the table is
append-only and SQLite's WAL serialises writers - is exactly the order in which
``event_id`` values were assigned. Timestamps default to the injected clock
(falling back to :func:`utc_now_iso`).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional, Sequence

from ....application.ports import Clock, UnitOfWork
from ....domain.base import utc_now_iso
from ....domain.inbox import (
    DELIVERY_DELIVERED,
    DELIVERY_READ,
    DELIVERY_UNREAD,
)
from ....domain.models import Channel, Message, MessageDelivery
from ....errors import ErrorCode, OktoNexusError


def _dumps_list(value: Any) -> str:
    items = list(value) if value is not None else []
    return json.dumps(items, ensure_ascii=False)


def _loads_list(text: str | None) -> list[Any]:
    if text is None:
        return []
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return []
    return list(parsed) if isinstance(parsed, list) else []


def _db_error(action: str, exc: sqlite3.Error) -> OktoNexusError:
    return OktoNexusError(
        ErrorCode.DB_ERROR,
        f"SQLite failure while {action}.",
        {"reason": str(exc)},
    )


class _ClockBacked:
    """Mixin providing a ``_now`` timestamp from an optional injected clock."""

    def __init__(self, clock: Optional[Clock] = None) -> None:
        self._clock = clock

    def _now(self) -> str:
        if self._clock is not None:
            return self._clock.now_iso()
        return utc_now_iso()


class SqliteChannelRepo(_ClockBacked):
    """Persistence for ``channels`` rows (unique per ``(workspace_id, name)``)."""

    _COLUMNS = "channel_id, workspace_id, name, created_at"

    def create(
        self,
        uow: UnitOfWork,
        *,
        channel_id: str,
        workspace_id: str,
        name: str,
        created_at: str | None = None,
    ) -> Channel:
        now = created_at or self._now()
        try:
            uow.connection.execute(
                """
                INSERT INTO channels (channel_id, workspace_id, name, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (channel_id, workspace_id, name, now),
            )
        except sqlite3.Error as exc:
            raise _db_error("creating channel", exc) from exc
        row = self.get(uow, workspace_id=workspace_id, channel_id=channel_id)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Channel missing immediately after insert.",
                {"channel_id": channel_id},
            )
        return row

    def get(
        self, uow: UnitOfWork, *, workspace_id: str, channel_id: str
    ) -> Channel | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM channels "
                "WHERE workspace_id = ? AND channel_id = ?",
                (workspace_id, channel_id),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise _db_error("reading channel", exc) from exc
        return self._row_to_channel(row) if row is not None else None

    def get_by_name(
        self, uow: UnitOfWork, *, workspace_id: str, name: str
    ) -> Channel | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM channels "
                "WHERE workspace_id = ? AND name = ?",
                (workspace_id, name),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise _db_error("reading channel by name", exc) from exc
        return self._row_to_channel(row) if row is not None else None

    def list(self, uow: UnitOfWork, *, workspace_id: str) -> list[Channel]:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM channels "
                "WHERE workspace_id = ? ORDER BY created_at, name",
                (workspace_id,),
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing channels", exc) from exc
        return [self._row_to_channel(row) for row in rows]

    @staticmethod
    def _row_to_channel(row: Any) -> Channel:
        return Channel(
            channel_id=row["channel_id"],
            workspace_id=row["workspace_id"],
            name=row["name"],
            created_at=row["created_at"],
        )


class SqliteMessageRepo(_ClockBacked):
    """Persistence for ``messages`` rows (workspace-scoped, append-only)."""

    _COLUMNS = (
        "message_id, workspace_id, channel_id, from_agent_id, from_session_id, "
        "target, subject, body, artifacts, parent_message_id, created_at"
    )

    def create(
        self,
        uow: UnitOfWork,
        *,
        message_id: str,
        workspace_id: str,
        from_agent_id: str,
        channel_id: str | None = None,
        from_session_id: str | None = None,
        target: str | None = None,
        subject: str | None = None,
        body: str | None = None,
        artifacts: Sequence[Any] | None = None,
        parent_message_id: str | None = None,
        created_at: str | None = None,
    ) -> Message:
        now = created_at or self._now()
        try:
            uow.connection.execute(
                """
                INSERT INTO messages
                    (message_id, workspace_id, channel_id, from_agent_id,
                     from_session_id, target, subject, body, artifacts,
                     parent_message_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    workspace_id,
                    channel_id,
                    from_agent_id,
                    from_session_id,
                    target,
                    subject,
                    body,
                    _dumps_list(artifacts),
                    parent_message_id,
                    now,
                ),
            )
        except sqlite3.Error as exc:
            raise _db_error("creating message", exc) from exc
        row = self.get(uow, workspace_id=workspace_id, message_id=message_id)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Message missing immediately after insert.",
                {"message_id": message_id},
            )
        return row

    def get(
        self, uow: UnitOfWork, *, workspace_id: str, message_id: str
    ) -> Message | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM messages "
                "WHERE workspace_id = ? AND message_id = ?",
                (workspace_id, message_id),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise _db_error("reading message", exc) from exc
        return self._row_to_message(row) if row is not None else None

    def list(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        channel_id: str | None = None,
        target: str | None = None,
        limit: int = 100,
    ) -> list[Message]:
        sql = f"SELECT {self._COLUMNS} FROM messages WHERE workspace_id = ?"
        params: list[Any] = [workspace_id]
        if channel_id is not None:
            sql += " AND channel_id = ?"
            params.append(channel_id)
        if target is not None:
            sql += " AND target = ?"
            params.append(target)
        # rowid ASC == insertion order == event_id order (append-only table).
        sql += " ORDER BY rowid ASC LIMIT ?"
        params.append(int(limit))
        try:
            cur = uow.connection.execute(sql, tuple(params))
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing messages", exc) from exc
        return [self._row_to_message(row) for row in rows]

    def list_by_ids(
        self, uow: UnitOfWork, *, message_ids: Sequence[str]
    ) -> list[Message]:
        ids = [m for m in message_ids if m]
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        try:
            rows = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM messages "
                f"WHERE message_id IN ({placeholders})",
                tuple(ids),
            ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing messages by id", exc) from exc
        return [self._row_to_message(row) for row in rows]

    @staticmethod
    def _row_to_message(row: Any) -> Message:
        return Message(
            message_id=row["message_id"],
            workspace_id=row["workspace_id"],
            from_agent_id=row["from_agent_id"],
            created_at=row["created_at"],
            channel_id=row["channel_id"],
            from_session_id=row["from_session_id"],
            target=row["target"],
            subject=row["subject"],
            body=row["body"],
            artifacts=_loads_list(row["artifacts"]),
            parent_message_id=row["parent_message_id"],
        )


class SqliteMessageDeliveryRepo(_ClockBacked):
    """Persistence for ``message_deliveries`` rows - the GLOBAL inbox (ADR 0001).

    Deliberately NOT ``workspace_id``-scoped: an agent's inbox spans every
    workspace. The ``unread`` -> ``delivered`` (leased) -> ``read`` lanes back the
    at-least-once pull/ack with lease-based redelivery.
    """

    _COLUMNS = (
        "delivery_id, message_id, recipient_agent_id, status, "
        "delivered_at, lease_expires_at, read_at, created_at"
    )

    def create(
        self,
        uow: UnitOfWork,
        *,
        delivery_id: str,
        message_id: str,
        recipient_agent_id: str,
        status: str,
        created_at: str | None = None,
    ) -> MessageDelivery:
        now = created_at or self._now()
        try:
            uow.connection.execute(
                "INSERT INTO message_deliveries "
                "(delivery_id, message_id, recipient_agent_id, status, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (delivery_id, message_id, recipient_agent_id, status, now),
            )
        except sqlite3.Error as exc:
            raise _db_error("creating message delivery", exc) from exc
        return MessageDelivery(
            delivery_id=delivery_id,
            message_id=message_id,
            recipient_agent_id=recipient_agent_id,
            status=status,
            created_at=now,
        )

    def claim_unread(
        self,
        uow: UnitOfWork,
        *,
        recipient_agent_id: str,
        limit: int,
        delivered_at: str,
        lease_expires_at: str,
    ) -> list[MessageDelivery]:
        conn = uow.connection
        try:
            ids = [
                r["delivery_id"]
                for r in conn.execute(
                    "SELECT delivery_id FROM message_deliveries "
                    "WHERE recipient_agent_id = ? AND status = ? "
                    "ORDER BY rowid ASC LIMIT ?",
                    (recipient_agent_id, DELIVERY_UNREAD, int(limit)),
                ).fetchall()
            ]
            if not ids:
                return []
            placeholders = ",".join("?" * len(ids))
            # Conditional update: only rows STILL unread are taken (guards a
            # concurrent pull). delivered_at/lease stamp this call's batch.
            conn.execute(
                f"UPDATE message_deliveries "
                f"SET status = ?, delivered_at = ?, lease_expires_at = ? "
                f"WHERE status = ? AND delivery_id IN ({placeholders})",
                (
                    DELIVERY_DELIVERED,
                    delivered_at,
                    lease_expires_at,
                    DELIVERY_UNREAD,
                    *ids,
                ),
            )
            rows = conn.execute(
                f"SELECT {self._COLUMNS} FROM message_deliveries "
                f"WHERE delivery_id IN ({placeholders}) "
                f"AND status = ? AND delivered_at = ? "
                f"ORDER BY rowid ASC",
                (*ids, DELIVERY_DELIVERED, delivered_at),
            ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("claiming inbox deliveries", exc) from exc
        return [self._row(r) for r in rows]

    def expire_leases(self, uow: UnitOfWork, *, now: str) -> int:
        try:
            cur = uow.connection.execute(
                "UPDATE message_deliveries "
                "SET status = ?, delivered_at = NULL, lease_expires_at = NULL "
                "WHERE status = ? AND lease_expires_at IS NOT NULL "
                "AND lease_expires_at < ?",
                (DELIVERY_UNREAD, DELIVERY_DELIVERED, now),
            )
        except sqlite3.Error as exc:
            raise _db_error("expiring inbox leases", exc) from exc
        return cur.rowcount

    def mark_read(
        self,
        uow: UnitOfWork,
        *,
        recipient_agent_id: str,
        message_ids: Sequence[str],
        read_at: str,
    ) -> int:
        ids = [m for m in message_ids if m]
        if not ids:
            return 0
        placeholders = ",".join("?" * len(ids))
        try:
            cur = uow.connection.execute(
                f"UPDATE message_deliveries SET status = ?, read_at = ? "
                f"WHERE recipient_agent_id = ? AND status IN (?, ?) "
                f"AND message_id IN ({placeholders})",
                (
                    DELIVERY_READ,
                    read_at,
                    recipient_agent_id,
                    DELIVERY_UNREAD,
                    DELIVERY_DELIVERED,
                    *ids,
                ),
            )
        except sqlite3.Error as exc:
            raise _db_error("acknowledging inbox deliveries", exc) from exc
        return cur.rowcount

    def list_by_status(
        self,
        uow: UnitOfWork,
        *,
        recipient_agent_id: str,
        statuses: Sequence[str],
        limit: int,
    ) -> list[MessageDelivery]:
        sts = list(statuses)
        if not sts:
            return []
        placeholders = ",".join("?" * len(sts))
        try:
            rows = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM message_deliveries "
                f"WHERE recipient_agent_id = ? AND status IN ({placeholders}) "
                f"ORDER BY rowid ASC LIMIT ?",
                (recipient_agent_id, *sts, int(limit)),
            ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing inbox deliveries", exc) from exc
        return [self._row(r) for r in rows]

    def counts(self, uow: UnitOfWork, *, recipient_agent_id: str) -> dict[str, int]:
        try:
            rows = uow.connection.execute(
                "SELECT status, COUNT(*) AS n FROM message_deliveries "
                "WHERE recipient_agent_id = ? GROUP BY status",
                (recipient_agent_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("counting inbox deliveries", exc) from exc
        return {row["status"]: row["n"] for row in rows}

    def list_history(
        self,
        uow: UnitOfWork,
        *,
        recipient_agent_id: str,
        offset: int = 0,
        limit: int = 100,
    ) -> list[MessageDelivery]:
        try:
            rows = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM message_deliveries "
                "WHERE recipient_agent_id = ? AND status = ? "
                "ORDER BY rowid DESC LIMIT ? OFFSET ?",
                (recipient_agent_id, DELIVERY_READ, int(limit), int(offset)),
            ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing inbox history", exc) from exc
        return [self._row(r) for r in rows]

    @staticmethod
    def _row(row: Any) -> MessageDelivery:
        return MessageDelivery(
            delivery_id=row["delivery_id"],
            message_id=row["message_id"],
            recipient_agent_id=row["recipient_agent_id"],
            status=row["status"],
            created_at=row["created_at"],
            delivered_at=row["delivered_at"],
            lease_expires_at=row["lease_expires_at"],
            read_at=row["read_at"],
        )
