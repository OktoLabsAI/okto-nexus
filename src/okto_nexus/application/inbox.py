"""Inbox slice application service - the per-recipient delivery lanes (ADR 0001).

Implements the GLOBAL, index-free message inbox as a robust queue:

* ``pull``    - atomically claim this recipient's claimable deliveries (unread
  + own lease-expired redeliveries) into ``delivered`` (in-flight, under a
  caller-tunable lease) and materialise them with their message body.
  At-least-once: an unacknowledged pull whose lease elapses is redelivered; a
  delivery that exhausts its claim attempts is ``parked`` (dead-letter).
* ``ack``     - move the recipient's pulled deliveries to ``read`` (history).
* ``extend``  - renew the lease of in-flight deliveries (long turns).
* ``peek``    - READ-ONLY, envelope-only view of pending (``unread`` +
  in-flight) items: triage metadata plus a bounded ``body_preview`` /
  ``body_bytes`` instead of the full body (``include_bodies=True`` opts back
  into full bodies; ``pull`` is the consumption path).
* ``count``   - READ-ONLY ``{unread, in_flight, read}`` lane sizes.
* ``history`` - the ``read`` lane, newest-first, keyset-paginated.
* ``message_status`` - READ-ONLY sender-side view of one message's deliveries.

``peek``/``count``/``history``/``message_status`` never write: they run under
``unit_of_work(write=False)`` and the effective lane of a lease-expired
in-flight delivery is computed in the SELECT - polling N agents never
serialises on SQLite's WAL writer lock. The only writers are ``pull``/``ack``/
``extend``, each scoped to a single recipient.

Deliberately workspace-AGNOSTIC: the inbox is keyed by the global ``agent_id``
(a direct message reaches the recipient regardless of where it was sent). The
message body is materialised via the GLOBAL ``MessageRepo.list_by_ids``.

Application layer: depends only on ports + pure domain helpers + the error
catalogue; never imports ``sqlite3``/``mcp`` (enforced by the boundary test).
"""

from __future__ import annotations

import json
from typing import Any

from ..config import DEFAULT_INBOX_LEASE_TTL_SECONDS
from ..domain.base import clamp_limit, iso_plus, utf8_byte_len
from ..domain.base import new_id
from ..domain.inbox import (
    DELIVERY_DELIVERED,
    new_delivery_id,
    DELIVERY_PARKED,
    DELIVERY_READ,
    DELIVERY_UNREAD,
)
from ..domain.messages import (
    MESSAGE_DELIVERED_TYPE,
    MESSAGE_READ_TYPE,
    MESSAGE_STREAM,
    parse_target,
)
from ..errors import ErrorCode, OktoNexusError

#: Page-size defaults/ceiling for inbox reads (mirrors the message limits).
DEFAULT_INBOX_LIMIT = 50
MAX_INBOX_LIMIT = 200
# The in-flight lease TTL is a NexusConfig knob (``inbox_lease_ttl_seconds``,
# env OKTO_NEXUS_INBOX_LEASE_TTL_SECONDS, parsed FAIL-CLOSED at startup); its
# default is imported from config above and re-exported under its historic
# name (``DEFAULT_INBOX_LEASE_TTL_SECONDS``) for call-site compatibility.
#: Clamp bounds for a caller-chosen lease (pull ``lease_seconds`` and extend
#: ``extend_seconds``): LLM turns routinely outlive a fixed short lease, but an
#: unbounded one would freeze redelivery.
MIN_LEASE_SECONDS = 10
MAX_LEASE_SECONDS = 3600
#: Maximum times a delivery may be claimed before it is parked (dead-letter)
#: instead of redelivered. Module constant for now; moves to configuration in
#: a later wave.
DEFAULT_MAX_DELIVERY_ATTEMPTS = 5
#: Characters of ``message.body`` surfaced as ``body_preview`` by the
#: envelope-only ``peek`` projection - enough to triage who/what without
#: materialising up to ``max_inline_bytes`` (64KB) per item in a polling read.
PEEK_BODY_PREVIEW_CHARS = 200

#: Inbox read receipts (opt-out via config.inbox_read_receipts): the body
#: ``kind`` that marks a receipt notification. Receipts NEVER generate
#: receipts (acknowledging one is a terminal act - no ping-pong).
READ_RECEIPT_KIND = "message.read_receipt"

