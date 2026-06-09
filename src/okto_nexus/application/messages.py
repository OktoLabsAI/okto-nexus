"""Channels & Messages slice application service.

Implements the four use cases this slice OWNS:

* ``message_create`` - persist a message row AND emit exactly one
  ``message.created`` event INSIDE the same SQLite unit of work (both commit or
  both roll back - atomic coupling);
* ``message_get``    - workspace-scoped single read (cross-workspace -> NOT_FOUND),
  honouring the IMPORTED routing visibility predicate;
* ``message_list``   - workspace-scoped, channel-filtered, event-ordered listing
  with cursor pagination (``next_cursor`` / ``has_more``) and visibility filtering;
* ``channel_list``   - return the per-workspace seeded channels.

Application layer: depends only on the ports in
:mod:`okto_nexus.application.ports`, the pure :mod:`okto_nexus.domain` helpers,
and the error catalogue. It NEVER imports ``sqlite3`` nor ``mcp`` (enforced by
the import-boundary test). All transaction control flows through the injected
``ConnectionFactory`` port; ``event_id`` assignment is delegated to the IMPORTED
:class:`EventEmitter` (owned by the Event Log slice), never redefined here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional

from ..domain.ids import resolve_realpath, resolve_workspace_id
from ..domain.messages import (
    MESSAGE_CREATED_TYPE,
    MESSAGE_STREAM,
    SEED_CHANNEL_NAMES,
    can_view_message,
    enforce_inline_size,
    new_channel_id,
    new_message_id,
    normalize_artifacts,
    parse_target,
    require_message_fields,
    serialize_target,
    validate_target,
)
from ..domain.models import Channel, Message
from ..domain.routing import RoutingAgent
from ..errors import ErrorCode, OktoNexusError
from .ports import (
    AgentRepo,
    ChannelRepo,
    Clock,
    ConnectionFactory,
    EventEmitter,
    EventWaiter,
    MessageRepo,
    UnitOfWork,
    WorkspaceRepo,
)

#: Default page size for ``message_list`` when the caller omits ``limit``.
DEFAULT_MESSAGE_LIMIT = 50

#: Hard ceiling on a single ``message_list`` page.
MAX_MESSAGE_LIMIT = 200

#: Upper bound on the rows scanned from the repo for one ``message_list`` call.
#: The repo returns messages ordered by insertion (== event_id order); the
#: service applies visibility filtering and cursor slicing on top, so it needs
#: the full candidate window to compute ``has_more`` without gaps.
_LIST_SCAN_CAP = 100_000


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


class MessageService:
    """Use-case orchestration for channels and messages."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        channels: ChannelRepo,
        messages: MessageRepo,
        workspaces: WorkspaceRepo,
        event_emitter: EventEmitter,
        clock: Clock,
        max_inline_bytes: int,
        agents: Optional[AgentRepo] = None,
        event_waiter: Optional[EventWaiter] = None,
    ) -> None:
        self._cf = connection_factory
        self._channels = channels
        self._messages = messages
        self._workspaces = workspaces
        self._agents = agents
        self._emitter = event_emitter
        self._waiter = event_waiter
        self._clock = clock
        self._max_inline_bytes = int(max_inline_bytes)

    # ------------------------------------------------------------------ #
    # message_create
    # ------------------------------------------------------------------ #
    def create_message(
        self,
        *,
        project_root: Any,
        from_agent_id: Any,
        subject: Any = None,
        body: Any = None,
        channel_id: Any = None,
        from_session_id: Any = None,
        target: Any = None,
        artifacts: Any = None,
        parent_message_id: Any = None,
    ) -> dict[str, Any]:
        """Persist a message and emit ``message.created`` atomically.

        On ANY rejection (workspace, validation, content size, unknown channel,
        unknown/cross-workspace parent, or a failed event append) neither the
        message row nor the event persists - the whole unit of work rolls back.
        """
        workspace_id, root_realpath = self._resolve_workspace(project_root)
        now = self._clock.now_iso()

        # Pure, write-free validation first (no row / event on rejection).
        require_message_fields(from_agent_id, subject, body)
        enforce_inline_size(subject, body, self._max_inline_bytes)
        validate_target(target, now)
        artifact_refs = normalize_artifacts(artifacts)

        if self._emitter is None:  # pragma: no cover - wiring guard
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                "No EventEmitter is wired; message.created cannot be emitted.",
                {},
            )

        target_text = serialize_target(target)
        target_echo = parse_target(target_text)
        channel = channel_id if _is_nonempty_str(channel_id) else None
        parent = parent_message_id if _is_nonempty_str(parent_message_id) else None
        message_id = new_message_id()

        with self._cf.unit_of_work() as uow:
            self._ensure_workspace(uow, workspace_id, root_realpath, now)
            self._require_channel(uow, workspace_id, channel)
            self._require_parent(uow, workspace_id, channel, parent)

            message = self._messages.create(
                uow,
                message_id=message_id,
                workspace_id=workspace_id,
                from_agent_id=from_agent_id,
                channel_id=channel,
                from_session_id=from_session_id if _is_nonempty_str(from_session_id) else None,
                target=target_text,
                subject=subject,
                body=body,
                artifacts=artifact_refs,
                parent_message_id=parent,
                created_at=now,
            )

            if self._agents is not None:
                self._agents.touch(uow, agent_id=from_agent_id, at=now)

            # Emit the single message.created event INSIDE this transaction; the
            # event_id is assigned by the Event Log slice within the same commit.
            event_payload: dict[str, Any] = {
                "message_id": message.message_id,
                "channel_id": message.channel_id,
                "from_agent_id": message.from_agent_id,
                "target": target_echo,
                "subject": message.subject,
                "created_at": message.created_at,
            }
            event_id = self._emitter.emit(
                uow,
                workspace_id=workspace_id,
                stream=MESSAGE_STREAM,
                type=MESSAGE_CREATED_TYPE,
                payload=event_payload,
                actor_agent_id=message.from_agent_id,
                visibility="eligible" if target_text else "public",
                target=target_text,
            )

            data = self._message_to_data(message, target_echo=target_echo)
            data["event_id"] = event_id
        return data

    # ------------------------------------------------------------------ #
    # message_get
    # ------------------------------------------------------------------ #
    def get_message(
        self, *, project_root: Any, message_id: Any, viewer_agent_id: Any = None
    ) -> dict[str, Any]:
        """Return a single workspace-scoped message or ``NOT_FOUND``.

        The same ``message_id`` requested under a different workspace - or a
        directed message the viewer is not eligible to see - is indistinguishable
        from a non-existent message and yields ``NOT_FOUND``.
        """
        if not _is_nonempty_str(message_id):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "message_id is required.",
                {"message_id": message_id},
            )
        workspace_id, _ = self._resolve_workspace(project_root)
        now = self._clock.now_iso()
        with self._cf.unit_of_work() as uow:
            message = self._messages.get(
                uow, workspace_id=workspace_id, message_id=message_id
            )
            if message is None:
                raise self._not_found_message(message_id)
            viewer = self._build_viewer(uow, workspace_id, viewer_agent_id)
            if not can_view_message(
                viewer, target=message.target, created_at=message.created_at, now=now
            ):
                raise self._not_found_message(message_id)
            return self._message_to_data(message)

    # ------------------------------------------------------------------ #
    # message_list
    # ------------------------------------------------------------------ #
    def list_messages(
        self,
        *,
        project_root: Any,
        channel_id: Any = None,
        cursor: Any = None,
        limit: Any = None,
        viewer_agent_id: Any = None,
    ) -> dict[str, Any]:
        """List workspace messages ordered by event_id, with cursor pagination.

        Messages are returned in strictly ascending insertion order (== event_id
        order). Directed messages are only visible to eligible viewers; broadcast
        messages are visible to all. ``cursor`` is the offset into the visible
        sequence; the response carries ``next_cursor`` and ``has_more``.
        """
        workspace_id, _ = self._resolve_workspace(project_root)
        offset = self._coerce_cursor(cursor)
        page_size = self._coerce_limit(limit)
        channel = channel_id if _is_nonempty_str(channel_id) else None
        now = self._clock.now_iso()

        with self._cf.unit_of_work() as uow:
            rows = self._messages.list(
                uow,
                workspace_id=workspace_id,
                channel_id=channel,
                limit=_LIST_SCAN_CAP,
            )
            viewer = self._build_viewer(uow, workspace_id, viewer_agent_id)
            visible = [
                m
                for m in rows
                if can_view_message(
                    viewer, target=m.target, created_at=m.created_at, now=now
                )
            ]
            page = visible[offset : offset + page_size]
            has_more = len(visible) > offset + len(page)
            next_cursor = offset + len(page) if has_more else None
            return {
                "messages": [self._message_to_data(m) for m in page],
                "next_cursor": next_cursor,
                "has_more": has_more,
            }

    # ------------------------------------------------------------------ #
    # message_wait
    # ------------------------------------------------------------------ #
    def wait_messages(
        self,
        *,
        project_root: Any,
        agent_id: Any,
        channel_id: Any = None,
        cursor: Any = None,
        limit: Any = None,
        timeout_seconds: Any = None,
    ) -> dict[str, Any]:
        """Long-poll for new messages, returning them MATERIALISED with body.

        This use case REUSES the Event Log slice's ``event_wait`` (via the
        injected :class:`EventWaiter` port) rather than reimplementing the
        poll/sleep loop: it waits on ``message.created`` events on the
        ``workspace`` stream, then materialises each referenced message (subject,
        body, artifacts, ...) under the SAME visibility predicate
        (:func:`can_view_message`) so a directed message is only ever surfaced to
        an eligible viewer.

        ``cursor`` is the event-log ``event_id`` cursor (NOT the visible-sequence
        offset used by ``message_list``); ``next_cursor`` / ``has_more`` /
        ``timed_out`` are propagated verbatim from the underlying ``event_wait``,
        so cursor semantics are INHERITED: on a NON-EMPTY page ``next_cursor``
        advances past every scanned event (including non-visible ones, never
        re-scanned); on a TIMEOUT (no visible event in range) it returns the
        ENTRY cursor unchanged and the still-hidden range is re-scanned on the
        next poll. An optional ``channel_id`` further filters the materialised
        page (channel-filtered messages were visible events, so the cursor had
        already advanced past them).

        ``agent_id`` is REQUIRED (it scopes visibility) and validated by the
        underlying ``event_wait``; the canonical request errors
        (WORKSPACE_REQUIRED / WORKSPACE_UNRESOLVED / VALIDATION_ERROR for
        cursor/limit/timeout) surface unchanged from there.
        """
        if self._waiter is None:
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                "No EventWaiter is wired; message_wait cannot long-poll the log.",
                {},
            )
        channel = channel_id if _is_nonempty_str(channel_id) else None

        # Delegate the blocking long-poll (and ALL request validation) to the
        # Event Log slice; filter to message.created on the observable stream.
        page = self._waiter.event_wait(
            project_root=project_root,
            agent_id=agent_id,
            stream=MESSAGE_STREAM,
            cursor=cursor,
            limit=limit,
            filters={"type": MESSAGE_CREATED_TYPE},
            timeout_seconds=timeout_seconds,
        )

        messages = self._materialise_wait_page(
            project_root=project_root,
            viewer_agent_id=agent_id,
            channel_id=channel,
            events=page.get("events", []),
        )
        return {
            "messages": messages,
            "next_cursor": page.get("next_cursor"),
            "has_more": page.get("has_more", False),
            "timed_out": page.get("timed_out", False),
        }

    def _materialise_wait_page(
        self,
        *,
        project_root: Any,
        viewer_agent_id: Any,
        channel_id: str | None,
        events: Any,
    ) -> list[dict[str, Any]]:
        """Resolve ``message.created`` events into full message dicts (with body).

        Each event payload carries only a ``message_id`` reference (never the
        body), so the row is loaded and re-checked against ``can_view_message``
        (defence in depth: ``event_wait`` already applied ``can_agent_see_event``,
        and both delegate to the SAME routing eligibility rule with the same
        viewer and target, so the two gates agree). A row that vanished, is not
        visible, or is outside ``channel_id`` is skipped. The cursor is owned by
        ``event_wait`` and is never adjusted here.

        Visibility - including the ``direct_with_fallback`` time window - is
        inherited verbatim from ``event_wait`` / ``can_agent_see_event``, so it
        is identical to what ``event_get`` / ``event_wait`` show the same agent.
        """
        if not events:
            return []
        workspace_id, _ = self._resolve_workspace(project_root)
        now = self._clock.now_iso()
        out: list[dict[str, Any]] = []
        with self._cf.unit_of_work() as uow:
            viewer = self._build_viewer(uow, workspace_id, viewer_agent_id)
            for event in events:
                payload = event.get("payload") if isinstance(event, Mapping) else None
                message_id = payload.get("message_id") if isinstance(payload, Mapping) else None
                if not _is_nonempty_str(message_id):
                    continue
                message = self._messages.get(
                    uow, workspace_id=workspace_id, message_id=message_id
                )
                if message is None:
                    continue
                if not can_view_message(
                    viewer, target=message.target, created_at=message.created_at, now=now
                ):
                    continue
                if channel_id is not None and message.channel_id != channel_id:
                    continue
                out.append(self._message_to_data(message))
        return out

    # ------------------------------------------------------------------ #
    # channel_list
    # ------------------------------------------------------------------ #
    def list_channels(self, *, project_root: Any) -> dict[str, Any]:
        """Return the per-workspace seeded channels (seeding idempotently first)."""
        workspace_id, root_realpath = self._resolve_workspace(project_root)
        now = self._clock.now_iso()
        with self._cf.unit_of_work() as uow:
            self._ensure_workspace(uow, workspace_id, root_realpath, now)
            self._seed_channels(uow, workspace_id, now)
            channels = self._channels.list(uow, workspace_id=workspace_id)
            return {"channels": [self._channel_to_data(c) for c in channels]}

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _resolve_workspace(self, project_root: Any) -> tuple[str, str]:
        """Resolve ``project_root`` -> ``(workspace_id, root_realpath)``.

        Absent/blank -> ``WORKSPACE_REQUIRED``; present but irresolvable ->
        ``WORKSPACE_UNRESOLVED`` (no fallback to a default/shared workspace).
        """
        if not _is_nonempty_str(project_root):
            raise OktoNexusError(
                ErrorCode.WORKSPACE_REQUIRED,
                "project_root is required to resolve the workspace.",
                {},
            )
        root_realpath = resolve_realpath(project_root)  # WORKSPACE_UNRESOLVED
        workspace_id = resolve_workspace_id(project_root)
        return workspace_id, root_realpath

    def _ensure_workspace(
        self, uow: UnitOfWork, workspace_id: str, root_realpath: str, now: str
    ) -> None:
        """Idempotently ensure the ``workspaces`` row exists (FK parent)."""
        self._workspaces.upsert(
            uow,
            workspace_id=workspace_id,
            root_realpath=root_realpath,
            last_seen_at=now,
        )

    def _seed_channels(self, uow: UnitOfWork, workspace_id: str, now: str) -> None:
        """Create any missing seeded channels for the workspace (idempotent)."""
        for name in SEED_CHANNEL_NAMES:
            if self._channels.get_by_name(uow, workspace_id=workspace_id, name=name) is None:
                self._channels.create(
                    uow,
                    channel_id=new_channel_id(),
                    workspace_id=workspace_id,
                    name=name,
                    created_at=now,
                )

    def _require_channel(
        self, uow: UnitOfWork, workspace_id: str, channel_id: str | None
    ) -> None:
        if channel_id is None:
            return
        if self._channels.get(uow, workspace_id=workspace_id, channel_id=channel_id) is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "channel_id does not reference a channel in this workspace.",
                {"channel_id": channel_id},
            )

    def _require_parent(
        self,
        uow: UnitOfWork,
        workspace_id: str,
        channel_id: str | None,
        parent_message_id: str | None,
    ) -> None:
        if parent_message_id is None:
            return
        parent = self._messages.get(
            uow, workspace_id=workspace_id, message_id=parent_message_id
        )
        # A parent that exists only in another workspace reads as None here and
        # is therefore indistinguishable from a non-existent parent.
        if parent is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "parent_message_id does not reference a message in this workspace.",
                {"parent_message_id": parent_message_id},
            )
        if channel_id is not None and parent.channel_id != channel_id:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "parent_message_id is not in the same channel as the reply.",
                {"parent_message_id": parent_message_id, "channel_id": channel_id},
            )

    def _build_viewer(
        self, uow: UnitOfWork, workspace_id: str, viewer_agent_id: Any
    ) -> RoutingAgent | None:
        """Build the routing view of the requesting agent (or ``None``).

        ``None`` requests an unfiltered read. When an ``agents`` repo is wired,
        the viewer's ``role``/``capabilities`` are loaded so capability/role
        routing targets resolve correctly; for direct targets the id suffices.
        """
        if not _is_nonempty_str(viewer_agent_id):
            return None
        role: str | None = None
        capabilities: Any = None
        if self._agents is not None:
            agent = self._agents.get(uow, viewer_agent_id)
            if agent is not None:
                role = agent.role
                capabilities = agent.capabilities
        return RoutingAgent(
            agent_id=viewer_agent_id,
            workspace_id=workspace_id,
            role=role,
            capabilities=capabilities,
        )

    @staticmethod
    def _coerce_cursor(cursor: Any) -> int:
        if cursor is None:
            return 0
        try:
            value = int(cursor)
        except (TypeError, ValueError):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "cursor must be a non-negative integer.",
                {"cursor": cursor},
            ) from None
        return value if value > 0 else 0

    @staticmethod
    def _coerce_limit(limit: Any) -> int:
        if limit is None:
            return DEFAULT_MESSAGE_LIMIT
        try:
            value = int(limit)
        except (TypeError, ValueError):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "limit must be a positive integer.",
                {"limit": limit},
            ) from None
        if value < 1:
            return DEFAULT_MESSAGE_LIMIT
        return min(value, MAX_MESSAGE_LIMIT)

    @staticmethod
    def _not_found_message(message_id: Any) -> OktoNexusError:
        return OktoNexusError(
            ErrorCode.NOT_FOUND,
            "message_id does not reference a message in this workspace.",
            {"message_id": message_id},
        )

    @staticmethod
    def _message_to_data(
        message: Message, *, target_echo: Any = "__derive__"
    ) -> dict[str, Any]:
        echo = parse_target(message.target) if target_echo == "__derive__" else target_echo
        return {
            "message_id": message.message_id,
            "workspace_id": message.workspace_id,
            "channel_id": message.channel_id,
            "from_agent_id": message.from_agent_id,
            "from_session_id": message.from_session_id,
            "target": echo,
            "subject": message.subject,
            "body": message.body,
            "artifacts": list(message.artifacts),
            "parent_message_id": message.parent_message_id,
            "created_at": message.created_at,
        }

    @staticmethod
    def _channel_to_data(channel: Channel) -> dict[str, Any]:
        return {
            "channel_id": channel.channel_id,
            "workspace_id": channel.workspace_id,
            "name": channel.name,
            "created_at": channel.created_at,
        }
