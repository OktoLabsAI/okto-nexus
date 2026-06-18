"""SQLite read-only queries for the dashboard (Nexus v2, spec S1 / C6).

Concrete :class:`ObservabilityQueries` adapter. Every method is a SELECT -
this module must never write (rule br_5865bb88). Aggregations carry
defensive LIMITs so a pathological store cannot blow up the API payload.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from ....application.ports import UnitOfWork
from ....errors import OktoNexusError, db_error_from_exception

#: Defensive ceilings (FR5: bounded payloads regardless of store size).
MAX_EDGES = 2000
MAX_HANDOFFS = 1000
MAX_SESSIONS = 2000
MAX_CHANNELS = 500


def _loads(text: str | None) -> Any:
    if text is None:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _db_error(action: str, exc: sqlite3.Error) -> OktoNexusError:
    return db_error_from_exception(action, exc)


class SqliteObservabilityQueries:
    """Read-only aggregate queries over the live store."""

    # ------------------------------------------------------------------ #
    def agent_rows(self, uow: UnitOfWork) -> list[dict[str, Any]]:
        try:
            rows = uow.connection.execute(
                """
                SELECT a.agent_id, a.role, a.capabilities, a.last_seen_at,
                       a.api_key_hash, a.is_active,
                       COUNT(s.session_id) AS active_sessions,
                       MAX(s.last_heartbeat_at) AS last_heartbeat_at
                FROM agents a
                LEFT JOIN sessions s
                    ON s.agent_id = a.agent_id AND s.status = 'active'
                GROUP BY a.agent_id
                ORDER BY a.created_at, a.agent_id
                """
            ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("reading agent presence rows", exc) from exc
        return [
            {
                "agent_id": row["agent_id"],
                "role": row["role"],
                "capabilities": _loads(row["capabilities"]) or {},
                "last_seen_at": row["last_seen_at"],
                "api_key_hash": row["api_key_hash"],
                "is_active": bool(row["is_active"]),
                "active_sessions": int(row["active_sessions"] or 0),
                "last_heartbeat_at": row["last_heartbeat_at"],
            }
            for row in rows
        ]

    def inbox_counts(self, uow: UnitOfWork) -> dict[str, dict[str, int]]:
        try:
            rows = uow.connection.execute(
                """
                SELECT recipient_agent_id, status, COUNT(*) AS n
                FROM message_deliveries
                GROUP BY recipient_agent_id, status
                """
            ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("reading inbox lane counts", exc) from exc
        counts: dict[str, dict[str, int]] = {}
        for row in rows:
            counts.setdefault(row["recipient_agent_id"], {})[row["status"]] = int(
                row["n"]
            )
        return counts

    def message_edges(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str | None,
        since_iso: str,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT m.from_agent_id AS from_agent,
                   d.recipient_agent_id AS to_agent,
                   COUNT(*) AS count,
                   MAX(m.created_at) AS last_at,
                   SUM(CASE WHEN d.status = 'unread' THEN 1 ELSE 0 END) AS unread,
                   SUM(CASE WHEN d.status = 'delivered' THEN 1 ELSE 0 END) AS delivered,
                   MAX(COALESCE(d.read_at, d.delivered_at)) AS last_done_at
            FROM message_deliveries d
            JOIN messages m ON m.message_id = d.message_id
            WHERE m.created_at >= ?
        """
        params: list[Any] = [since_iso]
        if workspace_id is not None:
            sql += " AND m.workspace_id = ?"
            params.append(workspace_id)
        sql += (
            " GROUP BY m.from_agent_id, d.recipient_agent_id"
            " ORDER BY count DESC, last_at DESC"
            f" LIMIT {MAX_EDGES}"
        )
        try:
            rows = uow.connection.execute(sql, tuple(params)).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("aggregating message edges", exc) from exc
        return [
            {
                "from": row["from_agent"],
                "to": row["to_agent"],
                "count": int(row["count"]),
                "last_at": row["last_at"],
                "in_flight": {
                    "unread": int(row["unread"] or 0),
                    "delivered": int(row["delivered"] or 0),
                },
                # Most recent COMPLETED hop (pulled or acked) in the pair:
                # the anchor of the dashboard's grey flow-decay edge.
                "last_done_at": row["last_done_at"],
            }
            for row in rows
        ]

    def handoff_rows(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str | None,
        statuses: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT handoff_id, workspace_id, status, created_at, updated_at, "
            "from_agent_id, claimed_by, target, visibility, lease_expires_at "
            "FROM handoffs WHERE 1=1"
        )
        params: list[Any] = []
        if workspace_id is not None:
            sql += " AND workspace_id = ?"
            params.append(workspace_id)
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            sql += f" AND status IN ({placeholders})"
            params.extend(statuses)
        sql += f" ORDER BY created_at DESC, handoff_id LIMIT {MAX_HANDOFFS}"
        try:
            rows = uow.connection.execute(sql, tuple(params)).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("reading handoffs", exc) from exc
        return [
            {
                "handoff_id": row["handoff_id"],
                "workspace_id": row["workspace_id"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "from_agent_id": row["from_agent_id"],
                "claimed_by": row["claimed_by"],
                "target": _loads(row["target"]),
                "visibility": row["visibility"],
                "lease_expires_at": row["lease_expires_at"],
            }
            for row in rows
        ]

    def channel_rows(
        self, uow: UnitOfWork, *, workspace_id: str | None
    ) -> list[dict[str, Any]]:
        sql = "SELECT channel_id, workspace_id, name, created_at FROM channels"
        params: tuple[Any, ...] = ()
        if workspace_id is not None:
            sql += " WHERE workspace_id = ?"
            params = (workspace_id,)
        sql += f" ORDER BY created_at, channel_id LIMIT {MAX_CHANNELS}"
        try:
            rows = uow.connection.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("reading channels", exc) from exc
        return [dict(row) for row in rows]

    def session_rows(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str | None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT session_id, agent_id, workspace_id, status, started_at, "
            "last_heartbeat_at, closed_at FROM sessions WHERE 1=1"
        )
        params: list[Any] = []
        if workspace_id is not None:
            sql += " AND workspace_id = ?"
            params.append(workspace_id)
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += f" ORDER BY started_at DESC, session_id LIMIT {MAX_SESSIONS}"
        try:
            rows = uow.connection.execute(sql, tuple(params)).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("reading sessions", exc) from exc
        return [dict(row) for row in rows]

    def messages_page(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str | None,
        agent_id: str | None,
        channel_id: str | None,
        lane: str | None,
        since_iso: str | None,
        until_iso: str | None,
        page: int,
        page_size: int,
        peer_id: str | None = None,
        from_agent_id: str | None = None,
        to_agent_id: str | None = None,
        undelivered_only: bool = False,
        include_body: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        where = ["1=1"]
        params: list[Any] = []
        if workspace_id is not None:
            where.append("m.workspace_id = ?")
            params.append(workspace_id)
        if channel_id is not None:
            where.append("m.channel_id = ?")
            params.append(channel_id)
        if since_iso is not None:
            where.append("m.created_at >= ?")
            params.append(since_iso)
        if until_iso is not None:
            where.append("m.created_at <= ?")
            params.append(until_iso)
        if agent_id is not None and peer_id is not None:
            # The pair's CONVERSATION, both directions (chat panel).
            where.append(
                "((m.from_agent_id = ? AND EXISTS (SELECT 1 FROM message_deliveries dd "
                "WHERE dd.message_id = m.message_id AND dd.recipient_agent_id = ?)) OR "
                "(m.from_agent_id = ? AND EXISTS (SELECT 1 FROM message_deliveries dd "
                "WHERE dd.message_id = m.message_id AND dd.recipient_agent_id = ?)))"
            )
            params.extend([agent_id, peer_id, peer_id, agent_id])
        elif agent_id is not None:
            where.append(
                "(m.from_agent_id = ? OR EXISTS (SELECT 1 FROM message_deliveries dd "
                "WHERE dd.message_id = m.message_id AND dd.recipient_agent_id = ?))"
            )
            params.extend([agent_id, agent_id])
        # Independent, AND-combined directional filters (dashboard DE/PARA).
        # Compose with agent/peer above and with each other.
        if from_agent_id is not None:
            where.append("m.from_agent_id = ?")
            params.append(from_agent_id)
        if to_agent_id is not None:
            where.append(
                "EXISTS (SELECT 1 FROM message_deliveries dr "
                "WHERE dr.message_id = m.message_id AND dr.recipient_agent_id = ?)"
            )
            params.append(to_agent_id)
        if undelivered_only:
            # Persisted sends that fanned out to NOBODY (failed tab); only
            # meaningful for the agent's OWN sends.
            if agent_id is not None:
                where.append("m.from_agent_id = ?")
                params.append(agent_id)
            where.append(
                "NOT EXISTS (SELECT 1 FROM message_deliveries dn "
                "WHERE dn.message_id = m.message_id)"
            )
        if lane is not None:
            where.append(
                "EXISTS (SELECT 1 FROM message_deliveries dl "
                "WHERE dl.message_id = m.message_id AND dl.status = ?)"
            )
            params.append(lane)
        where_sql = " AND ".join(where)

        try:
            total_row = uow.connection.execute(
                f"SELECT COUNT(*) FROM messages m WHERE {where_sql}", tuple(params)
            ).fetchone()
            total = int(total_row[0])

            offset = (page - 1) * page_size
            rows = uow.connection.execute(
                f"""
                SELECT m.message_id, m.workspace_id, m.channel_id, m.from_agent_id,
                       m.created_at, m.subject, m.body
                FROM messages m WHERE {where_sql}
                ORDER BY m.created_at DESC, m.message_id
                LIMIT ? OFFSET ?
                """,
                tuple(params) + (page_size, offset),
            ).fetchall()

            items: list[dict[str, Any]] = []
            for row in rows:
                deliveries = uow.connection.execute(
                    """
                    SELECT delivery_id, recipient_agent_id, status, created_at,
                           delivered_at, read_at
                    FROM message_deliveries WHERE message_id = ?
                    ORDER BY created_at, delivery_id
                    """,
                    (row["message_id"],),
                ).fetchall()
                body = row["body"] or ""
                item = {
                    "message_id": row["message_id"],
                    "workspace_id": row["workspace_id"],
                    "channel_id": row["channel_id"],
                    "from_agent_id": row["from_agent_id"],
                    "created_at": row["created_at"],
                    "subject": row["subject"],
                    "preview": body[:160],
                    "deliveries": [dict(d) for d in deliveries],
                }
                if include_body:
                    item["body"] = body
                items.append(item)
        except sqlite3.Error as exc:
            raise _db_error("reading message history", exc) from exc
        return items, total

    def conversation_peers(
        self, uow: UnitOfWork, *, agent_id: str
    ) -> dict[str, Any]:
        """Aggregate conversation partners + failed-send count in SQL.

        One UNION of the outbound (per-delivery recipient) and inbound
        (per-sender) directions, grouped per peer - O(peers) rows out,
        regardless of history size, so the chat's peer picker scales.
        """
        try:
            rows = uow.connection.execute(
                """
                SELECT peer, COUNT(*) AS count, MAX(at) AS last_at FROM (
                    SELECT d.recipient_agent_id AS peer, m.created_at AS at
                    FROM messages m
                    JOIN message_deliveries d ON d.message_id = m.message_id
                    WHERE m.from_agent_id = ?
                    UNION ALL
                    SELECT m.from_agent_id AS peer, m.created_at AS at
                    FROM messages m
                    JOIN message_deliveries d ON d.message_id = m.message_id
                    WHERE d.recipient_agent_id = ? AND m.from_agent_id != ?
                )
                GROUP BY peer
                ORDER BY last_at DESC
                """,
                (agent_id, agent_id, agent_id),
            ).fetchall()
            failed_row = uow.connection.execute(
                """
                SELECT COUNT(*) FROM messages m
                WHERE m.from_agent_id = ?
                  AND NOT EXISTS (SELECT 1 FROM message_deliveries dn
                                  WHERE dn.message_id = m.message_id)
                """,
                (agent_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise _db_error("aggregating conversation peers", exc) from exc
        return {
            "items": [dict(row) for row in rows],
            "failed_count": int(failed_row[0]),
        }

    def events_after(
        self,
        uow: UnitOfWork,
        *,
        cursor: int,
        workspace_id: str | None,
        stream: str | None,
        limit: int,
        type_: str | None = None,
        actor_agent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        # type_/actor_agent_id are optional equality filters (dashboard FR1):
        # absent -> no filter (byte-for-byte the prior behaviour). visibility
        # and target travel with the row so the detail modal can show them.
        sql = (
            "SELECT event_id, workspace_id, stream, type, created_at, "
            "actor_agent_id, payload, visibility, target FROM events "
            "WHERE event_id > ?"
        )
        params: list[Any] = [cursor]
        if workspace_id is not None:
            sql += " AND workspace_id = ?"
            params.append(workspace_id)
        if stream is not None:
            sql += " AND stream = ?"
            params.append(stream)
        if type_ is not None:
            sql += " AND type = ?"
            params.append(type_)
        if actor_agent_id is not None:
            sql += " AND actor_agent_id = ?"
            params.append(actor_agent_id)
        sql += " ORDER BY event_id ASC LIMIT ?"
        params.append(limit)
        try:
            rows = uow.connection.execute(sql, tuple(params)).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("reading events after cursor", exc) from exc
        return [
            {
                "event_id": int(row["event_id"]),
                "workspace_id": row["workspace_id"],
                "stream": row["stream"],
                "type": row["type"],
                "created_at": row["created_at"],
                "actor_agent_id": row["actor_agent_id"],
                "payload": _loads(row["payload"]),
                "visibility": row["visibility"],
                "target": _loads(row["target"]),
            }
            for row in rows
        ]

    def distinct_event_types(
        self, uow: UnitOfWork, *, workspace_id: str | None
    ) -> list[str]:
        # Powers the dashboard type filter (FR2): the type vocabulary is open,
        # so the picker is derived from the data, never hardcoded.
        sql = "SELECT DISTINCT type FROM events"
        params: list[Any] = []
        if workspace_id is not None:
            sql += " WHERE workspace_id = ?"
            params.append(workspace_id)
        sql += " ORDER BY type ASC"
        try:
            rows = uow.connection.execute(sql, tuple(params)).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing distinct event types", exc) from exc
        return [row["type"] for row in rows]
