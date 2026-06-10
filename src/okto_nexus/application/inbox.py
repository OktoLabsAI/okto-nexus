"""Inbox slice application service - the per-recipient delivery lanes (ADR 0001).

Implements the GLOBAL, index-free message inbox:

* ``pull``    - expire stale leases, then atomically take this recipient's
  ``unread`` deliveries into ``delivered`` (in-flight, under a lease) and
  materialise them with their message body. At-least-once: an unacknowledged
  pull whose lease elapses is redelivered.
* ``ack``     - move the recipient's pulled deliveries to ``read`` (history).
* ``peek``    - non-destructive view of pending (``unread`` + in-flight) items.
* ``count``   - ``{unread, in_flight, read}`` lane sizes.
* ``history`` - the ``read`` lane, newest-first, paginated.

Deliberately workspace-AGNOSTIC: the inbox is keyed by the global ``agent_id``
(a direct message reaches the recipient regardless of where it was sent). The
message body is materialised via the GLOBAL ``MessageRepo.list_by_ids``.

Application layer: depends only on ports + pure domain helpers + the error
catalogue; never imports ``sqlite3``/``mcp`` (enforced by the boundary test).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..domain.inbox import DELIVERY_DELIVERED, DELIVERY_READ, DELIVERY_UNREAD
from ..domain.messages import parse_target
from ..errors import ErrorCode, OktoNexusError

#: Page-size defaults/ceiling for inbox reads (mirrors the message limits).
DEFAULT_INBOX_LIMIT = 50
MAX_INBOX_LIMIT = 200
#: How long a pulled (in-flight) delivery is leased before it is redelivered.
DEFAULT_INBOX_LEASE_TTL_SECONDS = 300


def _iso_plus(now_iso: str, seconds: int) -> str:
    """Return ``now_iso`` (UTC ISO-8601, ``Z``) shifted forward by ``seconds``.

    Emits a FIXED-WIDTH microsecond fraction so the lease timestamp is
    lexicographically comparable with the ``now`` used by the SQL expiry sweep.
    """
    base = now_iso[:-1] + "+00:00" if now_iso.endswith(("Z", "z")) else now_iso
    dt = datetime.fromisoformat(base)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    shifted = dt + timedelta(seconds=seconds)
    return shifted.isoformat(timespec="microseconds").replace("+00:00", "Z")


class InboxService:
    """Use-case orchestration for the per-recipient message inbox."""

    def __init__(
        self,
        *,
        connection_factory: Any,
        deliveries: Any,
        messages: Any,
        agents: Any = None,
        clock: Any,
        lease_ttl_seconds: int = DEFAULT_INBOX_LEASE_TTL_SECONDS,
        default_limit: int = DEFAULT_INBOX_LIMIT,
        max_limit: int = MAX_INBOX_LIMIT,
    ) -> None:
        self._cf = connection_factory
        self._deliveries = deliveries
        self._messages = messages
        self._agents = agents
        self._clock = clock
        self._lease_ttl = int(lease_ttl_seconds)
        self._default_limit = int(default_limit)
        self._max_limit = int(max_limit)

    # ------------------------------------------------------------------ #
    # inbox_pull
    # ------------------------------------------------------------------ #
    def pull(self, *, agent_id: Any, limit: Any = None) -> dict[str, Any]:
        """Take this recipient's unread deliveries into in-flight and return them.

        Index-free: the server tracks per-recipient read state, so the caller
        never supplies a cursor. Opportunistic lease expiry runs first, so a
        previously-pulled-but-unacked delivery whose lease elapsed is redelivered.
        """
        aid = self._require_agent_id(agent_id)
        page_limit = self._clamp_limit(limit)
        now = self._clock.now_iso()
        lease = _iso_plus(now, self._lease_ttl)
        with self._cf.unit_of_work() as uow:
            self._deliveries.expire_leases(uow, now=now)
            batch = self._deliveries.claim_unread(
                uow,
                recipient_agent_id=aid,
                limit=page_limit,
                delivered_at=now,
                lease_expires_at=lease,
            )
            items = self._materialise(uow, batch)
            self._touch(uow, aid, now)
        return {"messages": items, "count": len(items)}

    # ------------------------------------------------------------------ #
    # inbox_ack
    # ------------------------------------------------------------------ #
    def ack(self, *, agent_id: Any, message_ids: Any) -> dict[str, Any]:
        """Move the recipient's deliveries for ``message_ids`` to history (read)."""
        aid = self._require_agent_id(agent_id)
        ids = self._coerce_ids(message_ids)
        now = self._clock.now_iso()
        with self._cf.unit_of_work() as uow:
            acked = self._deliveries.mark_read(
                uow, recipient_agent_id=aid, message_ids=ids, read_at=now
            )
            self._touch(uow, aid, now)
        return {"acknowledged": acked}

    # ------------------------------------------------------------------ #
    # inbox_peek
    # ------------------------------------------------------------------ #
    def peek(self, *, agent_id: Any, limit: Any = None) -> dict[str, Any]:
        """View pending deliveries (unread + in-flight) WITHOUT consuming them.

        Runs opportunistic lease expiry first (like ``pull``/``handoff_list``), so
        an in-flight delivery whose lease elapsed is shown as ``unread`` rather
        than stale ``delivered``; it never consumes an unread delivery.
        """
        aid = self._require_agent_id(agent_id)
        page_limit = self._clamp_limit(limit)
        now = self._clock.now_iso()
        with self._cf.unit_of_work() as uow:
            self._deliveries.expire_leases(uow, now=now)
            rows = self._deliveries.list_by_status(
                uow,
                recipient_agent_id=aid,
                statuses=(DELIVERY_UNREAD, DELIVERY_DELIVERED),
                limit=page_limit,
            )
            items = self._materialise(uow, rows)
        return {"messages": items, "count": len(items)}

    # ------------------------------------------------------------------ #
    # inbox_count
    # ------------------------------------------------------------------ #
    def count(self, *, agent_id: Any) -> dict[str, Any]:
        """Return the recipient's lane sizes ``{unread, in_flight, read}``.

        Runs opportunistic lease expiry first so an elapsed in-flight delivery is
        counted as ``unread`` (redeliverable), not ``in_flight`` - a recipient
        gating ``pull`` on ``unread`` is never misled into skipping it.
        """
        aid = self._require_agent_id(agent_id)
        now = self._clock.now_iso()
        with self._cf.unit_of_work() as uow:
            self._deliveries.expire_leases(uow, now=now)
            counts = self._deliveries.counts(uow, recipient_agent_id=aid)
        return {
            "unread": int(counts.get(DELIVERY_UNREAD, 0)),
            "in_flight": int(counts.get(DELIVERY_DELIVERED, 0)),
            "read": int(counts.get(DELIVERY_READ, 0)),
        }

    # ------------------------------------------------------------------ #
    # inbox_history
    # ------------------------------------------------------------------ #
    def history(
        self, *, agent_id: Any, cursor: Any = None, limit: Any = None
    ) -> dict[str, Any]:
        """List the recipient's acknowledged (read) deliveries, newest-first."""
        aid = self._require_agent_id(agent_id)
        page_limit = self._clamp_limit(limit)
        offset = self._parse_offset(cursor)
        with self._cf.unit_of_work() as uow:
            rows = self._deliveries.list_history(
                uow, recipient_agent_id=aid, offset=offset, limit=page_limit + 1
            )
            has_more = len(rows) > page_limit
            rows = rows[:page_limit]
            items = self._materialise(uow, rows)
        return {
            "messages": items,
            "next_cursor": str(offset + len(rows)) if has_more else None,
            "has_more": has_more,
        }

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _materialise(self, uow: Any, deliveries: Any) -> list[dict[str, Any]]:
        deliveries = list(deliveries)
        if not deliveries:
            return []
        messages = {
            m.message_id: m
            for m in self._messages.list_by_ids(
                uow, message_ids=[d.message_id for d in deliveries]
            )
        }
        return [self._item(d, messages.get(d.message_id)) for d in deliveries]

    @staticmethod
    def _item(delivery: Any, message: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "delivery_id": delivery.delivery_id,
            "message_id": delivery.message_id,
            "status": delivery.status,
            "delivered_at": delivery.delivered_at,
            "lease_expires_at": delivery.lease_expires_at,
            "read_at": delivery.read_at,
        }
        if message is not None:
            data.update(
                {
                    "from_agent_id": message.from_agent_id,
                    "workspace_id": message.workspace_id,
                    "channel_id": message.channel_id,
                    "subject": message.subject,
                    "body": message.body,
                    "target": parse_target(message.target),
                    "artifacts": message.artifacts,
                    "created_at": message.created_at,
                }
            )
        return data

    def _touch(self, uow: Any, agent_id: str, now: str) -> None:
        if self._agents is not None:
            self._agents.touch(uow, agent_id=agent_id, at=now)

    @staticmethod
    def _require_agent_id(agent_id: Any) -> str:
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "agent_id is required to address an inbox.",
                {"agent_id": agent_id},
            )
        return agent_id

    @staticmethod
    def _coerce_ids(message_ids: Any) -> list[str]:
        if message_ids is None:
            return []
        if isinstance(message_ids, str):
            candidates = [message_ids]
        else:
            try:
                candidates = list(message_ids)
            except TypeError:
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    "message_ids must be a string or a list of message_id strings.",
                    {"message_ids_type": type(message_ids).__name__},
                ) from None
        return [str(m) for m in candidates if isinstance(m, str) and m.strip()]

    def _clamp_limit(self, limit: Any) -> int:
        if limit is None:
            return self._default_limit
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "limit must be a positive integer.",
                {"limit": limit},
            )
        if limit < 1:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "limit must be a positive integer.",
                {"limit": limit},
            )
        return min(limit, self._max_limit)

    @staticmethod
    def _parse_offset(cursor: Any) -> int:
        if cursor is None or (isinstance(cursor, str) and not cursor.strip()):
            return 0
        try:
            value = int(str(cursor).strip())
        except (TypeError, ValueError):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "cursor must be a non-negative integer.",
                {"cursor": cursor},
            ) from None
        if value < 0:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "cursor must be a non-negative integer.",
                {"cursor": cursor},
            )
        return value
