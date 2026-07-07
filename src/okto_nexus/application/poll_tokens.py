"""Ephemeral poll-token service for remote monitor data-plane access."""

from __future__ import annotations

import hmac
from typing import Any, Mapping

from ..config import NexusConfig
from ..domain.base import iso_plus, iso_to_epoch, new_id
from ..domain.handoff import STATUS_OPEN
from ..domain.models import EphemeralPollToken
from ..domain.poll_tokens import (
    generate_poll_token,
    hash_poll_token,
    is_well_formed_poll_token,
)
from ..domain.routing import RoutingAgent, can_agent_see_event, is_agent_eligible
from ..domain.tag_selector import reachable
from ..errors import ErrorCode, OktoNexusError
from .events import DEFAULT_EVENT_LIMIT, EventService
from .identity import SESSION_STATUS_CLOSED, verify_session_credentials
from .inbox import InboxService
from .ports import (
    AgentRepo,
    Clock,
    ConnectionFactory,
    EventRepo,
    HandoffRepo,
    MessageDeliveryRepo,
    MessageRepo,
    PollTokenRepo,
    SessionRepo,
)

POLL_TOKEN_SCOPE: dict[str, Any] = {
    "events": {"read": True, "cursor": True, "long_poll": True},
    "inbox": {"count": True, "peek": True},
    "mutations": False,
}


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


