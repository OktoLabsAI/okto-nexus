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

from collections.abc import Mapping
from typing import Any

from ..config import (
    DEFAULT_MAX_INLINE_BYTES,
    DEFAULT_PRESENCE_TTL_SECONDS,
    TRUST_MODE_OPEN,
)
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
from ..domain.tag_selector import reachable, selector_matches
from ..domain.targets import (
    iter_target_capabilities,
    iter_target_selectors,
    target_strategy,
)
from ..domain.targets import (
    validate_target as validate_routing_target,
)
from ..domain.trace import resolve_trace, validate_trace_id
from ..domain.base import iso_plus
from ..errors import ErrorCode, OktoNexusError
from .approvals import ApprovalService
from .capabilities import CapabilityCatalogService
from .governance import GovernanceService, message_action_for
from .identity import (
    advance_session_presence,
    session_is_present,
    verify_session_credentials,
)
from .permissions import permission_set_for
from .ports import (
    AgentRepo,
    CapabilityCatalogRepo,
    ChannelRepo,
    Clock,
    ConnectionFactory,
    EmbeddingProvider,
    EventEmitter,
    MessageDeliveryRepo,
    MessageRepo,
    MessageVectorStore,
    SessionRepo,
    TagCatalogRepo,
    UnitOfWork,
    WorkspaceRepo,
)
from .tags import TagCatalogService


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
        config: Any = None,
        max_inline_bytes: int = DEFAULT_MAX_INLINE_BYTES,
        presence_ttl_seconds: int = DEFAULT_PRESENCE_TTL_SECONDS,
        trust_mode: str = TRUST_MODE_OPEN,
        embedding_provider: EmbeddingProvider | None = None,
        message_vectors: MessageVectorStore | None = None,
        tag_catalog: TagCatalogRepo | None = None,
        capability_catalog: CapabilityCatalogRepo | None = None,
        governance: GovernanceService | None = None,
        approvals: ApprovalService | None = None,
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
        # Live-tunable knobs (D6): when the NexusConfig OBJECT is injected (the
        # InboxService/HandoffService pattern) they are read from it per call,
        # so a settings PATCH takes effect immediately; the static parameters
        # remain as fallbacks for direct construction.
        self._config = config
        self._static_max_inline_bytes = int(max_inline_bytes)
        self._static_presence_ttl = int(presence_ttl_seconds)
        self._static_trust_mode = str(trust_mode)
        # Semantic-search generation (Frente 3): both None unless embedding is
        # enabled. When wired, create_message embeds NEW messages best-effort.
        self._embedding_provider = embedding_provider
        self._message_vectors = message_vectors
        # Central tag catalog (F1): when wired, every 'tag' target selector is
        # existence-checked fail-closed before anything routes.
        self._tag_catalog = tag_catalog
        # Central capability catalog (migration 014): when wired, every
        # 'capability' target name is existence-checked fail-closed too.
        self._capability_catalog = capability_catalog
        # Policy enforcement (spec 80624c1a): when wired, sends are enforced
        # pre-persistence inside the write UoW against the sender's attached
        # policies; None = no gate (and no bindings = no gate either).
        self._governance = governance
        # HITL approvals (spec 2948b2a2, feature_hitl): when wired, a
        # require_approval verdict intercepts the send into the approvals
        # queue instead of executing; None = verdicts are dropped (allow).
        self._approvals = approvals

    def _send_uow(self, *, workspace_id: str, agent_id: Any):
        """The write UoW for a send: governance-guarded when wired.

        The guard emits ``governance.denied`` in its own UoW AFTER a denial
        rolled the main one back (BR6); with no governance wired it is exactly
        ``unit_of_work()``.
        """
        if self._governance is not None:
            return self._governance.guard(workspace_id=workspace_id, agent_id=agent_id)
        return self._cf.unit_of_work()

    @property
    def _max_inline_bytes(self) -> int:
        if self._config is not None:
            return int(self._config.max_inline_bytes)
        return self._static_max_inline_bytes

    @property
    def _presence_ttl(self) -> int:
        if self._config is not None:
            return int(self._config.presence_ttl_seconds)
        return self._static_presence_ttl

    @property
    def _trust_mode(self) -> str:
        if self._config is not None:
            return str(self._config.trust_mode)
        return self._static_trust_mode

    def _feature_trace_on(self) -> bool:
        # The trace gate is read LIVE at the start of the use case (D6): a
        # settings PATCH mutates the shared NexusConfig in place.
        return bool(getattr(self._config, "feature_trace", False))

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
        trace_id: Any = None,
        session_secret: Any = None,
        _approved_execution: bool = False,
    ) -> dict[str, Any]:
        """Persist a message and emit ``message.created`` atomically.

        ``_approved_execution`` is the INTERNAL one-shot bypass of the HITL
        interception (spec 2948b2a2 BR2): only the approval decision path sets
        it, never a tool or REST parameter. It also skips the session
        credential gate - the submitter's authenticity was verified when the
        action was intercepted, sessions are ephemeral and secrets are never
        persisted; every OTHER gate (permissions, governance deny/quota,
        validation) stays active on re-execution.

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
        # Trace gating (D4/D6): flag OFF accepts-and-ignores the parameter (no
        # validation, no persistence, no echo); flag ON validates the explicit
        # id in this pure phase so a bad trace persists nothing.
        feature_trace_on = self._feature_trace_on()
        if feature_trace_on and trace_id is not None:
            validate_trace_id(trace_id)

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

        with self._send_uow(workspace_id=workspace_id, agent_id=from_agent_id) as uow:
            # Trust gate FIRST (M10): a failed credential check rolls the whole
            # uow back, so a forged sender never persists anything. Skipped on
            # approved re-execution (spec 2948b2a2): authenticity was verified
            # at interception time and the ephemeral session may be long gone.
            if not _approved_execution:
                verify_session_credentials(
                    self._sessions,
                    uow,
                    trust_mode=self._trust_mode,
                    tool="message_create",
                    agent_id=from_agent_id,
                    session_id=from_session_id,
                    session_secret=session_secret,
                )
                # A verified send proves the sender's session is alive now:
                # advance its heartbeat so presence tracks activity (no extra
                # heartbeat call). Best-effort, inside this uow - rolls back
                # if the send does.
                advance_session_presence(
                    self._sessions, uow, session_id=from_session_id, at=now
                )

            # Permission gate (migration 011): which SEND capability this is.
            # A channel post is gated by send_channel alone (its broadcast-ish
            # fan-out is the channel's nature, not a broadcast privilege); a
            # directed target additionally needs send_direct; a channel-less
            # group/broadcast send needs send_broadcast.
            perms = permission_set_for(self._agents, uow, from_agent_id)
            directed = requires_known_recipient(target)
            if channel is not None:
                perms.require("messages", "send_channel")
                if directed:
                    perms.require("messages", "send_direct")
            elif directed:
                perms.require("messages", "send_direct")
            else:
                perms.require("messages", "send_broadcast")
            rate = perms.limit("messages_per_minute")
            if rate > 0:
                sent = self._messages.count_since(
                    uow,
                    from_agent_id=str(from_agent_id),
                    since=iso_plus(now, -60.0),
                )
                if sent >= rate:
                    raise OktoNexusError(
                        ErrorCode.PERMISSION_DENIED,
                        f"Rate limit exceeded: this agent may send at most "
                        f"{rate} message(s) per minute "
                        f"(limits.messages_per_minute).",
                        {
                            "required_permission": "limits.messages_per_minute",
                            "limit": rate,
                            "sent_last_60s": sent,
                        },
                    )

            workspace_created = self._ensure_workspace(
                uow, workspace_id, root_realpath, now
            )
            self._require_channel(uow, workspace_id, channel)
            parent_row = self._require_parent(uow, workspace_id, channel, parent)
            # D3 precedence matrix: explicit > inherited from the parent row >
            # generated (flag ON); always None with the flag OFF (D4).
            resolved_trace = resolve_trace(
                explicit=trace_id,
                inherited=parent_row.trace_id if parent_row is not None else None,
                feature_on=feature_trace_on,
            )

            # Catalog EXISTENCE gate (F1, fail-closed): every 'tag' selector in
            # the target (incl. nested mixed rules) must reference registered
            # tags, or the whole send rolls back before anything routes.
            self._ensure_target_selectors_registered(uow, target)
            self._ensure_target_capabilities_registered(uow, target)

            # Resolve recipients UP FRONT (read-only): a directed target to an
            # unknown agent raises NOT_FOUND here, rolling the whole uow back so no
            # message / delivery / event persists (ADR 0001).
            recipients, warning, excluded_stale, filtered_by_audience = (
                self._resolve_recipients(uow, workspace_id, from_agent_id, target, now)
            )

            # Quantitative permission gates over the RESOLVED fan-out.
            max_recipients = perms.limit("max_recipients")
            if max_recipients > 0 and len(recipients) > max_recipients:
                raise OktoNexusError(
                    ErrorCode.PERMISSION_DENIED,
                    f"The send would reach {len(recipients)} recipients but "
                    f"this agent is limited to {max_recipients} "
                    f"(limits.max_recipients).",
                    {
                        "required_permission": "limits.max_recipients",
                        "limit": max_recipients,
                        "resolved_recipients": len(recipients),
                    },
                )
            # Governance gate (spec 80624c1a): deny rules + quotas from the
            # sender's attached policies, composed and evaluated PRE-persistence
            # in this same UoW, after the permission gate and recipient
            # resolution. No bindings = no governance inside enforce() (BR2). A
            # denial raises, rolls everything back, and the guard emits
            # governance.denied afterwards.
            if self._governance is not None:
                verdict = self._governance.enforce(
                    uow,
                    agent_id=from_agent_id,
                    action=message_action_for(target_echo, channel),
                    size_bytes=len(body.encode("utf-8"))
                    if isinstance(body, str)
                    else 0,
                )
                if (
                    verdict is not None
                    and self._approvals is not None
                    and not _approved_execution
                ):
                    # HITL interception (spec 2948b2a2 FR2): the send WOULD
                    # have passed but a require_approval policy matched. The
                    # approvals row + approval.requested commit in THIS UoW
                    # (BR1) and the pending envelope early-returns - no
                    # message row, no deliveries, no message.created. Session
                    # credentials are deliberately NOT persisted.
                    return self._approvals.intercept(
                        uow,
                        workspace_id=workspace_id,
                        agent_id=from_agent_id,
                        action=message_action_for(target_echo, channel),
                        policy_id=verdict.policy.policy_id,
                        kwargs={
                            "project_root": root_realpath,
                            "from_agent_id": from_agent_id,
                            "subject": subject,
                            "body": body,
                            "channel_id": channel,
                            "target": target_echo,
                            "artifacts": artifact_refs,
                            "parent_message_id": parent,
                            "trace_id": resolved_trace,
                        },
                        trace_id=resolved_trace,
                    )
            message = self._messages.create(
                uow,
                message_id=message_id,
                workspace_id=workspace_id,
                from_agent_id=from_agent_id,
                channel_id=channel,
                from_session_id=from_session_id
                if _is_nonempty_str(from_session_id)
                else None,
                target=target_text,
                subject=subject,
                body=body,
                artifacts=artifact_refs,
                parent_message_id=parent,
                trace_id=resolved_trace,
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
            if message.trace_id is not None:
                # Payload-borne trace (D1): the event log carries the trace so
                # trajectories reconstruct without joining the messages table.
                event_payload["trace_id"] = message.trace_id
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
            if filtered_by_audience:
                # Outbound audience scoping (F1): these agents matched the
                # target but sit outside the sender's comm_scope - the drop is
                # counted, never silent.
                data["filtered_by_audience"] = filtered_by_audience
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

        # Best-effort semantic index of the NEW message, in its OWN unit of work
        # AFTER the send committed (TR3 / br_0bdedc28): a failure here never
        # aborts the send or the fan-out, and there is no backfill of history.
        self._maybe_generate_embedding(
            message_id=message_id, subject=subject, body=body, created_at=now
        )
        return data

    # ------------------------------------------------------------------ #
    # Semantic-search generation (Frente 3)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _embed_text(subject: Any, body: Any) -> str:
        """The text fed to the embedder: subject + body when both are present."""
        parts = [
            part for part in (subject, body) if isinstance(part, str) and part.strip()
        ]
        return "\n".join(parts)

    def _maybe_generate_embedding(
        self, *, message_id: str, subject: Any, body: Any, created_at: str
    ) -> None:
        """Generate + persist the message embedding, BEST-EFFORT (never raises).

        No-op when embedding is disabled (no provider / no vector store wired)
        or the body is empty/whitespace (FR4: only messages WITH a body are
        embedded). Encoding happens BEFORE the write transaction opens so the
        WAL writer lock is held only for the upsert. EVERY failure - provider
        error, DB lock, anything - is swallowed: the message is already sent.
        """
        provider = self._embedding_provider
        vectors = self._message_vectors
        if provider is None or vectors is None:
            return
        if not _is_nonempty_str(body):
            return
        try:
            vector = provider.encode(self._embed_text(subject, body))
            with self._cf.unit_of_work() as uow:
                vectors.upsert(
                    uow,
                    message_id=message_id,
                    vector=vector,
                    model=provider.model,
                    dim=provider.dim,
                    created_at=created_at,
                )
        except Exception:  # noqa: BLE001 - best-effort: a failed embed never aborts the send
            return

    # ------------------------------------------------------------------ #
    # channel_create / channel_list
    # ------------------------------------------------------------------ #
    def create_channel(
        self, *, project_root: Any, name: Any, agent_id: Any = None
    ) -> dict[str, Any]:
        """Create a channel by name in the workspace - IDEMPOTENT by name.

        ``agent_id`` is the OPTIONAL caller identity for the permission gate
        (``channels.create``): the HTTP transport passes the authenticated
        agent; the cooperative stdio transport has no enforced identity, so
        an absent id resolves to the unrestricted set (default-allow).

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
                permission_set_for(self._agents, uow, agent_id).require(
                    "channels", "create"
                )
                self._ensure_workspace(uow, workspace_id, root_realpath, now)
                existing = self._channels.get_by_name(
                    uow, workspace_id=workspace_id, name=channel_name
                )
                if existing is not None:
                    return {
                        "channel": self._channel_to_data(existing),
                        "created": False,
                    }
                channel = self._channels.create(
                    uow,
                    channel_id=new_channel_id(),
                    workspace_id=workspace_id,
                    name=channel_name,
                    created_at=now,
                )
                return {"channel": self._channel_to_data(channel), "created": True}
        except OktoNexusError as exc:
            # A permission denial is NEVER the race below: re-raise before the
            # idempotent re-read, or an existing channel name would mask it.
            if exc.code == ErrorCode.PERMISSION_DENIED:
                raise
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
            if (
                self._channels.get_by_name(uow, workspace_id=workspace_id, name=name)
                is None
            ):
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
        if (
            self._channels.get(uow, workspace_id=workspace_id, channel_id=channel_id)
            is None
        ):
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
    ) -> Message | None:
        """Validate the reply parent and return its materialised row.

        The returned row is how a reply INHERITS its parent's ``trace_id``
        (D3); ``None`` when the message is not a reply.
        """
        if parent_message_id is None:
            return None
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
        return parent

    def _resolve_recipients(
        self,
        uow: UnitOfWork,
        workspace_id: str,
        from_agent_id: Any,
        target: Any,
        now: str,
    ) -> tuple[list[str], str | None, list[str], int]:
        """Resolve the recipient set for a message target (ADR 0001 + M6).

        ``broadcast``/no-target fans out to the workspace's PRESENT agents (the
        single presence predicate: active session AND heartbeat within
        ``presence_ttl_seconds``); every other target resolves against the
        GLOBAL registry (S1). A group fan-out excludes the sender (you never
        inbox your own broadcast). A *directed* target (``direct``/
        ``direct_with_fallback``) matching nobody is an unknown recipient ->
        ``NOT_FOUND``; a group target matching nobody returns a ``warning``
        (never a silent zero-recipient send - D1b).

        Outbound audience scoping (F1): when the SENDER carries a
        ``comm_scope.outbound`` selector, the resolved set is additionally
        filtered to the agents whose tags match it. A blocked *directed* send
        raises ``PERMISSION_DENIED`` with an OPAQUE message (the selector and
        the target's tags never leak to the sender); a group fan-out silently
        loses nobody - blocked agents are dropped AND counted in
        ``filtered_by_audience`` plus an explicit warning.

        Inbound scoping (F2): each candidate whose own ``comm_scope.inbound``
        does not match the sender's tags is unreachable. A blocked *directed*
        send raises the byte-identical opaque ``PERMISSION_DENIED`` (the
        sender never learns which side refused); fan-out drops are SILENT -
        recipient policy is neither a warning nor a ``filtered_by_audience``
        increment, and a send whose whole audience is inbound-blocked
        delivers to nobody without error.

        Returns ``(recipients, warning, excluded_stale, filtered_by_audience)``:
        ``excluded_stale`` names the agents whose ONLY active sessions are
        heartbeat-stale and who were therefore excluded from a broadcast - the
        exclusion is always explicit (an alive-but-busy agent is never dropped
        silently); ``filtered_by_audience`` counts the agents removed by the
        sender's outbound scope.
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
            # An unknown direct target stays NOT_FOUND regardless of the
            # sender's scope (there is nothing to hide about a ghost).
            if directed:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    "The direct target does not match any registered agent.",
                    {"target": parse_target(serialize_target(target))},
                )
            if target_strategy(target) == "tag":
                # A tag selector matching no LIVE agent is a hard error - a
                # zero-match tag send must never degrade into a silent
                # nobody-send (and never falls back to broadcast).
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    "The tag selector does not match any present agent; the "
                    "message was not sent (there is no broadcast fallback).",
                    {
                        "reason": "NO_MATCHING_AGENTS",
                        "target": parse_target(serialize_target(target)),
                    },
                )
            warnings.append(
                "no agents matched the target; the message was delivered to nobody."
            )
        filtered_by_audience = 0
        if recipients:
            sender = self._agents.get(uow, str(from_agent_id))
            registry = {a.agent_id: a for a in self._agents.list(uow)}
            outbound = self._outbound_selector(uow, from_agent_id)
            if outbound is not None:
                allowed = [
                    r
                    for r in recipients
                    if selector_matches(
                        outbound, getattr(registry.get(r), "tags", None)
                    )
                ]
                filtered_by_audience = len(recipients) - len(allowed)
                if filtered_by_audience and directed:
                    # OPAQUE by design (AC6): the denial never reveals the
                    # sender's selector or the target's tags - only that the
                    # sender's own scope excludes this recipient.
                    raise OktoNexusError(
                        ErrorCode.PERMISSION_DENIED,
                        "Direct sends from this agent are restricted by its "
                        "communication scope; the target is outside it.",
                        {"required_permission": "comm_scope.outbound"},
                    )
                recipients = allowed
                if filtered_by_audience:
                    tail = (
                        " The message was delivered to nobody."
                        if not recipients
                        else ""
                    )
                    warnings.append(
                        f"{filtered_by_audience} agent(s) matched the target "
                        "but are outside this agent's outbound communication "
                        "scope (comm_scope.outbound) and were not delivered "
                        "to." + tail
                    )
            # Inbound leg (F2): each remaining candidate's own
            # comm_scope.inbound must match the SENDER's tags (reachable's
            # outbound leg is already satisfied above). Recipient policy is
            # never a sender error nor a sender metric: fan-out drops are
            # SILENT (no warning, filtered_by_audience untouched) and a
            # blocked directed send raises the SAME opaque error as the
            # outbound leg, so the sender cannot tell which side refused.
            if recipients:
                sender_view = (
                    sender if sender is not None else {"agent_id": str(from_agent_id)}
                )
                kept = [
                    r
                    for r in recipients
                    if reachable(sender_view, registry.get(r) or {"agent_id": r})
                ]
                if len(kept) != len(recipients) and directed:
                    raise OktoNexusError(
                        ErrorCode.PERMISSION_DENIED,
                        "Direct sends from this agent are restricted by its "
                        "communication scope; the target is outside it.",
                        {"required_permission": "comm_scope.outbound"},
                    )
                recipients = kept
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
        return recipients, warning, excluded_stale, filtered_by_audience

    def _ensure_target_selectors_registered(self, uow: UnitOfWork, target: Any) -> None:
        """Run the catalog EXISTENCE gate over every 'tag' selector in ``target``.

        FORM was already validated (``validate_target``); this checks each
        referenced ``(key, value)`` pair against the central catalog and raises
        ``VALIDATION_ERROR`` fail-closed on anything unregistered. A no-op when
        no catalog repo is wired (partial wirings never route 'tag' targets
        through a registry-backed transport).
        """
        if self._tag_catalog is None:
            return
        resolved = validate_routing_target(target)
        if resolved is None:
            return
        service = TagCatalogService(catalog=self._tag_catalog)
        for selector in iter_target_selectors(resolved):
            service.ensure_registered(uow, selector, field="target.selector")

    def _ensure_target_capabilities_registered(
        self, uow: UnitOfWork, target: Any
    ) -> None:
        """Run the catalog EXISTENCE gate over every capability name in
        ``target`` (migration 014).

        FORM was already validated (``validate_target``); this checks every
        referenced name - the ``capability`` strategy's string/list and any
        sub-rule nested inside ``mixed``/``direct_with_fallback`` - against
        the central catalog and raises ``VALIDATION_ERROR`` fail-closed on
        anything unregistered. A no-op when no catalog repo is wired.
        """
        if self._capability_catalog is None:
            return
        resolved = validate_routing_target(target)
        if resolved is None:
            return
        names = list(iter_target_capabilities(resolved))
        if names:
            CapabilityCatalogService(
                catalog=self._capability_catalog
            ).ensure_registered(uow, names, field="target.capability")

    def _outbound_selector(self, uow: UnitOfWork, from_agent_id: Any) -> Any:
        """The sender's ``comm_scope.outbound`` selector, or ``None``.

        ``None`` means no restriction: an unset scope, an unregistered sender
        (the cooperative stdio transport has no enforced identity), or a scope
        without an outbound direction. The envelope was already validated
        fail-closed at write time; this read path only extracts.
        """
        sender = self._agents.get(uow, str(from_agent_id))
        scope = getattr(sender, "comm_scope", None) if sender is not None else None
        if not isinstance(scope, Mapping):
            return None
        return scope.get("outbound")

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
        # Enrich the present agents with their registry profile (role /
        # capabilities / tags) so attribute-based targets - notably 'tag'
        # selectors - can evaluate against the LIVE audience. A present agent
        # missing from the registry keeps None everywhere (a tag selector then
        # never matches it - fail-closed).
        registry = {a.agent_id: a for a in self._agents.list(uow)}
        candidates = [
            RoutingAgent(
                agent_id=a,
                workspace_id=workspace_id,
                role=getattr(registry.get(a), "role", None),
                capabilities=getattr(registry.get(a), "capabilities", None),
                tags=getattr(registry.get(a), "tags", None),
            )
            for a in present_ids
        ]
        return candidates, sorted(active_ids - present_ids)

    def _global_candidates(
        self, uow: UnitOfWork, workspace_id: str
    ) -> list[RoutingAgent]:
        """Every registered agent (global), carrying role + capabilities + tags."""
        return [
            RoutingAgent(
                agent_id=agent.agent_id,
                workspace_id=workspace_id,
                role=agent.role,
                capabilities=agent.capabilities,
                tags=getattr(agent, "tags", None),
            )
            for agent in self._agents.list(uow)
        ]

    @staticmethod
    def _message_to_data(
        message: Message, *, target_echo: Any = "__derive__"
    ) -> dict[str, Any]:
        echo = (
            parse_target(message.target) if target_echo == "__derive__" else target_echo
        )
        data = {
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
        if message.trace_id is not None:
            # Echoed only when resolved: flag-OFF sends stay byte-identical to
            # the pre-feature response shape (D4).
            data["trace_id"] = message.trace_id
        return data

    @staticmethod
    def _channel_to_data(channel: Channel) -> dict[str, Any]:
        return {
            "channel_id": channel.channel_id,
            "workspace_id": channel.workspace_id,
            "name": channel.name,
            "created_at": channel.created_at,
        }
