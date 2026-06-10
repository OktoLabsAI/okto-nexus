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
    DELIVERY_PARKED,
    DELIVERY_READ,
    DELIVERY_UNREAD,
)
from ....domain.models import Channel, Message, MessageDelivery
from ....errors import ErrorCode, OktoNexusError, db_error_from_exception


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
    # Centralised classification: lock/busy contention => retryable=True.
    return db_error_from_exception(action, exc)


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
    at-least-once pull/ack with lease-based redelivery; ``parked`` is the
    dead-letter lane for deliveries that exhausted their claim ``attempts``.

    Reads are strictly READ-ONLY: an in-flight row whose lease elapsed is
    PROJECTED as ``unread`` via SQL CASE (never swept by an UPDATE), so peek /
    count / history polling never competes for the WAL writer lock. The only
    physical writes are recipient-scoped: ``claim_pending`` / ``mark_read`` /
    ``extend_leases``.
    """

    _COLUMNS = (
        "delivery_id, message_id, recipient_agent_id, status, "
        "delivered_at, lease_expires_at, read_at, created_at"
    )

    # An in-flight row whose lease elapsed at :now - the read-time projection
    # shows/counts it as 'unread' (redeliverable). Parameters: (delivered, now).
    _EXPIRED = (
        "(status = ? AND lease_expires_at IS NOT NULL AND lease_expires_at < ?)"
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

    def claim_pending(
        self,
        uow: UnitOfWork,
        *,
        recipient_agent_id: str,
        limit: int,
        now: str,
        lease_expires_at: str,
        max_attempts: int,
    ) -> list[MessageDelivery]:
        # A SINGLE recipient-scoped statement claims unread rows AND the
        # recipient's own lease-expired redeliveries (no global sweep). The
        # write lock is taken by this first statement, so a concurrent pull
        # serialises here instead of failing on a stale read snapshot.
        # RETURNING tells us exactly which rows THIS call touched; rows whose
        # attempts were already exhausted are parked (dead-letter), not
        # redelivered, and are filtered out of the returned batch.
        try:
            rows = uow.connection.execute(
                f"""
                UPDATE message_deliveries SET
                    status = CASE WHEN attempts < ? THEN ? ELSE ? END,
                    attempts = CASE WHEN attempts < ? THEN attempts + 1
                                    ELSE attempts END,
                    delivered_at = CASE WHEN attempts < ? THEN ? ELSE NULL END,
                    lease_expires_at = CASE WHEN attempts < ? THEN ?
                                            ELSE NULL END
                WHERE delivery_id IN (
                    SELECT delivery_id FROM message_deliveries
                    WHERE recipient_agent_id = ?
                      AND (status = ? OR {self._EXPIRED})
                    ORDER BY created_at ASC, rowid ASC
                    LIMIT ?
                )
                RETURNING rowid, {self._COLUMNS}
                """,
                (
                    int(max_attempts), DELIVERY_DELIVERED, DELIVERY_PARKED,
                    int(max_attempts),
                    int(max_attempts), now,
                    int(max_attempts), lease_expires_at,
                    recipient_agent_id,
                    DELIVERY_UNREAD, DELIVERY_DELIVERED, now,
                    int(limit),
                ),
            ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("claiming inbox deliveries", exc) from exc
        claimed = [r for r in rows if r["status"] == DELIVERY_DELIVERED]
        claimed.sort(key=lambda r: (r["created_at"], r["rowid"]))
        return [self._row(r) for r in claimed]

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

    def extend_leases(
        self,
        uow: UnitOfWork,
        *,
        recipient_agent_id: str,
        message_ids: Sequence[str],
        now: str,
        lease_expires_at: str,
    ) -> list[str]:
        ids = [m for m in message_ids if m]
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        try:
            rows = uow.connection.execute(
                # Only genuinely in-flight rows: delivered AND lease not yet
                # elapsed (an expired lease is redeliverable, not extendable).
                f"UPDATE message_deliveries SET lease_expires_at = ? "
                f"WHERE recipient_agent_id = ? AND status = ? "
                f"AND lease_expires_at IS NOT NULL AND lease_expires_at >= ? "
                f"AND message_id IN ({placeholders}) "
                f"RETURNING message_id",
                (lease_expires_at, recipient_agent_id, DELIVERY_DELIVERED,
                 now, *ids),
            ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("extending inbox leases", exc) from exc
        return [r["message_id"] for r in rows]

    def list_by_status(
        self,
        uow: UnitOfWork,
        *,
        recipient_agent_id: str,
        statuses: Sequence[str],
        now: str,
        limit: int,
    ) -> list[MessageDelivery]:
        sts = list(statuses)
        if not sts:
            return []
        placeholders = ",".join("?" * len(sts))
        # READ-ONLY: the effective lane (and the cleared lease fields of an
        # expired in-flight row) is projected in the SELECT, never UPDATEd.
        try:
            rows = uow.connection.execute(
                f"SELECT delivery_id, message_id, recipient_agent_id, "
                f"CASE WHEN {self._EXPIRED} THEN ? ELSE status END AS status, "
                f"CASE WHEN {self._EXPIRED} THEN NULL ELSE delivered_at END "
                f"AS delivered_at, "
                f"CASE WHEN {self._EXPIRED} THEN NULL ELSE lease_expires_at END "
                f"AS lease_expires_at, "
                f"read_at, created_at "
                f"FROM message_deliveries "
                f"WHERE recipient_agent_id = ? "
                f"AND CASE WHEN {self._EXPIRED} THEN ? ELSE status END "
                f"IN ({placeholders}) "
                f"ORDER BY rowid ASC LIMIT ?",
                (
                    DELIVERY_DELIVERED, now, DELIVERY_UNREAD,
                    DELIVERY_DELIVERED, now,
                    DELIVERY_DELIVERED, now,
                    recipient_agent_id,
                    DELIVERY_DELIVERED, now, DELIVERY_UNREAD,
                    *sts, int(limit),
                ),
            ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing inbox deliveries", exc) from exc
        return [self._row(r) for r in rows]

    def counts(
        self, uow: UnitOfWork, *, recipient_agent_id: str, now: str
    ) -> dict[str, int]:
        try:
            rows = uow.connection.execute(
                f"SELECT CASE WHEN {self._EXPIRED} THEN ? ELSE status END "
                "AS lane, COUNT(*) AS n FROM message_deliveries "
                "WHERE recipient_agent_id = ? GROUP BY lane",
                (DELIVERY_DELIVERED, now, DELIVERY_UNREAD, recipient_agent_id),
            ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("counting inbox deliveries", exc) from exc
        return {row["lane"]: row["n"] for row in rows}

    def list_history(
        self,
        uow: UnitOfWork,
        *,
        recipient_agent_id: str,
        before: tuple[str, str] | None = None,
        limit: int = 100,
    ) -> list[MessageDelivery]:
        sql = (
            f"SELECT {self._COLUMNS} FROM message_deliveries "
            "WHERE recipient_agent_id = ? AND status = ? "
        )
        params: list[Any] = [recipient_agent_id, DELIVERY_READ]
        if before is not None:
            # Keyset boundary (exclusive): strictly older than the last row of
            # the previous page, so interleaved acks can never duplicate items.
            sql += "AND (read_at, delivery_id) < (?, ?) "
            params.extend(before)
        sql += "ORDER BY read_at DESC, delivery_id DESC LIMIT ?"
        params.append(int(limit))
        try:
            rows = uow.connection.execute(sql, tuple(params)).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing inbox history", exc) from exc
        return [self._row(r) for r in rows]

    def list_for_messages(
        self,
        uow: UnitOfWork,
        *,
        recipient_agent_id: str,
        message_ids: Sequence[str],
    ) -> list[MessageDelivery]:
        ids = [m for m in message_ids if m]
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        try:
            rows = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM message_deliveries "
                f"WHERE recipient_agent_id = ? AND message_id IN ({placeholders}) "
                f"ORDER BY rowid ASC",
                (recipient_agent_id, *ids),
            ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("reading inbox deliveries", exc) from exc
        return [self._row(r) for r in rows]

    def list_for_message(
        self, uow: UnitOfWork, *, message_id: str, now: str
    ) -> list[dict[str, Any]]:
        try:
            rows = uow.connection.execute(
                f"SELECT recipient_agent_id, "
                f"CASE WHEN {self._EXPIRED} THEN ? ELSE status END AS status, "
                f"attempts, read_at "
                f"FROM message_deliveries WHERE message_id = ? ORDER BY rowid ASC",
                (DELIVERY_DELIVERED, now, DELIVERY_UNREAD, message_id),
            ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("reading message delivery status", exc) from exc
        return [
            {
                "recipient_agent_id": r["recipient_agent_id"],
                "status": r["status"],
                "attempts": r["attempts"],
                "read_at": r["read_at"],
            }
            for r in rows
        ]

    def count_read_before(self, uow: UnitOfWork, *, cutoff: str) -> int:
        """Count ``read`` (history) rows acknowledged before ``cutoff``.

        The prune dry-run view: matches EXACTLY the predicate of
        :meth:`prune_read_before` (defensive ``COALESCE(read_at, created_at)``
        for a hypothetical read row missing its ``read_at`` stamp).
        """
        try:
            row = uow.connection.execute(
                "SELECT COUNT(*) FROM message_deliveries "
                "WHERE status = ? AND COALESCE(read_at, created_at) < ?",
                (DELIVERY_READ, cutoff),
            ).fetchone()
        except sqlite3.Error as exc:
            raise _db_error("counting prunable deliveries", exc) from exc
        return int(row[0])

    def prune_read_before(
        self, uow: UnitOfWork, *, cutoff: str, limit: int
    ) -> int:
        """Delete up to ``limit`` ``read`` rows acknowledged before ``cutoff``.

        The ONLY delete path on ``message_deliveries``, used exclusively by the
        retention slice. The ``status = 'read'`` predicate is baked into the
        SQL, so the protected lanes are unreachable BY CONSTRUCTION:
        ``unread`` (queued), ``delivered`` (in-flight under a lease) and
        ``parked`` (dead-letter awaiting an operator) rows are never deleted,
        regardless of age - pruning history must never lose an undelivered or
        quarantined message. Bounded by ``limit`` per batch so the WAL writer
        lock is held briefly.
        """
        try:
            cur = uow.connection.execute(
                """
                DELETE FROM message_deliveries WHERE delivery_id IN (
                    SELECT delivery_id FROM message_deliveries
                    WHERE status = ? AND COALESCE(read_at, created_at) < ?
                    ORDER BY COALESCE(read_at, created_at) ASC, delivery_id ASC
                    LIMIT ?
                )
                """,
                (DELIVERY_READ, cutoff, int(limit)),
            )
        except sqlite3.Error as exc:
            raise _db_error("pruning read deliveries", exc) from exc
        return int(cur.rowcount)

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