class PollTokenService:
    """Issue EPTs on the MCP control plane and consume them on REST."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        poll_tokens: PollTokenRepo,
        sessions: SessionRepo,
        agents: AgentRepo,
        events: EventRepo,
        deliveries: MessageDeliveryRepo,
        messages: MessageRepo,
        handoffs: HandoffRepo | None,
        clock: Clock,
        config: NexusConfig,
    ) -> None:
        self._cf = connection_factory
        self._poll_tokens = poll_tokens
        self._sessions = sessions
        self._agents = agents
        self._events = events
        self._deliveries = deliveries
        self._messages = messages
        self._handoffs = handoffs
        self._clock = clock
        self._config = config

    # ------------------------------------------------------------------ #
    # Control plane (MCP)
    # ------------------------------------------------------------------ #
    def issue(
        self, *, actor_agent_id: Any, session_id: Any, session_secret: Any
    ) -> dict[str, Any]:
        """Issue one EPT for the authenticated actor's session workspace."""
        actor = self._require_actor(actor_agent_id)
        now = self._clock.now_iso()
        raw = generate_poll_token()
        token_hash = hash_poll_token(raw)
        expires_at = iso_plus(now, int(self._config.poll_token_ttl_seconds))
        with self._cf.unit_of_work() as uow:
            verify_session_credentials(
                self._sessions,
                uow,
                trust_mode="strict",
                tool="poll_token_issue",
                agent_id=actor,
                session_id=session_id,
                session_secret=session_secret,
            )
            session = self._sessions.get(uow, str(session_id))
            if session is None:  # pragma: no cover - verified above
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    "session_id does not exist.",
                    {"session_id": session_id},
                )
            issue_cursor = self._events.max_event_id(
                uow, workspace_id=session.workspace_id, stream=None
            )
            token = self._poll_tokens.issue(
                uow,
                token_id=new_id("ept"),
                token_hash=token_hash,
                agent_id=actor,
                workspace_id=session.workspace_id,
                session_id=session.session_id,
                issue_cursor=issue_cursor,
                scope=POLL_TOKEN_SCOPE,
                expires_at=expires_at,
                created_at=now,
            )
            self._sessions.heartbeat(uow, session_id=session.session_id, at=now)
            self._agents.touch(uow, agent_id=actor, at=now)
        return self._control_payload(raw, token)

    def renew(
        self, *, actor_agent_id: Any, session_id: Any, session_secret: Any
    ) -> dict[str, Any]:
        """Rotate the active EPT for a session and extend its expiry."""
        actor = self._require_actor(actor_agent_id)
        now = self._clock.now_iso()
        raw = generate_poll_token()
        token_hash = hash_poll_token(raw)
        expires_at = iso_plus(now, int(self._config.poll_token_ttl_seconds))
        with self._cf.unit_of_work() as uow:
            verify_session_credentials(
                self._sessions,
                uow,
                trust_mode="strict",
                tool="poll_token_renew",
                agent_id=actor,
                session_id=session_id,
                session_secret=session_secret,
            )
            current = self._poll_tokens.get_active_for_session(
                uow, session_id=str(session_id)
            )
            if current is None or current.agent_id != actor:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    "No active poll token exists for this session; issue one first.",
                    {"session_id": session_id},
                )
            if self._is_expired(current, now):
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    "The active poll token is already expired; issue a new token.",
                    {"token_id": current.token_id, "expires_at": current.expires_at},
                )
            token = self._poll_tokens.rotate(
                uow,
                token_id=current.token_id,
                token_hash=token_hash,
                expires_at=expires_at,
                renewed_at=now,
            )
            self._sessions.heartbeat(uow, session_id=str(session_id), at=now)
            self._agents.touch(uow, agent_id=actor, at=now)
        return self._control_payload(raw, token, include_base=False)

    def revoke(
        self, *, actor_agent_id: Any, session_id: Any, session_secret: Any
    ) -> dict[str, Any]:
        """Revoke the active EPT(s) bound to a session."""
        actor = self._require_actor(actor_agent_id)
        now = self._clock.now_iso()
        with self._cf.unit_of_work() as uow:
            verify_session_credentials(
                self._sessions,
                uow,
                trust_mode="strict",
                tool="poll_token_revoke",
                agent_id=actor,
                session_id=session_id,
                session_secret=session_secret,
            )
            revoked = self._poll_tokens.revoke_for_session(
                uow, session_id=str(session_id), revoked_at=now
            )
            self._sessions.heartbeat(uow, session_id=str(session_id), at=now)
            self._agents.touch(uow, agent_id=actor, at=now)
        return {"revoked": True, "revoked_count": revoked}

    # ------------------------------------------------------------------ #
    # Data plane (REST)
    # ------------------------------------------------------------------ #
    def authenticate(self, raw_token: str | None) -> EphemeralPollToken | None:
        """Resolve an EPT bearer and weakly stamp ``last_used_at``.

        Returns ``None`` for every auth failure so the HTTP adapter can produce
        a uniform 401 without leaking whether the token id/hash/session existed.
        """
        if not raw_token or not is_well_formed_poll_token(raw_token):
            return None
        token_hash = hash_poll_token(raw_token)
        now = self._clock.now_iso()
        try:
            with self._cf.unit_of_work() as uow:
                token = self._poll_tokens.get_by_hash(uow, token_hash=token_hash)
                if token is None:
                    return None
                if not hmac.compare_digest(token.token_hash, token_hash):
                    return None
                if token.revoked_at is not None or self._is_expired(token, now):
                    return None
                session = self._sessions.get(uow, token.session_id)
                if session is None or session.status == SESSION_STATUS_CLOSED:
                    return None
                agent = self._agents.get(uow, token.agent_id)
                if agent is None or not getattr(agent, "is_active", True):
                    return None
                self._poll_tokens.touch_used(uow, token_id=token.token_id, at=now)
                return token
        except OktoNexusError:
            return None

    def event_cursor(self, token: EphemeralPollToken, *, stream: Any) -> dict[str, Any]:
        stream_value = str(stream or "workspace")
        service = self._event_service()
        cursor = service.latest_cursor_for_workspace(
            workspace_id=token.workspace_id,
            agent_id=token.agent_id,
            stream=stream_value,
        )
        return {
            "cursor": max(int(cursor), int(token.issue_cursor)),
            "issue_cursor": int(token.issue_cursor),
            "workspace_id": token.workspace_id,
        }

    def events(
        self,
        token: EphemeralPollToken,
        *,
        stream: Any,
        cursor: Any,
        limit: Any,
        filters: Mapping[str, Any] | None,
        timeout_seconds: Any,
        raw_token: str | None,
    ) -> dict[str, Any]:
        cursor_value = self._cursor_at_or_after_issue(token, cursor)
        service = self._event_service()
        timeout = 0 if timeout_seconds is None else timeout_seconds
        result = service.event_wait_for_workspace(
            workspace_id=token.workspace_id,
            agent_id=token.agent_id,
            stream=str(stream or "workspace"),
            cursor=cursor_value,
            limit=limit,
            filters=filters,
            timeout_seconds=timeout,
        )
        # A long-poll may have parked while the operator revoked the token or
        # while it expired. Re-check before returning any event envelope.
        if raw_token is not None and self.authenticate(raw_token) is None:
            raise OktoNexusError(
                "AUTH_FAILED",
                "Authentication failed: poll token is expired or revoked.",
                {},
            )
        result["issue_cursor"] = int(token.issue_cursor)
        result["workspace_id"] = token.workspace_id
        return result

    def inbox_count(self, token: EphemeralPollToken) -> dict[str, Any]:
        data = self._inbox_service().count(agent_id=token.agent_id)
        data["handoffs_pending"] = self._handoffs_pending(token)
        return data

    def inbox_peek(self, token: EphemeralPollToken, *, limit: Any = None) -> dict[str, Any]:
        data = self._inbox_service().peek(
            agent_id=token.agent_id,
            limit=limit,
            include_parked=False,
            include_bodies=False,
        )
        for item in data.get("messages", []):
            item.pop("body", None)
            item.pop("body_preview", None)
        return data

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _event_service(self) -> EventService:
        return EventService(
            connection_factory=self._cf,
            events=self._events,
            agents=self._agents,
            clock=self._clock,
            config=self._config,
            default_limit=DEFAULT_EVENT_LIMIT,
            max_limit=self._config.max_event_limit,
            touch_on_read=False,
        )

    def _inbox_service(self) -> InboxService:
        return InboxService(
            connection_factory=self._cf,
            deliveries=self._deliveries,
            messages=self._messages,
            agents=self._agents,
            clock=self._clock,
            lease_ttl_seconds=self._config.inbox_lease_ttl_seconds,
            config=self._config,
        )

    def _handoffs_pending(self, token: EphemeralPollToken) -> int:
        if self._handoffs is None:
            return 0
        now = self._clock.now_iso()
        with self._cf.unit_of_work(write=False) as uow:
            agent_row = self._agents.get(uow, token.agent_id)
            agent = RoutingAgent(
                agent_id=token.agent_id,
                workspace_id=token.workspace_id,
                role=getattr(agent_row, "role", None),
                capabilities=getattr(agent_row, "capabilities", None),
                tags=getattr(agent_row, "tags", None),
            )
            rows = self._handoffs.list(
                uow, workspace_id=token.workspace_id, status=STATUS_OPEN
            )
            aggregates = self._handoffs.dependency_aggregates(
                uow,
                workspace_id=token.workspace_id,
                handoff_ids=[h.handoff_id for h in rows],
            )
            pending = 0
            for handoff in rows:
                try:
                    visible = can_agent_see_event(agent, handoff, now)
                    eligible = is_agent_eligible(
                        agent, handoff.target, handoff.created_at, now
                    )
                except OktoNexusError:
                    continue
                if not (visible and eligible):
                    continue
                dep = aggregates.get(handoff.handoff_id)
                if dep and dep["satisfied"] != dep["total"]:
                    continue
                if not self._claimant_in_creator_audience(uow, handoff, token.agent_id):
                    continue
                pending += 1
            return pending

    def _claimant_in_creator_audience(
        self, uow: Any, handoff: Any, agent_id: str
    ) -> bool:
        creator_id = getattr(handoff, "from_agent_id", None)
        creator = (
            self._agents.get(uow, str(creator_id))
            if _is_nonempty_str(creator_id)
            else None
        )
        if creator is None:
            creator = {
                "agent_id": str(creator_id) if _is_nonempty_str(creator_id) else None
            }
        claimant = self._agents.get(uow, str(agent_id)) or {"agent_id": str(agent_id)}
        return reachable(creator, claimant)

    def _cursor_at_or_after_issue(self, token: EphemeralPollToken, cursor: Any) -> int:
        from ..domain.base import normalize_cursor

        value = normalize_cursor(cursor)
        if value < int(token.issue_cursor):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "cursor is older than this poll token's issue cursor. Call "
                "/api/v1/events/cursor and resume forward from that value.",
                {"cursor": value, "issue_cursor": int(token.issue_cursor)},
            )
        return value

    def _control_payload(
        self,
        raw_token: str,
        token: EphemeralPollToken,
        *,
        include_base: bool = True,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "token": raw_token,
            "token_id": token.token_id,
            "expires_at": token.expires_at,
            "scope": token.scope,
            "limits": {
                "ttl_seconds": int(self._config.poll_token_ttl_seconds),
                "max_wait_timeout_seconds": int(
                    self._config.max_wait_timeout_seconds
                ),
                "max_event_limit": int(self._config.max_event_limit),
                "default_profile": "summary",
            },
        }
        if include_base:
            data["base_url"] = "/api/v1"
        return data

    @staticmethod
    def _is_expired(token: EphemeralPollToken, now_iso: str) -> bool:
        try:
            return iso_to_epoch(token.expires_at) <= iso_to_epoch(now_iso)
        except (TypeError, ValueError):
            return True

    @staticmethod
    def _require_actor(actor_agent_id: Any) -> str:
        if not _is_nonempty_str(actor_agent_id):
            raise OktoNexusError(
                ErrorCode.PERMISSION_DENIED,
                "poll_token_* tools require an authenticated agent identity. "
                "Connect over streamable HTTP with an agent API key, or set "
                "OKTO_NEXUS_API_KEY for stdio.",
                {},
            )
        return str(actor_agent_id)
