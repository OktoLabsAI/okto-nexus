"""Channels & Messages slice application service.

Implements the use cases this slice OWNS:

* ``message_create`` - persist a message row, **resolve its recipients and fan
  out one inbox delivery per recipient**, and emit exactly one ``message.created``
  event - all INSIDE the same SQLite unit of work (atomic coupling). Reading a
  message is the INBOX slice's job (``inbox_*``), not this slice's (ADR 0001);
* ``create_channel`` - create a channel by name (idempotent), so agents add the
  channels they need beyond the seeded ``general`` default;
* ``channel_list``   - return the workspace channels (seeding ``general`` first).

Application layer: depends only on the ports in
:mod:`okto_nexus.application.ports`, the pure :mod:`okto_nexus.domain` helpers,
and the error catalogue. It NEVER imports ``sqlite3`` nor ``mcp`` (enforced by
the import-boundary test). All transaction control flows through the injected
``ConnectionFactory`` port; ``event_id`` assignment is delegated to the IMPORTED
:class:`EventEmitter` (owned by the Event Log slice), never redefined here.
"""

from __future__ import annotations

from typing import Any

from ..config import DEFAULT_PRESENCE_TTL_SECONDS, TRUST_MODE_OPEN
from ..domain.ids import resolve_realpath, resolve_workspace_id
from ..domain.messages import (
    MESSAGE_CREATED_TYPE,
    MESSAGE_STREAM,
    SEED_CHANNEL_NAMES,
    enforce_inline_size,
    new_channel_id,
    new_message_id,
    normalize_artifacts,
    parse_target,
    require_message_fields,
    serialize_target,
    validate_channel_name,
    validate_target,
)
from ..domain.inbox import (
    DELIVERY_UNREAD,
    assert_deliverable_message_target,
    new_delivery_id,
    requires_known_recipient,
    requires_workspace_audience,
    resolve_recipients,
)
from ..domain.models import Channel, Message
from ..domain.routing import RoutingAgent
from ..errors import ErrorCode, OktoNexusError
from .identity import session_is_present, verify_session_credentials
from .ports import (
    AgentRepo,
    ChannelRepo,
    Clock,
    ConnectionFactory,
    EventEmitter,
    MessageDeliveryRepo,
    MessageRepo,
    SessionRepo,
    UnitOfWork,
    WorkspaceRepo,
)


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
        agents: AgentRepo,
        sessions: SessionRepo,
        deliveries: MessageDeliveryRepo,
        event_emitter: EventEmitter,
        clock: Clock,
        max_inline_bytes: int,
        presence_ttl_seconds: int = DEFAULT_PRESENCE_TTL_SECONDS,
        trust_mode: str = TRUST_MODE_OPEN,
    ) -> None:
        self._cf = connection_factory
        self._channels = channels
        self._messages = messages
        self._workspaces = workspaces
        self._agents = agents
        self._sessions = sessions
        self._deliveries = deliveries
        self._emitter = event_emitter
        self._clock = clock
        self._max_inline_bytes = int(max_inline_bytes)
        self._presence_ttl = int(presence_ttl_seconds)
        self._trust_mode = str(trust_mode)

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
        session_secret: Any = None,
    ) -> dict[str, Any]:
        """Persist a message and emit ``message.created`` atomically.

        On ANY rejection (workspace, validation, content size, unknown channel,
        unknown/cross-workspace parent, failed trust check, or a failed event
        append) neither the message row nor the event persists - the whole
        unit of work rolls back.

        Trust (M10): in ``trust_mode='strict'`` a valid ``from_session_id`` +
        ``session_secret`` pair belonging to ``from_agent_id`` is required; in
        ``open`` mode a SUPPLIED ``session_secret`` is still validated (a wrong
        credential is never ignored).

        Presence (M6): a broadcast/no-target message fans out to the
        workspace's PRESENT agents only (active session with a heartbeat within
        ``presence_ttl_seconds``). Agents excluded because every active session
        of theirs is stale are surfaced EXPLICITLY in ``excluded_stale`` plus a
        ``warning`` - the sender is never silently deceived about who was left
        out.

        When ``project_root`` resolves to a workspace that did NOT exist yet,
        the upsert creates it and the response carries ``workspace_created:
        true`` - a mistyped path silently materialising a phantom workspace is
        exactly the failure mode this flag surfaces (check it if you expected
        an existing workspace).
        """
        workspace_id, root_realpath = self._resolve_workspace(project_root)
        now = self._clock.now_iso()

        # Pure, write-free validation first (no row / event on rejection).
        require_message_fields(from_agent_id, subject, body)
        enforce_inline_size(subject, body, self._max_inline_bytes)
        validate_target(target, now)
        # Reject targets that would broadcast against the GLOBAL registry under
        # eager inbox delivery (direct_with_fallback; broadcast nested in mixed).
        assert_deliverable_message_target(target)
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
            # Trust gate FIRST (M10): a failed credential check rolls the whole
            # uow back, so a forged sender never persists anything.
            verify_session_credentials(
                self._sessions,
                uow,
                trust_mode=self._trust_mode,
                tool="message_create",
                agent_id=from_agent_id,
                session_id=from_session_id,
                session_secret=session_secret,
            )
            workspace_created = self._ensure_workspace(
                uow, workspace_id, root_realpath, now
            )
            self._require_channel(uow, workspace_id, channel)
            self._require_parent(uow, workspace_id, channel, parent)

            # Resolve recipients UP FRONT (read-only): a directed target to an
            # unknown agent raises NOT_FOUND here, rolling the whole uow back so no
            # message / delivery / event persists (ADR 0001).
            recipients, warning, excluded_stale = self._resolve_recipients(
                uow, workspace_id, from_agent_id, target, now
            )

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

            self._agents.touch(uow, agent_id=from_agent_id, at=now)

            # Fan out into each recipient's GLOBAL inbox (one delivery per agent).
            for recipient_id in recipients:
                self._deliveries.create(
                    uow,
                    delivery_id=new_delivery_id(),
                    message_id=message.message_id,
                    recipient_agent_id=recipient_id,
                    status=DELIVERY_UNREAD,
                    created_at=now,
                )

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
            data["recipients"] = recipients
            data["delivered_count"] = len(recipients)
            if excluded_stale:
                # Explicit, never silent (M6): these agents hold ONLY stale
                # active sessions and were excluded from the fan-out.
                data["excluded_stale"] = excluded_stale
            if warning is not None:
                data["warning"] = warning
            if workspace_created:
                # The upsert materialised a BRAND-NEW workspace: surface it so a
                # mistyped project_root never creates a phantom silently.
                data["workspace_created"] = True
        return data

    # ------------------------------------------------------------------ #
    # channel_create / channel_list
    # ------------------------------------------------------------------ #
    def create_channel(self, *, project_root: Any, name: Any) -> dict[str, Any]:
        """Create a channel by name in the workspace - IDEMPOTENT by name.

        Channels are lightweight, workspace-global organizational labels with no
        membership/ACL: any agent in the workspace can read and post to any
        channel. Creating an EXISTING name returns the existing channel with
        ``created=False``; a new name creates it and returns ``created=True``.
        The name is validated/trimmed by :func:`validate_channel_name`.

        Idempotency holds under CONCURRENCY too: if a peer wins the
        ``UNIQUE(workspace, name)`` race between our read and our insert, the
        insert error is swallowed and the peer's row is returned (``created``
        ``False``) instead of surfacing a spurious ``DB_ERROR``.
        """
        workspace_id, root_realpath = self._resolve_workspace(project_root)
        channel_name = validate_channel_name(name)
        now = self._clock.now_iso()
        try:
            with self._cf.unit_of_work() as uow:
                self._ensure_workspace(uow, workspace_id, root_realpath, now)
                existing = self._channels.get_by_name(
                    uow, workspace_id=workspace_id, name=channel_name
                )
                if existing is not None:
                    return {"channel": self._channel_to_data(existing), "created": False}
                channel = self._channels.create(
                    uow,
                    channel_id=new_channel_id(),
                    workspace_id=workspace_id,
                    name=channel_name,
                    created_at=now,
                )
                return {"channel": self._channel_to_data(channel), "created": True}
        except OktoNexusError:
            # A concurrent creator may have won the UNIQUE(workspace, name) race
            # between our get_by_name and our insert. Re-read in a fresh unit of
            # work; if the row now exists, the create is idempotent (created
            # False). Otherwise the failure was unrelated - re-raise it.
            with self._cf.unit_of_work() as uow:
                raced = self._channels.get_by_name(
                    uow, workspace_id=workspace_id, name=channel_name
                )
            if raced is not None:
                return {"channel": self._channel_to_data(raced), "created": False}
            raise

    def list_channels(self, *, project_root: Any) -> dict[str, Any]:
        """Return the workspace channels (seeding the ``general`` default first)."""
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
    ) -> bool:
        """Idempotently ensure the ``workspaces`` row exists (FK parent).

        Returns ``True`` when this call CREATED the row (it did not exist
        before the upsert), so callers can surface the implicit creation
        instead of silently materialising a phantom workspace.
        """
        created = self._workspaces.get(uow, workspace_id) is None
        self._workspaces.upsert(
            uow,
            workspace_id=workspace_id,
            root_realpath=root_realpath,
            last_seen_at=now,
        )
        return created

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

    def _resolve_recipients(
        self,
        uow: UnitOfWork,
        workspace_id: str,
        from_agent_id: Any,
        target: Any,
        now: str,
    ) -> tuple[list[str], str | None, list[str]]:
        """Resolve the recipient set for a message target (ADR 0001 + M6).

        ``broadcast``/no-target fans out to the workspace's PRESENT agents (the
        single presence predicate: active session AND heartbeat within
        ``presence_ttl_seconds``); every other target resolves against the
        GLOBAL registry (S1). A group fan-out excludes the sender (you never
        inbox your own broadcast). A *directed* target (``direct``/
        ``direct_with_fallback``) matching nobody is an unknown recipient ->
        ``NOT_FOUND``; a group target matching nobody returns a ``warning``
        (never a silent zero-recipient send - D1b).

        Returns ``(recipients, warning, excluded_stale)``: ``excluded_stale``
        names the agents whose ONLY active sessions are heartbeat-stale and who
        were therefore excluded from a broadcast - the exclusion is always
        explicit (an alive-but-busy agent is never dropped silently).
        """
        excluded_stale: list[str] = []
        if requires_workspace_audience(target):
            candidates, excluded_stale = self._workspace_audience(
                uow, workspace_id, now
            )
            excluded_stale = [a for a in excluded_stale if a != str(from_agent_id)]
        else:
            candidates = self._global_candidates(uow, workspace_id)
        resolved = resolve_recipients(target, candidates, now=now)
        directed = requires_known_recipient(target)
        if not directed:
            resolved = resolved - {str(from_agent_id)}
        recipients = sorted(resolved)
        warnings: list[str] = []
        if not recipients:
            if directed:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    "The direct target does not match any registered agent.",
                    {"target": parse_target(serialize_target(target))},
                )
            warnings.append(
                "no agents matched the target; the message was delivered to nobody."
            )
        if excluded_stale:
            warnings.append(
                f"{len(excluded_stale)} agent(s) were excluded from the "
                "broadcast because every active session of theirs has a "
                f"heartbeat older than presence_ttl_seconds "
                f"({self._presence_ttl}s): {', '.join(excluded_stale)}. They "
                "will NOT receive this message (see excluded_stale); reach "
                "one explicitly with a direct target if it is alive but busy."
            )
        warning = " ".join(warnings) if warnings else None
        return recipients, warning, excluded_stale

    def _workspace_audience(
        self, uow: UnitOfWork, workspace_id: str, now: str
    ) -> tuple[list[RoutingAgent], list[str]]:
        """Split the workspace's active-session holders into present vs stale.

        PRESENT (the broadcast audience) uses the single, shared predicate
        :func:`okto_nexus.application.identity.session_is_present` - one notion
        of presence bus-wide. An agent with ANY fresh active session is
        present; an agent whose active sessions are ALL heartbeat-stale lands
        in the second list (sorted) so the caller can surface the exclusion.
        """
        sessions = self._sessions.list(uow, workspace_id=workspace_id, status="active")
        present_ids: set[str] = set()
        active_ids: set[str] = set()
        for session in sessions:
            active_ids.add(session.agent_id)
            if session_is_present(session, now, self._presence_ttl):
                present_ids.add(session.agent_id)
        candidates = [
            RoutingAgent(agent_id=a, workspace_id=workspace_id) for a in present_ids
        ]
        return candidates, sorted(active_ids - present_ids)

    def _global_candidates(
        self, uow: UnitOfWork, workspace_id: str
    ) -> list[RoutingAgent]:
        """Every registered agent (global), carrying role + capabilities."""
        return [
            RoutingAgent(
                agent_id=agent.agent_id,
                workspace_id=workspace_id,
                role=agent.role,
                capabilities=agent.capabilities,
            )
            for agent in self._agents.list(uow)
        ]

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