#: Separator of the opaque history cursor (``<read_at>~<delivery_id>``).
_HISTORY_CURSOR_SEP = "~"


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
        event_emitter: Any = None,
        config: Any = None,
    ) -> None:
        self._config = config
        self._cf = connection_factory
        self._deliveries = deliveries
        self._messages = messages
        self._agents = agents
        self._emitter = event_emitter
        self._clock = clock
        self._lease_ttl = int(lease_ttl_seconds)
        self._default_limit = int(default_limit)
        self._max_limit = int(max_limit)

    # ------------------------------------------------------------------ #
    # inbox_pull
    # ------------------------------------------------------------------ #
    def pull(
        self, *, agent_id: Any, limit: Any = None, lease_seconds: Any = None
    ) -> dict[str, Any]:
        """Claim this recipient's claimable deliveries into in-flight and return them.

        Index-free: the server tracks per-recipient read state, so the caller
        never supplies a cursor. A single recipient-scoped claim covers both
        ``unread`` rows and this recipient's lease-expired redeliveries (no
        global sweep). ``lease_seconds`` tunes the lease for long turns
        (clamped to ``MIN_LEASE_SECONDS..MAX_LEASE_SECONDS``); a delivery
        claimed ``DEFAULT_MAX_DELIVERY_ATTEMPTS`` times is parked (dead-letter)
        instead of redelivered.
        """
        aid = self._require_agent_id(agent_id)
        page_limit = self._clamp_limit(limit)
        ttl = self._clamp_lease_seconds(lease_seconds, field="lease_seconds")
        now = self._clock.now_iso()
        lease = iso_plus(now, ttl)
        with self._cf.unit_of_work() as uow:
            batch = self._deliveries.claim_pending(
                uow,
                recipient_agent_id=aid,
                limit=page_limit,
                now=now,
                lease_expires_at=lease,
                max_attempts=DEFAULT_MAX_DELIVERY_ATTEMPTS,
            )
            items = self._materialise(uow, batch)
            # Delivery receipts (sender-visible): one message.delivered per
            # claimed delivery, in the SAME transaction as the lane
            # transition - the receipt exists iff the claim committed.
            # At-least-once means a redelivery emits AGAIN (the receipt
            # mirrors the lane truthfully).
            self._emit_receipts(
                uow, items, type_=MESSAGE_DELIVERED_TYPE, recipient=aid, at=now
            )
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
            acked_ids = self._deliveries.mark_read(
                uow, recipient_agent_id=aid, message_ids=ids, read_at=now
            )
            # Read receipts (sender-visible): one message.read per delivery
            # that ACTUALLY transitioned (an already-read or unknown id never
            # produces a receipt), atomic with the transition itself.
            if acked_ids:
                acked_messages = self._messages.list_by_ids(
                    uow, message_ids=acked_ids
                )
                if self._emitter is not None:
                    read_items = [
                        {
                            "message_id": m.message_id,
                            "workspace_id": m.workspace_id,
                            "from_agent_id": m.from_agent_id,
                        }
                        for m in acked_messages
                    ]
                    self._emit_receipts(
                        uow,
                        read_items,
                        type_=MESSAGE_READ_TYPE,
                        recipient=aid,
                        at=now,
                    )
                self._deliver_read_receipts(uow, acked_messages, reader=aid, at=now)
            self._touch(uow, aid, now)
        return {"acknowledged": len(acked_ids), "read_message_ids": acked_ids}

    # ------------------------------------------------------------------ #
    # inbox_extend
    # ------------------------------------------------------------------ #
    def extend(
        self, *, agent_id: Any, message_ids: Any, extend_seconds: Any
    ) -> dict[str, Any]:
        """Renew the lease of the recipient's IN-FLIGHT deliveries.

        The new lease is ``now + extend_seconds`` (clamped to
        ``MIN_LEASE_SECONDS..MAX_LEASE_SECONDS``). ALL-OR-NOTHING: if any id is
        not currently in-flight (never pulled, lease already expired, already
        acknowledged, parked, or not delivered to this recipient at all) the
        call fails with a per-message reason and NOTHING is extended.
        """
        aid = self._require_agent_id(agent_id)
        ids = list(dict.fromkeys(self._coerce_ids(message_ids)))
        if not ids:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "message_ids must name at least one pulled message whose lease "
                "should be extended.",
                {"message_ids": message_ids},
            )
        seconds = self._clamp_lease_seconds(
            extend_seconds, field="extend_seconds", required=True
        )
        now = self._clock.now_iso()
        lease = iso_plus(now, seconds)
        with self._cf.unit_of_work() as uow:
            extended = self._deliveries.extend_leases(
                uow,
                recipient_agent_id=aid,
                message_ids=ids,
                now=now,
                lease_expires_at=lease,
            )
            if len(extended) != len(ids):
                # Raising rolls back the uow, so the partially-extended leases
                # above are undone (all-or-nothing).
                self._raise_extend_error(uow, aid, ids, extended, now)
            self._touch(uow, aid, now)
        return {"extended": len(extended), "lease_expires_at": lease}

    # ------------------------------------------------------------------ #
    # inbox_peek
    # ------------------------------------------------------------------ #
    def peek(
        self,
        *,
        agent_id: Any,
        limit: Any = None,
        include_parked: Any = False,
        include_bodies: Any = False,
    ) -> dict[str, Any]:
        """View pending deliveries (unread + in-flight) WITHOUT consuming them.

        100% READ-ONLY: nothing is leased, moved, or swept. An in-flight
        delivery whose lease elapsed is shown as ``unread`` (its effective
        lane, computed at read time). ``include_parked=True`` additionally
        surfaces the dead-letter lane.

        Envelope-only by default: each item carries the triage metadata plus
        ``body_preview`` (first ``PEEK_BODY_PREVIEW_CHARS`` characters) and
        ``body_bytes`` (UTF-8 size of the full body) instead of ``body`` -
        a worst-case peek would otherwise materialise up to
        ``limit x max_inline_bytes`` of body text just to poll.
        ``include_bodies=True`` opts back into full bodies; ``pull`` (the
        consumption path) and ``history`` always return them.
        """
        aid = self._require_agent_id(agent_id)
        page_limit = self._clamp_limit(limit)
        for field, value in (
            ("include_parked", include_parked),
            ("include_bodies", include_bodies),
        ):
            if not isinstance(value, bool):
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    f"{field} must be a boolean.",
                    {field: value},
                )
        statuses: tuple[str, ...] = (DELIVERY_UNREAD, DELIVERY_DELIVERED)
        if include_parked:
            statuses = statuses + (DELIVERY_PARKED,)
        now = self._clock.now_iso()
        with self._cf.unit_of_work(write=False) as uow:
            rows = self._deliveries.list_by_status(
                uow,
                recipient_agent_id=aid,
                statuses=statuses,
                now=now,
                limit=page_limit,
            )
            items = self._materialise(uow, rows, include_body=include_bodies)
        return {"messages": items, "count": len(items)}

    # ------------------------------------------------------------------ #
    # inbox_count
    # ------------------------------------------------------------------ #
    def count(self, *, agent_id: Any) -> dict[str, Any]:
        """Return the recipient's lane sizes ``{unread, in_flight, read}``.

        100% READ-ONLY: an elapsed in-flight delivery is COUNTED as ``unread``
        (its effective lane) without sweeping it - a recipient gating ``pull``
        on ``unread`` is never misled into skipping it, and polling never takes
        the writer lock. Parked (dead-letter) deliveries are excluded; inspect
        them with ``peek(include_parked=True)``.
        """
        aid = self._require_agent_id(agent_id)
        now = self._clock.now_iso()
        with self._cf.unit_of_work(write=False) as uow:
            counts = self._deliveries.counts(uow, recipient_agent_id=aid, now=now)
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
        """List the recipient's acknowledged (read) deliveries, newest-first.

        Keyset-paginated: the opaque cursor pins the page boundary to the last
        row already seen, so messages acknowledged between pages can never
        duplicate (or hide) items the way an OFFSET cursor would. READ-ONLY.
        """
        aid = self._require_agent_id(agent_id)
        page_limit = self._clamp_limit(limit)
        before = self._parse_history_cursor(cursor)
        with self._cf.unit_of_work(write=False) as uow:
            rows = self._deliveries.list_history(
                uow, recipient_agent_id=aid, before=before, limit=page_limit + 1
            )
            has_more = len(rows) > page_limit
            rows = rows[:page_limit]
            items = self._materialise(uow, rows)
        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = (
                f"{last.read_at}{_HISTORY_CURSOR_SEP}{last.delivery_id}"
            )
        return {
            "messages": items,
            "next_cursor": next_cursor,
            "has_more": has_more,
        }

    # ------------------------------------------------------------------ #
    # message_status (sender-side)
    # ------------------------------------------------------------------ #
    def message_status(self, *, message_id: Any) -> dict[str, Any]:
        """Return the per-recipient delivery states of a SENT message.

        READ-ONLY sender-side observability (cures the blind sender post-send):
        one entry per recipient with the EFFECTIVE status (``unread`` /
        ``delivered`` / ``read`` / ``parked``; an elapsed in-flight lease reads
        as ``unread``), the claim ``attempts``, and ``read_at``.
        """
        if not isinstance(message_id, str) or not message_id.strip():
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "message_id is required to inspect a message's deliveries.",
                {"message_id": message_id},
            )
        now = self._clock.now_iso()
        with self._cf.unit_of_work(write=False) as uow:
            if not self._messages.list_by_ids(uow, message_ids=[message_id]):
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    "No such message. Pass the message_id returned by "
                    "message_create.",
                    {"message_id": message_id},
                )
            rows = self._deliveries.list_for_message(
                uow, message_id=message_id, now=now
            )
        deliveries = [
            {
                "recipient": r["recipient_agent_id"],
                "status": r["status"],
                "attempts": r["attempts"],
                "read_at": r["read_at"],
            }
            for r in rows
        ]
        return {
            "message_id": message_id,
            "deliveries": deliveries,
            "count": len(deliveries),
        }

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _deliver_read_receipts(
        self, uow: Any, acked_messages: Any, *, reader: str, at: str
    ) -> None:
        """Land ONE read-receipt notification per original sender (opt-out).

        The inbox counterpart of the ``message.read`` event: when enabled
        (``config.inbox_read_receipts``, default true, live-tunable), each
        sender whose message was just acknowledged receives a compact
        notification in ITS OWN inbox - grouped per sender, never for
        self-sends, and NEVER for receipts themselves (acknowledging a
        receipt is terminal; no ping-pong by construction). Skipped when the
        sender is no longer a registered agent.
        """
        if self._config is not None and not getattr(
            self._config, "inbox_read_receipts", True
        ):
            return
        # Group the acked messages per (sender, workspace).
        groups: dict[tuple[str, str], list[Any]] = {}
        for message in acked_messages:
            sender = message.from_agent_id
            if not sender or sender == reader:
                continue  # self-send: you know you read it
            if self._is_receipt(message):
                continue  # receipts never generate receipts
            groups.setdefault((sender, message.workspace_id), []).append(message)
        for (sender, workspace_id), batch in groups.items():
            if self._agents is None or self._agents.get(uow, sender) is None:
                continue
            count = len(batch)
            subject = (
                f"read receipt: {count} message(s) read by {reader}"
                if count > 1
                else f"read receipt: {batch[0].subject or batch[0].message_id} "
                f"read by {reader}"
            )
            body = {
                "kind": READ_RECEIPT_KIND,
                "read_by": reader,
                "read_at": at,
                "message_ids": [m.message_id for m in batch],
                "subjects": [m.subject for m in batch],
            }
            message = self._messages.create(
                uow,
                message_id=new_id("msg"),
                workspace_id=workspace_id,
                from_agent_id=reader,
                target=json.dumps(
                    {"strategy": "direct", "agent_id": sender},
                    ensure_ascii=False,
                ),
                subject=subject,
                body=json.dumps(body, ensure_ascii=False),
                created_at=at,
            )
            self._deliveries.create(
                uow,
                delivery_id=new_delivery_id(),
                message_id=message.message_id,
                recipient_agent_id=sender,
                status=DELIVERY_UNREAD,
                created_at=at,
            )

    @staticmethod
    def _is_receipt(message: Any) -> bool:
        """Whether the message is itself a read receipt (loop guard)."""
        try:
            body = json.loads(message.body or "")
        except (TypeError, ValueError):
            return False
        return isinstance(body, dict) and body.get("kind") == READ_RECEIPT_KIND

    def _emit_receipts(
        self,
        uow: Any,
        items: Any,
        *,
        type_: str,
        recipient: str,
        at: str,
    ) -> None:
        """Emit one sender-visible receipt event per item (same transaction).

        Visibility is ``eligible`` with a DIRECT target at the original
        sender: the receipt shows up ONLY in the sender's event stream (plus
        the operator dashboard) - other agents never learn who read what. A
        wired emitter is optional (legacy embedders without the events slice
        simply skip receipts).
        """
        if self._emitter is None:
            return
        for item in items:
            workspace_id = item.get("workspace_id")
            sender = item.get("from_agent_id")
            if not workspace_id or not sender:
                continue  # message row vanished; no receipt to anchor
            self._emitter.emit(
                uow,
                workspace_id=workspace_id,
                stream=MESSAGE_STREAM,
                type=type_,
                payload={
                    "message_id": item["message_id"],
                    "recipient_agent_id": recipient,
                    "from_agent_id": sender,
                    "at": at,
                },
                actor_agent_id=recipient,
                visibility="eligible",
                target=json.dumps(
                    {"strategy": "direct", "agent_id": sender},
                    ensure_ascii=False,
                ),
            )

    def _materialise(
        self, uow: Any, deliveries: Any, *, include_body: bool = True
    ) -> list[dict[str, Any]]:
        deliveries = list(deliveries)
        if not deliveries:
            return []
        messages = {
            m.message_id: m
            for m in self._messages.list_by_ids(
                uow, message_ids=[d.message_id for d in deliveries]
            )
        }
        return [
            self._item(d, messages.get(d.message_id), include_body=include_body)
            for d in deliveries
        ]

    @staticmethod
    def _item(
        delivery: Any, message: Any, *, include_body: bool = True
    ) -> dict[str, Any]:
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
                    "target": parse_target(message.target),
                    "artifacts": message.artifacts,
                    "created_at": message.created_at,
                }
            )
            if include_body:
                data["body"] = message.body
            else:
                # Envelope-only projection (peek): a bounded preview plus the
                # full UTF-8 size so the recipient can decide whether the
                # message is worth an inbox_pull.
                body = message.body if isinstance(message.body, str) else ""
                data["body_preview"] = body[:PEEK_BODY_PREVIEW_CHARS]
                data["body_bytes"] = utf8_byte_len(body)
        return data

    def _raise_extend_error(
        self, uow: Any, agent_id: str, ids: list[str], extended: Any, now: str
    ) -> None:
        """Raise the precise, per-message reason an extend could not apply."""
        rows = {
            d.message_id: d
            for d in self._deliveries.list_for_messages(
                uow, recipient_agent_id=agent_id, message_ids=ids
            )
        }
        extended_set = set(extended)
        problems: list[dict[str, Any]] = []
        for mid in ids:
            if mid in extended_set:
                continue
            delivery = rows.get(mid)
            if delivery is None:
                problems.append(
                    {
                        "message_id": mid,
                        "status": None,
                        "reason": "this message was never delivered to you; "
                        "check the message_id and your agent_id",
                    }
                )
            elif delivery.status == DELIVERY_DELIVERED:
                # In the extend path a delivered row missed only when its
                # lease already elapsed (effective lane: unread again).
                problems.append(
                    {
                        "message_id": mid,
                        "status": DELIVERY_UNREAD,
                        "reason": "the lease already expired, so the message "
                        "is redeliverable; inbox_pull it again instead of "
                        "extending",
                    }
                )
            elif delivery.status == DELIVERY_UNREAD:
                problems.append(
                    {
                        "message_id": mid,
                        "status": DELIVERY_UNREAD,
                        "reason": "not pulled yet; only in-flight (pulled, "
                        "unacknowledged) messages have a lease to extend - "
                        "inbox_pull it first",
                    }
                )
            elif delivery.status == DELIVERY_READ:
                problems.append(
                    {
                        "message_id": mid,
                        "status": DELIVERY_READ,
                        "reason": "already acknowledged into history; there "
                        "is no lease to extend",
                    }
                )
            else:
                problems.append(
                    {
                        "message_id": mid,
                        "status": delivery.status,
                        "reason": "parked (dead-letter) after exhausting its "
                        "delivery attempts; inspect it with "
                        "inbox_peek(include_parked=true)",
                    }
                )
        all_unknown = all(p["status"] is None for p in problems)
        code = ErrorCode.NOT_FOUND if all_unknown else ErrorCode.INVALID_TRANSITION
        raise OktoNexusError(
            code,
            "inbox_extend applies only to your in-flight (pulled, "
            "unacknowledged, lease still valid) messages; nothing was "
            "extended.",
            {"agent_id": agent_id, "not_in_flight": problems, "now": now},
        )

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
        # Shared pagination grammar (domain.base): one limit parser bus-wide.
        return clamp_limit(limit, default=self._default_limit, maximum=self._max_limit)

    def _clamp_lease_seconds(
        self, seconds: Any, *, field: str, required: bool = False
    ) -> int:
        if seconds is None and not required:
            return self._lease_ttl
        if isinstance(seconds, bool) or not isinstance(seconds, int):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{field} must be an integer number of seconds "
                f"(clamped to {MIN_LEASE_SECONDS}..{MAX_LEASE_SECONDS}).",
                {field: seconds},
            )
        return max(MIN_LEASE_SECONDS, min(seconds, MAX_LEASE_SECONDS))

    @staticmethod
    def _parse_history_cursor(cursor: Any) -> tuple[str, str] | None:
        if cursor is None or (isinstance(cursor, str) and not cursor.strip()):
            return None
        invalid = OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "cursor is opaque: pass back the next_cursor returned by the "
            "previous inbox_history page (or omit it for the first page).",
            {"cursor": cursor},
        )
        if not isinstance(cursor, str):
            raise invalid
        read_at, sep, delivery_id = cursor.partition(_HISTORY_CURSOR_SEP)
        if not sep or not read_at or not delivery_id:
            raise invalid
        return (read_at, delivery_id)
