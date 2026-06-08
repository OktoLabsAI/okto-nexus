"""Identity slice application service.

Implements the workspace / agent / session use cases of Okto Nexus V1:

* ``workspace_resolve`` - deterministic ``workspace_id`` from ``project_root``
  (the SERVER hashes; the CLIENT only supplies the path) plus an idempotent
  upsert of the ``workspaces`` row.
* ``workspace_list`` - GLOBAL-ADMIN: enumerate ALL workspaces (the only read
  that crosses workspace boundaries; every other read stays scoped).
* ``agent_register`` - upsert of a global, logical agent identity.
* ``session_open`` - create a workspace-scoped session (server-assigned id).
* ``session_heartbeat`` - advance ``last_heartbeat_at`` and report the derived
  status (``active``/``stale``).
* ``session_close`` - idempotently close a session (``status='closed'`` +
  ``closed_at``); repeating is a no-op that keeps the row closed.

This module is part of the application layer: it depends only on the ports in
:mod:`okto_nexus.application.ports`, the pure :mod:`okto_nexus.domain` helpers,
the error catalogue, and :class:`NexusConfig`. It NEVER imports ``sqlite3`` nor
``mcp`` (enforced by the import-boundary test). All transaction control flows
through the injected :class:`ConnectionFactory` port; every coordinated mutation
and its audit event commit atomically inside a single unit of work.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from ..config import NexusConfig
from ..domain.base import new_id, utf8_byte_len
from ..domain.ids import resolve_realpath, resolve_workspace_id
from ..errors import ErrorCode, OktoNexusError
from .ports import (
    AgentRepo,
    Clock,
    ConnectionFactory,
    EventEmitter,
    SessionRepo,
    UnitOfWork,
    WorkspaceRepo,
)

#: Default stale TTL (seconds) when ``OKTO_NEXUS_SESSION_STALE_TTL_SECONDS`` is
#: unset. ``NexusConfig`` does not carry this knob, so the inbound adapter
#: resolves it from the environment and injects it here.
DEFAULT_SESSION_STALE_TTL_SECONDS = 60

#: Event stream used for session-lifecycle audit events.
SESSION_STREAM = "session"

SESSION_STATUS_ACTIVE = "active"
SESSION_STATUS_STALE = "stale"
SESSION_STATUS_CLOSED = "closed"


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _iso_to_epoch(iso: str) -> float:
    """Parse a UTC ISO-8601 timestamp (``...Z`` or ``+00:00``) to POSIX epoch."""
    text = iso.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


class IdentityService:
    """Use-case orchestration for workspace / agent / session identity."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        workspaces: WorkspaceRepo,
        agents: AgentRepo,
        sessions: SessionRepo,
        clock: Clock,
        config: NexusConfig,
        event_emitter: Optional[EventEmitter] = None,
        stale_ttl_seconds: int = DEFAULT_SESSION_STALE_TTL_SECONDS,
    ) -> None:
        self._cf = connection_factory
        self._workspaces = workspaces
        self._agents = agents
        self._sessions = sessions
        self._clock = clock
        self._config = config
        self._emitter = event_emitter
        self._stale_ttl = int(stale_ttl_seconds)

    # ------------------------------------------------------------------ #
    # Workspace
    # ------------------------------------------------------------------ #
    def workspace_resolve(
        self, *, project_root: Any, display_name: str | None = None
    ) -> dict[str, Any]:
        """Resolve ``project_root`` to a ``workspace_id`` and upsert the row.

        ``workspace_id = sha256(realpath(project_root))`` (lowercase hex). The
        client passes ``project_root``; the server computes the hash. Returns
        the stored workspace fields.

        Raises ``VALIDATION_ERROR`` when ``project_root`` is missing or not an
        absolute path, and ``WORKSPACE_UNRESOLVED`` when realpath cannot be
        resolved (no fallback to a default/shared workspace).
        """
        if not _is_nonempty_str(project_root):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "project_root is required and must be an absolute path string.",
                {"project_root": project_root},
            )
        if not os.path.isabs(project_root):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "project_root must be an absolute path.",
                {"project_root": project_root},
            )

        # WORKSPACE_UNRESOLVED is raised here for broken symlinks / missing
        # paths; no workspaces row is created.
        root_realpath = resolve_realpath(project_root)
        workspace_id = resolve_workspace_id(project_root)

        now = self._clock.now_iso()
        with self._cf.unit_of_work() as uow:
            ws = self._workspaces.upsert(
                uow,
                workspace_id=workspace_id,
                display_name=display_name,
                root_realpath=root_realpath,
                last_seen_at=now,
            )
        return {
            "workspace_id": ws.workspace_id,
            "display_name": ws.display_name,
            "root_realpath": ws.root_realpath,
            "created_at": ws.created_at,
            "last_seen_at": ws.last_seen_at,
        }

    def workspace_list(self) -> list[dict[str, Any]]:
        """Enumerate ALL workspaces (the single global-admin surface).

        This is the ONLY identity read that deliberately crosses workspace
        boundaries: it returns rows from every workspace, unscoped. Every other
        read (e.g. :meth:`list_sessions`) is scoped to a single ``workspace_id``
        and never leaks rows from another workspace.
        """
        with self._cf.unit_of_work() as uow:
            rows = self._workspaces.list_all(uow)
        return [
            {
                "workspace_id": ws.workspace_id,
                "display_name": ws.display_name,
                "root_realpath": ws.root_realpath,
                "created_at": ws.created_at,
                "last_seen_at": ws.last_seen_at,
            }
            for ws in rows
        ]

    # ------------------------------------------------------------------ #
    # Agent
    # ------------------------------------------------------------------ #
    def agent_register(
        self,
        *,
        agent_id: Any,
        role: str | None = None,
        capabilities: Any = None,
        metadata: Any = None,
    ) -> dict[str, Any]:
        """Upsert a logical agent identity keyed by ``agent_id``.

        Independent of any session or workspace; re-registration updates the
        mutable fields (role/capabilities/metadata) without changing
        ``agent_id``. Raises ``VALIDATION_ERROR`` for a missing id and
        ``CONTENT_TOO_LARGE`` when inline capabilities/metadata exceed the limit.
        """
        if not _is_nonempty_str(agent_id):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "agent_id is required.",
                {"agent_id": agent_id},
            )
        self._check_inline_size("capabilities", capabilities)
        self._check_inline_size("metadata", metadata)

        with self._cf.unit_of_work() as uow:
            agent = self._agents.upsert(
                uow,
                agent_id=agent_id,
                role=role,
                capabilities=capabilities,
                metadata=metadata,
            )
        return {
            "agent_id": agent.agent_id,
            "role": agent.role,
            "capabilities": agent.capabilities,
            "metadata": agent.metadata,
            "created_at": agent.created_at,
            "updated_at": self._clock.now_iso(),
        }

    # ------------------------------------------------------------------ #
    # Session
    # ------------------------------------------------------------------ #
    def session_open(
        self, *, agent_id: Any, workspace_id: Any, metadata: Any = None
    ) -> dict[str, Any]:
        """Open a session bound immutably to ``(agent_id, workspace_id)``.

        ``session_id`` is assigned by the server. Raises ``WORKSPACE_REQUIRED``
        when ``workspace_id`` is absent, ``VALIDATION_ERROR`` for a missing
        ``agent_id``, and ``NOT_FOUND`` when the referenced workspace or agent
        does not exist. No ``sessions`` row is created on any failure.
        """
        if not _is_nonempty_str(workspace_id):
            raise OktoNexusError(
                ErrorCode.WORKSPACE_REQUIRED,
                "workspace_id is required for session_open.",
                {},
            )
        if not _is_nonempty_str(agent_id):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "agent_id is required.",
                {"agent_id": agent_id},
            )
        self._check_inline_size("metadata", metadata)

        now = self._clock.now_iso()
        session_id = new_id("ses")
        with self._cf.unit_of_work() as uow:
            if self._workspaces.get(uow, workspace_id) is None:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    "workspace_id does not exist.",
                    {"workspace_id": workspace_id},
                )
            if self._agents.get(uow, agent_id) is None:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    "agent_id does not exist.",
                    {"agent_id": agent_id},
                )
            session = self._sessions.create(
                uow,
                session_id=session_id,
                agent_id=agent_id,
                workspace_id=workspace_id,
                status=SESSION_STATUS_ACTIVE,
                started_at=now,
            )
            payload: dict[str, Any] = {
                "session_id": session.session_id,
                "agent_id": session.agent_id,
            }
            if metadata is not None:
                payload["metadata"] = metadata
            self._emit(
                uow,
                workspace_id=session.workspace_id,
                event_type="session.opened",
                actor_agent_id=session.agent_id,
                session_id=session.session_id,
                payload=payload,
            )
        return {
            "session_id": session.session_id,
            "agent_id": session.agent_id,
            "workspace_id": session.workspace_id,
            "status": SESSION_STATUS_ACTIVE,
            "started_at": session.started_at,
            "last_heartbeat_at": session.last_heartbeat_at,
        }

    def session_heartbeat(
        self, *, session_id: Any, workspace_id: Any = None
    ) -> dict[str, Any]:
        """Advance ``last_heartbeat_at`` and return the derived status.

        Raises ``VALIDATION_ERROR`` for a missing ``session_id``, ``NOT_FOUND``
        for an unknown session, and ``WORKSPACE_MISMATCH`` when the optional
        ``workspace_id`` does not match the session's workspace (no mutation).
        """
        if not _is_nonempty_str(session_id):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "session_id is required.",
                {"session_id": session_id},
            )
        now = self._clock.now_iso()
        with self._cf.unit_of_work() as uow:
            session = self._sessions.get(uow, session_id)
            if session is None:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    "session_id does not exist.",
                    {"session_id": session_id},
                )
            self._guard_workspace(session.workspace_id, workspace_id, session_id)
            updated = self._sessions.heartbeat(uow, session_id=session_id, at=now)
            status = self.derive_status(updated, now)
            self._emit(
                uow,
                workspace_id=updated.workspace_id,
                event_type="session.heartbeat",
                actor_agent_id=updated.agent_id,
                session_id=updated.session_id,
                payload={"session_id": updated.session_id, "status": status},
            )
        return {
            "session_id": updated.session_id,
            "status": status,
            "last_heartbeat_at": updated.last_heartbeat_at,
        }

    def session_close(
        self, *, session_id: Any, workspace_id: Any = None
    ) -> dict[str, Any]:
        """Idempotently close a session and report its terminal state.

        The first call marks ``status='closed'`` and stamps ``closed_at``; a
        second call on the same ``session_id`` returns successfully without
        error and the row stays closed (original ``closed_at`` preserved). Only
        the transition to ``closed`` emits an audit event.

        Raises ``VALIDATION_ERROR`` for a missing ``session_id``, ``NOT_FOUND``
        for an unknown session, and ``WORKSPACE_MISMATCH`` when the optional
        ``workspace_id`` does not match the session's workspace (no mutation).
        """
        if not _is_nonempty_str(session_id):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "session_id is required.",
                {"session_id": session_id},
            )
        now = self._clock.now_iso()
        with self._cf.unit_of_work() as uow:
            session = self._sessions.get(uow, session_id)
            if session is None:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    "session_id does not exist.",
                    {"session_id": session_id},
                )
            self._guard_workspace(session.workspace_id, workspace_id, session_id)
            was_closed = session.status == SESSION_STATUS_CLOSED
            closed = self._sessions.close(uow, session_id=session_id, at=now)
            if not was_closed:
                self._emit(
                    uow,
                    workspace_id=closed.workspace_id,
                    event_type="session.closed",
                    actor_agent_id=closed.agent_id,
                    session_id=closed.session_id,
                    payload={
                        "session_id": closed.session_id,
                        "status": SESSION_STATUS_CLOSED,
                    },
                )
        return {
            "session_id": closed.session_id,
            "agent_id": closed.agent_id,
            "workspace_id": closed.workspace_id,
            "status": SESSION_STATUS_CLOSED,
            "started_at": closed.started_at,
            "last_heartbeat_at": closed.last_heartbeat_at,
            "closed_at": closed.closed_at,
        }

    # ------------------------------------------------------------------ #
    # Reads (workspace-scoped; used for stale derivation & isolation)
    # ------------------------------------------------------------------ #
    def get_session(
        self, *, session_id: Any, workspace_id: Any = None
    ) -> dict[str, Any]:
        """Read a session with its status DERIVED at read time (stale/active).

        Optional ``workspace_id`` enforces ``WORKSPACE_MISMATCH``; the row is
        never mutated.
        """
        if not _is_nonempty_str(session_id):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "session_id is required.",
                {"session_id": session_id},
            )
        now = self._clock.now_iso()
        with self._cf.unit_of_work() as uow:
            session = self._sessions.get(uow, session_id)
            if session is None:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    "session_id does not exist.",
                    {"session_id": session_id},
                )
            self._guard_workspace(session.workspace_id, workspace_id, session_id)
            status = self.derive_status(session, now)
        return {
            "session_id": session.session_id,
            "agent_id": session.agent_id,
            "workspace_id": session.workspace_id,
            "status": status,
            "started_at": session.started_at,
            "last_heartbeat_at": session.last_heartbeat_at,
        }

    def list_sessions(
        self, *, workspace_id: Any, status: str | None = None
    ) -> list[dict[str, Any]]:
        """List sessions in a workspace with derived status (workspace-scoped).

        A standard (non global-admin) read: ``WORKSPACE_REQUIRED`` when the
        workspace is absent; NEVER returns rows from another workspace.
        """
        if not _is_nonempty_str(workspace_id):
            raise OktoNexusError(
                ErrorCode.WORKSPACE_REQUIRED,
                "workspace_id is required.",
                {},
            )
        now = self._clock.now_iso()
        with self._cf.unit_of_work() as uow:
            rows = self._sessions.list(uow, workspace_id=workspace_id, status=status)
        out: list[dict[str, Any]] = []
        for session in rows:
            out.append(
                {
                    "session_id": session.session_id,
                    "agent_id": session.agent_id,
                    "workspace_id": session.workspace_id,
                    "status": self.derive_status(session, now),
                    "started_at": session.started_at,
                    "last_heartbeat_at": session.last_heartbeat_at,
                }
            )
        return out

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def derive_status(self, session: Any, now_iso: str | None = None) -> str:
        """Derive a session's effective status from its heartbeat vs the TTL.

        Closed sessions stay ``closed``. An ``active`` session whose last
        heartbeat is older than the stale TTL is reported as ``stale`` while the
        row remains persisted (no background reaper in V1).
        """
        if session.status == SESSION_STATUS_CLOSED:
            return SESSION_STATUS_CLOSED
        if session.status != SESSION_STATUS_ACTIVE:
            return session.status
        reference = session.last_heartbeat_at or session.started_at
        if reference is None:
            return session.status
        now_iso = now_iso or self._clock.now_iso()
        try:
            delta = _iso_to_epoch(now_iso) - _iso_to_epoch(reference)
        except (ValueError, TypeError):
            return session.status
        if delta > self._stale_ttl:
            return SESSION_STATUS_STALE
        return SESSION_STATUS_ACTIVE

    def _guard_workspace(
        self, owner_workspace_id: str, provided: Any, entity_id: str
    ) -> None:
        if provided is not None and _is_nonempty_str(provided):
            if owner_workspace_id != provided:
                raise OktoNexusError(
                    ErrorCode.WORKSPACE_MISMATCH,
                    "Entity belongs to a different workspace.",
                    {"entity_id": entity_id, "workspace_id": provided},
                )

    def _check_inline_size(self, field: str, value: Any) -> None:
        if value is None:
            return
        try:
            serialized = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{field} is not JSON-serialisable.",
                {"field": field},
            ) from exc
        limit = self._config.max_inline_bytes
        if utf8_byte_len(serialized) > limit:
            raise OktoNexusError(
                ErrorCode.CONTENT_TOO_LARGE,
                f"{field} inline content exceeds {limit} UTF-8 bytes.",
                {"field": field, "max_inline_bytes": limit},
            )

    def _emit(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        event_type: str,
        actor_agent_id: str | None,
        session_id: str | None,
        payload: Mapping[str, Any] | None,
    ) -> None:
        """Emit a session-lifecycle audit event inside ``uow`` (best-effort).

        Skipped when no :class:`EventEmitter` is wired (the Event Log slice owns
        ``event_id`` assignment, imported here, not redefined). The actor
        ``agent_id`` and ``session_id`` are always preserved (INV11).
        """
        if self._emitter is None:
            return
        self._emitter.emit(
            uow,
            workspace_id=workspace_id,
            stream=SESSION_STREAM,
            type=event_type,
            payload=dict(payload) if payload else None,
            actor_agent_id=actor_agent_id,
            visibility="workspace",
            target=session_id,
        )
