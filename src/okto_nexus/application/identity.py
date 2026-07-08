"""Identity slice application service.

Implements the workspace / agent / session use cases of Okto Nexus V1:

* ``workspace_resolve`` - deterministic ``workspace_id`` from ``project_root``
  (the SERVER hashes; the CLIENT only supplies the path) plus an idempotent
  upsert of the ``workspaces`` row.
* ``workspace_list`` - GLOBAL-ADMIN: enumerate ALL workspaces (on-disk paths
  opt-in via ``include_paths``).
* ``agent_register`` - upsert of a global, logical agent identity.
* ``agent_list`` / ``agent_get`` - GLOBAL reads over agent identities.
* ``session_open`` - create a workspace-scoped session (server-assigned id).

The deliberately cross-workspace (global) reads are ``workspace_list`` and
``agent_list`` / ``agent_get`` / ``capability_list`` (agents are global
identities); every workspace/session read stays scoped to a single
``workspace_id``.
* ``session_heartbeat`` - advance ``last_heartbeat_at`` and report the derived
  status (``active``/``stale``).
* ``session_close`` - idempotently close a session (``status='closed'`` +
  ``closed_at``); repeating is a no-op that keeps the row closed.
* ``list_present`` - the SINGLE presence read (M6): active sessions whose
  heartbeat is within ``presence_ttl_seconds`` (the same predicate the message
  broadcast audience uses). ``session_open``/``session_heartbeat`` also reap
  sessions dead past ``session_reap_seconds`` opportunistically.

This module additionally owns the M10 trust primitives: ``session_open``
returns a per-session ``session_secret`` (uuid4), and
:func:`verify_session_credentials` / :class:`SessionTrustGuard` enforce it on
the sensitive verbs according to ``NexusConfig.trust_mode``.

This module is part of the application layer: it depends only on the ports in
:mod:`okto_nexus.application.ports`, the pure :mod:`okto_nexus.domain` helpers,
the error catalogue, and :class:`NexusConfig`. It NEVER imports ``sqlite3`` nor
``mcp`` (enforced by the import-boundary test). All transaction control flows
through the injected :class:`ConnectionFactory` port; every coordinated mutation
and its audit event commit atomically inside a single unit of work.
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Mapping, Optional

from ..config import (
    DEFAULT_PRESENCE_TTL_SECONDS,
    DEFAULT_SESSION_REAP_SECONDS,
    DEFAULT_SESSION_STALE_TTL_SECONDS,
    TRUST_MODE_OPEN,
    TRUST_MODE_STRICT,
    NexusConfig,
)
from ..domain.approvals import OPERATOR_AGENT_ID, is_reserved_agent_id
from ..domain.base import check_inline_size, iso_to_epoch, new_id
from ..domain.ids import resolve_realpath, resolve_workspace_id
from ..domain.routing import normalize_capabilities
from ..domain.tag_selector import reachable
from ..errors import ErrorCode, OktoNexusError
from .capabilities import CapabilityCatalogService
from .permissions import permission_set_for
from .ports import (
    AgentRepo,
    CapabilityCatalogRepo,
    Clock,
    ConnectionFactory,
    EventEmitter,
    SessionRepo,
    UnitOfWork,
    WorkspaceRepo,
)

# The stale TTL (seconds) is a NexusConfig knob (``session_stale_ttl_seconds``,
# env OKTO_NEXUS_SESSION_STALE_TTL_SECONDS, parsed FAIL-CLOSED at startup); the
# default is imported from config above and re-exported under its historic name
# (``DEFAULT_SESSION_STALE_TTL_SECONDS``) for call-site compatibility.

#: Event stream used for session-lifecycle audit events. Session lifecycle is
#: workspace-level observability, so it rides the canonical ``workspace``
#: stream - ``"session"`` is NOT in ``domain.events.VALID_STREAMS`` and would
#: be rejected fail-closed by the event write path (and invisible to every
#: consumer if it ever persisted).
SESSION_STREAM = "workspace"

SESSION_STATUS_ACTIVE = "active"
SESSION_STATUS_STALE = "stale"
SESSION_STATUS_CLOSED = "closed"


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def session_is_present(session: Any, now_iso: str, presence_ttl_seconds: int) -> bool:
    """The SINGLE presence predicate (M6): stored-active AND fresh heartbeat.

    Reconciles the three previously-unreconciled notions of presence (stored
    status, derived stale status, agent ``last_seen_at``): a session is PRESENT
    iff its persisted status is ``active`` and its last heartbeat (falling back
    to ``started_at``) is within ``presence_ttl_seconds`` of ``now_iso``. Both
    ``IdentityService.list_present`` and the message broadcast audience consume
    this exact function, so "who is present" has one answer bus-wide. A session
    with no parseable heartbeat reference is NOT present (it cannot prove
    liveness) - callers surface the exclusion explicitly, never silently.
    """
    if session.status != SESSION_STATUS_ACTIVE:
        return False
    reference = session.last_heartbeat_at or session.started_at
    if not _is_nonempty_str(reference):
        return False
    try:
        delta = iso_to_epoch(now_iso) - iso_to_epoch(reference)
    except (ValueError, TypeError):
        return False
    return delta <= int(presence_ttl_seconds)


def verify_session_credentials(
    sessions: SessionRepo,
    uow: UnitOfWork,
    *,
    trust_mode: str,
    tool: str,
    agent_id: Any,
    session_id: Any = None,
    session_secret: Any = None,
) -> None:
    """Enforce the M10 trust contract for a sensitive verb (inside ``uow``).

    ``trust_mode='strict'``: ``session_id`` AND ``session_secret`` are required
    and must match an open (non-closed) session of ``agent_id``.
    ``trust_mode='open'``: credentials are optional, but a SUPPLIED
    ``session_secret`` is always verified - a wrong credential is never
    ignored (a bare ``session_id`` keeps its legacy attribution-only meaning).

    Errors are prescriptive: missing credentials name ``session_open`` as the
    fix; a mismatch states exactly which check failed (without echoing the
    stored secret).
    """
    has_sid = _is_nonempty_str(session_id)
    has_secret = _is_nonempty_str(session_secret)
    if trust_mode == TRUST_MODE_STRICT:
        if not has_sid or not has_secret:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{tool} requires session_id AND session_secret in "
                "trust_mode='strict'. Open a session with "
                f"session_open(agent_id='{agent_id}', workspace_id=...) and "
                "pass back the returned session_id and session_secret.",
                {
                    "tool": tool,
                    "trust_mode": TRUST_MODE_STRICT,
                    "session_id_provided": has_sid,
                    "session_secret_provided": has_secret,
                },
            )
    elif not has_secret:
        # open mode without a supplied credential: legacy behaviour.
        return
    if not has_sid:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{tool}: session_secret was provided without session_id. Pass the "
            "session_id returned by session_open alongside its secret.",
            {"tool": tool},
        )
    session = sessions.get(uow, session_id)
    if session is None:
        raise OktoNexusError(
            ErrorCode.NOT_FOUND,
            f"{tool}: session_id does not exist. Open a new session with "
            "session_open and use the returned session_id + session_secret.",
            {"tool": tool, "session_id": session_id},
        )
    if session.agent_id != agent_id:
        raise OktoNexusError(
            ErrorCode.NOT_OWNER,
            f"{tool}: session {session.session_id} belongs to agent "
            f"'{session.agent_id}', not '{agent_id}'. You may only act with a "
            "session opened for your own agent_id.",
            {"tool": tool, "session_id": session_id, "agent_id": agent_id},
        )
    if session.status == SESSION_STATUS_CLOSED:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{tool}: session {session.session_id} is closed and no longer "
            "authorizes actions. Open a new session with session_open.",
            {"tool": tool, "session_id": session_id},
        )
    stored = sessions.get_secret(uow, session_id=session.session_id)
    if stored is None:
        raise OktoNexusError(
            ErrorCode.NOT_OWNER,
            f"{tool}: session {session.session_id} has no stored secret (it "
            "was opened before the trust upgrade). Close it and open a new "
            "session with session_open to obtain a session_secret.",
            {"tool": tool, "session_id": session_id},
        )
    if stored != session_secret:
        raise OktoNexusError(
            ErrorCode.NOT_OWNER,
            f"{tool}: session_secret does not match session "
            f"{session.session_id}. Use the secret returned by the "
            "session_open call that created this session (or open a new one).",
            {"tool": tool, "session_id": session_id},
        )


def advance_session_presence(
    sessions: SessionRepo,
    uow: UnitOfWork,
    *,
    session_id: Any,
    at: str | None = None,
) -> None:
    """Stamp ``last_heartbeat_at`` from an AUTHENTICATED, ACTIVE action.

    Presence (both the dashboard rollup and the broadcast audience) keys on the
    session heartbeat, NOT on the agent's ``last_seen_at``. So an agent that
    actively coordinates - receiving (``inbox_pull``), sending, claiming a
    handoff - but does not spam ``session_heartbeat`` decays to stale even
    though it is plainly alive. Any verb it invokes with VALID session
    credentials is itself proof of liveness, so we advance the heartbeat exactly
    as ``session_heartbeat`` would: real activity keeps presence fresh with no
    standalone heartbeat call (same efficiency, honest status).

    Best-effort: a blank ``session_id`` is a no-op and a missing/closed session
    is swallowed, so a liveness stamp can NEVER fail an action whose own
    credential checks already passed.
    """
    if not _is_nonempty_str(session_id):
        return
    try:
        sessions.heartbeat(uow, session_id=session_id, at=at)
    except OktoNexusError:
        pass


class SessionTrustGuard:
    """Adapter-side helper enforcing M10 on tools whose service is slice-foreign.

    Inbound tool modules (handoff, inbox) build one guard per registration and
    call :meth:`require` before delegating a sensitive verb to the application
    service. The check runs in its own READ-ONLY unit of work via
    :func:`verify_session_credentials`, so the verbs themselves stay untouched.
    """

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        sessions: SessionRepo,
        trust_mode: str = TRUST_MODE_OPEN,
    ) -> None:
        self._cf = connection_factory
        self._sessions = sessions
        self._trust_mode = str(trust_mode)

    def require(
        self,
        *,
        tool: str,
        agent_id: Any,
        session_id: Any = None,
        session_secret: Any = None,
    ) -> None:
        """Raise unless the supplied credentials satisfy the trust mode.

        On success it ALSO advances the session heartbeat: an authenticated,
        active verb is itself proof of liveness, so presence tracks real
        activity without a standalone ``session_heartbeat`` call. The single
        unit of work is therefore a WRITE (the verification read plus the
        presence stamp); a failed credential check rolls it back untouched.
        """
        if self._trust_mode != TRUST_MODE_STRICT and not _is_nonempty_str(
            session_secret
        ):
            return  # open mode, nothing supplied: skip the transaction entirely
        with self._cf.unit_of_work() as uow:
            verify_session_credentials(
                self._sessions,
                uow,
                trust_mode=self._trust_mode,
                tool=tool,
                agent_id=agent_id,
                session_id=session_id,
                session_secret=session_secret,
            )
            # Verified active action -> the session is alive now; keep presence
            # fresh off real activity (best-effort, never fails the action).
            advance_session_presence(self._sessions, uow, session_id=session_id)


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
        capability_catalog: Optional[CapabilityCatalogRepo] = None,
    ) -> None:
        self._cf = connection_factory
        self._workspaces = workspaces
        self._agents = agents
        self._sessions = sessions
        self._clock = clock
        self._config = config
        self._emitter = event_emitter
        self._capability_catalog = capability_catalog
        self._stale_ttl = int(stale_ttl_seconds)
        self._presence_ttl = int(
            getattr(config, "presence_ttl_seconds", DEFAULT_PRESENCE_TTL_SECONDS)
        )
        self._reap_seconds = int(
            getattr(config, "session_reap_seconds", DEFAULT_SESSION_REAP_SECONDS)
        )

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

    def workspace_list(
        self, *, include_paths: bool = False, actor_agent_id: Any = None
    ) -> list[dict[str, Any]]:
        """Enumerate ALL workspaces (a global-admin surface).

        This deliberately crosses workspace boundaries: it returns rows from
        every workspace, unscoped (as do :meth:`agent_list` / :meth:`agent_get`,
        since agents are global identities). Every WORKSPACE/SESSION read (e.g.
        :meth:`list_sessions`) stays scoped to a single ``workspace_id`` and
        never leaks rows from another workspace.

        ``root_realpath`` is OMITTED from each entry unless
        ``include_paths=True``. Disclosure of every project's on-disk location
        is opt-in defense-in-depth against prompt-injection exfiltration (an
        injected agent echoing the filesystem layout of ALL projects); the
        trust model itself is unchanged - the caller is the same OS user that
        supplied the path to ``workspace_resolve`` in the first place.
        """
        with self._cf.unit_of_work() as uow:
            if _is_nonempty_str(actor_agent_id):
                perms = permission_set_for(self._agents, uow, str(actor_agent_id))
                perms.require("workspaces", "list")
                if include_paths:
                    perms.require("workspaces", "include_paths")
            rows = self._workspaces.list_all(uow)
        out: list[dict[str, Any]] = []
        for ws in rows:
            entry: dict[str, Any] = {
                "workspace_id": ws.workspace_id,
                "display_name": ws.display_name,
                "created_at": ws.created_at,
                "last_seen_at": ws.last_seen_at,
            }
            if include_paths:
                entry["root_realpath"] = ws.root_realpath
            out.append(entry)
        return out

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
        actor_agent_id: Any = None,
    ) -> dict[str, Any]:
        """Upsert a logical agent identity keyed by ``agent_id``.

        Independent of any session or workspace; re-registration updates the
        mutable fields (role/capabilities/metadata) without changing
        ``agent_id``. Raises ``VALIDATION_ERROR`` for a missing id and
        ``CONTENT_TOO_LARGE`` when inline capabilities/metadata exceed the limit.

        ``actor_agent_id`` is the AUTHENTICATED caller identity (the API key's
        agent on the HTTP transport). When present, registration is
        SELF-ONLY: an authenticated agent may update its OWN role/capabilities
        but can neither mint new identities nor rewrite another agent's
        profile - identities are created by the operator on the dashboard
        (PERMISSION_DENIED otherwise). Absent (the cooperative stdio mode
        with no key), the open V1 contract is preserved.
        """
        if not _is_nonempty_str(agent_id):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "agent_id is required.",
                {"agent_id": agent_id},
            )
        # Reserved operator identity (spec 2948b2a2 BR4, fail-closed, no
        # flag): the human's first-class identity is seeded at bootstrap and
        # can never be registered/impersonated through a public write path.
        if is_reserved_agent_id(agent_id):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"agent_id '{agent_id}' is reserved for the human operator "
                "and cannot be registered by agents.",
                {"agent_id": agent_id, "reserved": OPERATOR_AGENT_ID},
            )
        if _is_nonempty_str(actor_agent_id) and str(agent_id) != str(actor_agent_id):
            raise OktoNexusError(
                ErrorCode.PERMISSION_DENIED,
                "agent_register is self-only on an authenticated connection: "
                f"your API key identifies you as '{actor_agent_id}', so you "
                f"cannot register or modify '{agent_id}'. New identities are "
                "created by the operator on the dashboard (Agents -> New "
                "agent); use agent_whoami to read your own profile.",
                {
                    "required_permission": "identity.self_only",
                    "authenticated_agent_id": str(actor_agent_id),
                    "attempted_agent_id": str(agent_id),
                },
            )
        self._check_inline_size("capabilities", capabilities)
        self._check_inline_size("metadata", metadata)
        # Validate the capabilities SHAPE up front (VALIDATION_ERROR for a
        # non-iterable/non-mapping value) so a poison value is never persisted -
        # keeping capability_list and capability routing/eligibility safe.
        announced = normalize_capabilities(capabilities)

        now = self._clock.now_iso()
        with self._cf.unit_of_work() as uow:
            if _is_nonempty_str(actor_agent_id):
                perms = permission_set_for(self._agents, uow, str(actor_agent_id))
                if role is not None or metadata is not None or capabilities is not None:
                    perms.require("identity", "update_profile")
                if capabilities is not None:
                    perms.require("identity", "update_capabilities")
            # EXISTENCE gate (migration 014, fail-closed): every announced
            # capability must already be in the central catalog. Runs inside
            # the write transaction so nothing persists on rejection. A no-op
            # when no catalog repo is wired (partial test wirings).
            if self._capability_catalog is not None and announced:
                CapabilityCatalogService(
                    catalog=self._capability_catalog
                ).ensure_registered(uow, announced, field="capabilities")
            agent = self._agents.upsert(
                uow,
                agent_id=agent_id,
                role=role,
                capabilities=capabilities,
                metadata=metadata,
            )
            # Registering is itself an interaction; stamp last_seen_at.
            self._agents.touch(uow, agent_id=agent_id, at=now)
        return {
            "agent_id": agent.agent_id,
            "role": agent.role,
            "capabilities": agent.capabilities,
            "metadata": agent.metadata,
            "created_at": agent.created_at,
            "updated_at": now,
            "last_seen_at": now,
        }

    def agent_whoami(self, *, actor_agent_id: Any) -> dict[str, Any]:
        """Return the AUTHENTICATED caller's own profile (key-derived).

        The self-service mirror of the dashboard registration: name
        (agent_id), role, capabilities, metadata, timestamps, plus the
        communication permissions the operator assigned (``permissions`` is
        ``None`` for unrestricted/full access). Raises ``VALIDATION_ERROR``
        when the connection carries no authenticated identity (the
        cooperative stdio mode without a key) and ``NOT_FOUND`` if the
        identity row vanished (deleted while connected).
        """
        if not _is_nonempty_str(actor_agent_id):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "This connection has no authenticated identity: agent_whoami "
                "derives your profile from the API key. Connect through "
                "/mcp?api_key=... (or set OKTO_NEXUS_API_KEY on stdio); in "
                "the open cooperative mode read a profile with "
                "agent_get(agent_id=...).",
                {},
            )
        with self._cf.unit_of_work() as uow:
            agent = self._agents.get(uow, str(actor_agent_id))
        if agent is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "The authenticated identity no longer exists in the registry.",
                {"agent_id": str(actor_agent_id)},
            )
        data = self._agent_to_data(agent)
        data["permissions"] = agent.permissions
        data["preset_id"] = agent.preset_id
        data["is_active"] = agent.is_active
        return data

    def agent_list(self, *, caller_agent_id: Any = None) -> list[dict[str, Any]]:
        """Enumerate the registered agents VISIBLE to the caller.

        Agent identities are global, so this is a deliberately cross-workspace
        read. Each entry carries ``last_seen_at`` - the timestamp of the agent's
        most recent action on the bus (``None`` if it never acted).

        Discovery is scoped by reachability (F2 - "visible = reachable"): an
        AUTHENTICATED caller sees only the agents its comm scope can reach
        (its own outbound AND each peer's inbound), plus always itself. An
        anonymous caller (``caller_agent_id=None`` - the cooperative stdio
        mode or the operator REST surface) sees everything.
        """
        with self._cf.unit_of_work() as uow:
            rows = self._agents.list(uow)
            rows = self._filter_reachable(uow, caller_agent_id, rows)
        return [self._agent_to_data(agent) for agent in rows]

    def agent_get(
        self, *, agent_id: Any, caller_agent_id: Any = None
    ) -> dict[str, Any]:
        """Return one agent's full details, including ``last_seen_at``.

        Raises ``VALIDATION_ERROR`` for a missing ``agent_id`` and ``NOT_FOUND``
        when no such agent is registered. For an AUTHENTICATED caller an agent
        its comm scope cannot reach also reads as ``NOT_FOUND`` - byte-identical
        to the non-existent case, so unreachable and unknown are
        indistinguishable (F2; the policy never leaks).
        """
        if not _is_nonempty_str(agent_id):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "agent_id is required.",
                {"agent_id": agent_id},
            )
        with self._cf.unit_of_work() as uow:
            agent = self._agents.get(uow, agent_id)
            if (
                agent is not None
                and self._filter_reachable(uow, caller_agent_id, [agent]) == []
            ):
                agent = None
        if agent is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "agent_id does not exist.",
                {"agent_id": agent_id},
            )
        return self._agent_to_data(agent)

    def capability_list(self, *, caller_agent_id: Any = None) -> list[dict[str, Any]]:
        """List the capability CATALOG merged with who advertises each name.

        A discovery surface: for each capability, the agents that possess
        it (so a caller can decide whom to address with a capability-targeted
        message or handoff). Capabilities are normalised with the SAME rule
        capability routing uses (:func:`normalize_capabilities`), so what is
        listed is exactly what a ``target: {strategy: "capability"}`` would match.

        With the central catalog wired (migration 014) the result is
        CATALOG-COMPLETE: every registered name appears - with its
        ``description`` and ``agent_count: 0`` when nobody advertises it yet -
        so callers discover the full sanctioned vocabulary, not just what
        happens to be owned. Ownership stays scoped by reachability exactly
        like :meth:`agent_list` (F2); anonymous callers see everything. The
        union is kept defensively (an advertised name missing from the catalog
        still lists, with ``description: None``). Result is sorted by
        capability; ``agents`` is sorted per capability.
        """
        with self._cf.unit_of_work() as uow:
            agents = self._agents.list(uow)
            agents = self._filter_reachable(uow, caller_agent_id, agents)
            catalog = (
                self._capability_catalog.list(uow)
                if self._capability_catalog is not None
                else []
            )
        index: dict[str, list[str]] = {}
        for agent in agents:
            # ``agent_register`` validates the capabilities shape up front, so a
            # persisted value always normalises cleanly (no poison to guard).
            for cap in normalize_capabilities(agent.capabilities):
                index.setdefault(cap, []).append(agent.agent_id)
        descriptions = {row.name: row.description for row in catalog}
        names = sorted(set(index) | set(descriptions))
        return [
            {
                "capability": cap,
                "description": descriptions.get(cap),
                "agent_count": len(index.get(cap, [])),
                "agents": sorted(index.get(cap, [])),
            }
            for cap in names
        ]

    def _filter_reachable(
        self, uow: Any, caller_agent_id: Any, agents: list[Any]
    ) -> list[Any]:
        """Keep the agents the caller's comm scope can REACH (F2 discovery).

        ``caller_agent_id=None``/blank means an unscoped surface (anonymous
        stdio caller or the operator REST/dashboard) - no filtering. The
        shared :func:`~okto_nexus.domain.tag_selector.reachable` predicate
        supplies the self carve-out: the caller always sees itself.
        """
        if not _is_nonempty_str(caller_agent_id):
            return agents
        caller = self._agents.get(uow, str(caller_agent_id))
        caller_view: Any = (
            caller if caller is not None else {"agent_id": str(caller_agent_id)}
        )
        return [a for a in agents if reachable(caller_view, a)]

    @staticmethod
    def _agent_to_data(agent: Any) -> dict[str, Any]:
        # ``tags`` are PUBLIC discovery data (a peer needs them to reason
        # about tag-targeted routing); ``comm_scope`` is operator-private and
        # deliberately NEVER leaves the identity slice on this surface.
        return {
            "agent_id": agent.agent_id,
            "role": agent.role,
            "capabilities": agent.capabilities,
            "metadata": agent.metadata,
            "created_at": agent.created_at,
            "last_seen_at": agent.last_seen_at,
            "tags": getattr(agent, "tags", None) or {},
        }

    # ------------------------------------------------------------------ #
    # Session
    # ------------------------------------------------------------------ #
    def session_open(
        self,
        *,
        agent_id: Any,
        workspace_id: Any,
        metadata: Any = None,
        actor_agent_id: Any = None,
    ) -> dict[str, Any]:
        """Open a session bound immutably to ``(agent_id, workspace_id)``.

        ``session_id`` is assigned by the server, together with a random
        ``session_secret`` (uuid4) returned ONLY here (M10): keep it - in
        ``trust_mode='strict'`` the sensitive verbs require it, and in ``open``
        mode it is validated whenever supplied. Also reaps the workspace's
        long-dead sessions opportunistically (M6). Raises ``WORKSPACE_REQUIRED``
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
        if _is_nonempty_str(actor_agent_id) and str(agent_id) != str(actor_agent_id):
            raise OktoNexusError(
                ErrorCode.PERMISSION_DENIED,
                "session_open is self-only on an authenticated connection: "
                f"your API key identifies you as '{actor_agent_id}', so you "
                f"cannot open a session for '{agent_id}'.",
                {
                    "required_permission": "identity.session_self",
                    "authenticated_agent_id": str(actor_agent_id),
                    "attempted_agent_id": str(agent_id),
                },
            )
        self._check_inline_size("metadata", metadata)

        now = self._clock.now_iso()
        session_id = new_id("ses")
        # uuid4 per ADR: a random, server-generated, per-session shared secret.
        session_secret = str(uuid.uuid4())
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
                session_secret=session_secret,
            )
            self._agents.touch(uow, agent_id=agent_id, at=now)
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
            self._reap_stale_sessions(uow, workspace_id=workspace_id, now=now)
        return {
            "session_id": session.session_id,
            "agent_id": session.agent_id,
            "workspace_id": session.workspace_id,
            "status": SESSION_STATUS_ACTIVE,
            "started_at": session.started_at,
            "last_heartbeat_at": session.last_heartbeat_at,
            "session_secret": session_secret,
        }

    def session_heartbeat(
        self, *, session_id: Any, workspace_id: Any = None
    ) -> dict[str, Any]:
        """Advance ``last_heartbeat_at`` and return the derived status.

        Also reaps the workspace's long-dead sessions opportunistically (M6) -
        the freshly heartbeated session can never be among them.

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
            self._agents.touch(uow, agent_id=updated.agent_id, at=now)
            status = self.derive_status(updated, now)
            self._emit(
                uow,
                workspace_id=updated.workspace_id,
                event_type="session.heartbeat",
                actor_agent_id=updated.agent_id,
                session_id=updated.session_id,
                payload={"session_id": updated.session_id, "status": status},
            )
            self._reap_stale_sessions(uow, workspace_id=updated.workspace_id, now=now)
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
            self._agents.touch(uow, agent_id=closed.agent_id, at=now)
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

    def list_present(self, *, workspace_id: Any) -> list[dict[str, Any]]:
        """The SINGLE presence read (M6): the workspace's PRESENT sessions.

        A session is present iff :func:`session_is_present` holds - persisted
        status ``active`` AND last heartbeat within ``presence_ttl_seconds``
        (config; default 1800s). This is the same predicate the message
        broadcast audience uses, so a session listed here is exactly a session
        that would receive a broadcast. Sorted deterministically by
        ``(agent_id, session_id)``. ``WORKSPACE_REQUIRED`` when the workspace
        is absent.
        """
        if not _is_nonempty_str(workspace_id):
            raise OktoNexusError(
                ErrorCode.WORKSPACE_REQUIRED,
                "workspace_id is required.",
                {},
            )
        now = self._clock.now_iso()
        with self._cf.unit_of_work() as uow:
            rows = self._sessions.list(
                uow, workspace_id=workspace_id, status=SESSION_STATUS_ACTIVE
            )
        present = [s for s in rows if session_is_present(s, now, self._presence_ttl)]
        present.sort(key=lambda s: (s.agent_id, s.session_id))
        return [
            {
                "session_id": s.session_id,
                "agent_id": s.agent_id,
                "workspace_id": s.workspace_id,
                "status": SESSION_STATUS_ACTIVE,
                "started_at": s.started_at,
                "last_heartbeat_at": s.last_heartbeat_at,
            }
            for s in present
        ]

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _reap_stale_sessions(
        self, uow: UnitOfWork, *, workspace_id: str, now: str
    ) -> list[str]:
        """Opportunistic reaper (M6): close sessions dead past the reap window.

        Every ``active`` session in the workspace whose last heartbeat (falling
        back to ``started_at``) is older than ``session_reap_seconds`` is
        closed in place (status ``closed`` + ``closed_at``), emitting one
        ``session.reaped`` audit event with ``reason='stale'`` - so a session
        that died without ``session_close`` stops haunting the workspace
        forever. Runs inside the caller's unit of work; an unparseable
        heartbeat is skipped (never silently closed). Returns the reaped ids.
        """
        try:
            now_epoch = iso_to_epoch(now)
        except (ValueError, TypeError):  # pragma: no cover - defensive
            return []
        reaped: list[str] = []
        for session in self._sessions.list(
            uow, workspace_id=workspace_id, status=SESSION_STATUS_ACTIVE
        ):
            reference = session.last_heartbeat_at or session.started_at
            if not _is_nonempty_str(reference):
                continue
            try:
                ref_epoch = iso_to_epoch(reference)
            except (ValueError, TypeError):
                continue
            if now_epoch - ref_epoch <= self._reap_seconds:
                continue
            closed = self._sessions.close(uow, session_id=session.session_id, at=now)
            self._emit(
                uow,
                workspace_id=closed.workspace_id,
                event_type="session.reaped",
                actor_agent_id=closed.agent_id,
                session_id=closed.session_id,
                payload={
                    "session_id": closed.session_id,
                    "agent_id": closed.agent_id,
                    "status": SESSION_STATUS_CLOSED,
                    "reason": "stale",
                    "last_heartbeat_at": session.last_heartbeat_at,
                },
            )
            reaped.append(closed.session_id)
        return reaped

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
            delta = iso_to_epoch(now_iso) - iso_to_epoch(reference)
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
        """Enforce the inclusive 64KB UTF-8 inline content limit (shared helper)."""
        check_inline_size(field, value, self._config.max_inline_bytes)

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
        ``event_id`` assignment, imported here, not redefined). Events ride the
        canonical ``workspace`` stream with ``visibility='public'`` and NO
        routing ``target`` (lifecycle is workspace-wide observability, not
        directed work; ``target`` is a routing rule, never a bare session id).
        The actor ``agent_id`` and ``session_id`` are always preserved (INV11):
        ``session_id`` travels in the payload.
        """
        if self._emitter is None:
            return
        data: dict[str, Any] = dict(payload) if payload else {}
        if session_id is not None:
            data.setdefault("session_id", session_id)
        self._emitter.emit(
            uow,
            workspace_id=workspace_id,
            stream=SESSION_STREAM,
            type=event_type,
            payload=data or None,
            actor_agent_id=actor_agent_id,
            visibility="public",
            target=None,
        )
