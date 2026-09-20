"""MCP inbound tools for the harness-connector lifecycle slice (ADR 0004).

Registers eight tools on the FastMCP server, each returning the canonical
envelope (success ``{ok:true,data}`` / failure ``{ok:false,error}``) via
:func:`tool_envelope`/:func:`async_tool_envelope`, so no exception ever
crosses the adapter boundary:

* ``harness_list``       - catalog of available harness kinds/substrates and
  their DECLARED capabilities, read straight off each real connector class
  (never hand-copied into a table - see :func:`capabilities_catalog`).
* ``harness_open``       - open a session for a kind (spawn or attach),
  register it as an ordinary agent (D3), and start tracking it.
* ``harness_send``       - send a turn (``send_turn``) to a live session.
* ``harness_steer``      - steer a live session, honouring the connector's
  declared ``steer_timing``.
* ``harness_interrupt``  - interrupt the in-flight turn.
* ``harness_close``      - end a session and stop tracking it.
* ``harness_get``        - one session's state: the LIVE in-memory view if
  still tracked, else the last durable row (D10 durability, never a fabricated
  liveness signal).
* ``harness_event_list`` - durable replay of a session's events (D10).

Naming reconciliation against ``plans/harness-integrations/02-phase35-
supervisor-spec.md``'s proposed names (explicitly flagged there as guesses):
every tool keeps the spec's ``harness_<verb>`` shape (matches this repo's
``<noun>_<verb>`` grammar: ``agent_register``, ``handoff_claim``,
``poll_token_issue``) EXCEPT two renames to match the REAL grammar the spec
told implementers to check:

* ``harness_status`` -> ``harness_get``, matching the single-entity-read
  suffix every other slice uses (``agent_get``, ``handoff_get``,
  ``memory_get``), not a bespoke name.
* ``harness_events`` -> ``harness_event_list``, matching the
  catalog/collection suffix every other slice uses (``agent_list``,
  ``capability_list``, ``tag_list``) - a bare plural noun is the one proposed
  name that broke the ``<noun>_<verb>`` grammar outright.

``harness_list`` itself matches ``capability_list``/``tag_list`` precedent: a
CATALOG read (kinds/substrates this server can open), not an instance
listing - a live-session listing is deliberately NOT built in this phase (see
this module's own docstring note below on scope).

Kind -> connector construction (composition-root job; the frozen
:class:`~okto_nexus.application.ports.HarnessConnector` port and the
:class:`~okto_nexus.application.harness_supervisor.HarnessSupervisor` both
take an ALREADY-CONSTRUCTED connector and explicitly refuse to know how to
build one) lives here, in :func:`build_connector_factories`/
:func:`build_connector` - REST routes (``routes.py``) import and reuse the
SAME functions, so the MCP and HTTP surfaces can never drift on how a
``kind``/``substrate`` maps to a real connector.

``domain.harness.HARNESS_KINDS`` is frozen at THREE members
(``{pi, codex, claude_code}``) but FOUR connectors exist:
``ClaudeCodeStreamConnector`` (D7a, primary, full-duplex) and
``ClaudeCodeAttachConnector`` (D7b, ``cc-socks`` attach, send-only) are BOTH
``kind="claude_code"``. Since the port is frozen and a new kind cannot be
added, substrate selection is a parameter on ``harness_open``
(``substrate: "stream" | "attach"``, default ``"stream"``), never a second
``kind`` value.

Deliberate scope boundaries (read before extending this module):

* Boot-time declared harnesses (D8's "declared AND on-demand" - see
  :class:`~okto_nexus.application.harness_supervisor.HarnessBootSpec`/
  ``open_declared``) are NOT wired into ``serve`` here. That docstring is
  explicit that connector construction is "the composition root's job...
  nothing analogous wires connectors here, deliberately" - this phase is the
  on-demand surface only; a config-driven boot sequence is future work.
* ``harness_open`` does NOT accept an ``agent_capabilities`` parameter.
  :meth:`HarnessSupervisor.open` registers the session's agent identity via
  ``AgentRepo.upsert`` DIRECTLY (the same idempotent primitive
  ``agent_register`` itself uses) - but unlike ``agent_register``/
  ``POST /agents`` (which both run capabilities through the central catalog's
  fail-closed existence gate BEFORE the upsert -
  ``_ensure_capabilities_registered`` in ``routes.py`` /
  ``IdentityService``), the supervisor's direct repo call has no such gate.
  Exposing ``agent_capabilities`` on this surface would silently let a
  harness-registered agent carry unregistered capability names, bypassing a
  guarantee every other identity-writing surface enforces. Reported here
  rather than quietly worked around: fixing it belongs in
  ``HarnessSupervisor.open`` (out of this task's scope - that module was
  built by another agent this session and is not modified here), not in the
  surface layer papering over it. ``role``/``metadata`` (both catalog-free)
  ARE exposed.
* A caller must already hold a ``session_id`` (from ``harness_open``'s
  return, or from ``harness_event_list``) to call ``harness_get``/
  ``harness_send``/etc. - there is no ``harness_list``-style catalog of
  currently-live sessions in this phase (the spec's suggested tool set does
  not include one either). A future phase can add one following the
  ``agent_list`` precedent without touching this module's other tools.

This module is the slice's composition root: :func:`build_service` wires the
concrete SQLite harness repos, the in-memory subscriber registry (D1) and a
shared :class:`~okto_nexus.application.messages.MessageService` (reused,
never re-wired, via ``tools.messages.build_service`` - D10's notable-event
inbox delivery) into ONE process-wide
:class:`~okto_nexus.application.harness_supervisor.HarnessSupervisor`,
cached on ``deps`` exactly like ``tools/_guardrails.py`` caches its
``GuardrailService`` (``getattr(deps, "harness_supervisor", None)`` / lazy
build / stash back on ``deps``) rather than ``Deps``'s OTHER precedent
(``approvals``: a declared dataclass field, built eagerly in ``bootstrap()``).
Either precedent is legitimate; the guardrails shape was chosen here because
nothing else in ``serve``'s fail-closed bootstrap needs the supervisor to
exist before the first tool/route touches it, so an eager build in
``bootstrap()`` would be dead weight on every process that never opens a
harness. It does NOT import the MCP SDK; the live server is passed into
:func:`register`, matching the ``register(server, deps)`` contract.
"""

from __future__ import annotations

import functools
from typing import Annotated, Any, Mapping

import anyio.to_thread
from pydantic import Field

from okto_nexus.adapters.inbound.mcp.tools.messages import (
    build_service as build_message_service,
)
from okto_nexus.adapters.outbound.harness.claude_code_attach import (
    CAPABILITIES as _CLAUDE_CODE_ATTACH_CAPABILITIES,
)
from okto_nexus.adapters.outbound.harness.claude_code_attach import (
    ClaudeCodeAttachConnector,
)
from okto_nexus.adapters.outbound.harness.claude_code_stream import (
    ClaudeCodeStreamConnector,
)
from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
from okto_nexus.adapters.outbound.harness.pi import PiRpcConnector
from okto_nexus.adapters.outbound.harness.subscribers import (
    InMemoryHarnessSubscriberRegistry,
)
from okto_nexus.adapters.outbound.sqlite.harness_repo import (
    SqliteHarnessEventRepo,
    SqliteHarnessSessionRepo,
)
from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteAgentRepo
from okto_nexus.application.harness_supervisor import HarnessSupervisor
from okto_nexus.application.ports import HarnessConnector
from okto_nexus.domain.harness import (
    HARNESS_KINDS,
    HarnessCapabilities,
    HarnessEvent,
    HarnessSession,
    validate_harness_kind,
)
from okto_nexus.envelope import (
    async_tool_envelope,
    require_json_object_param,
    tool_envelope,
)
from okto_nexus.errors import ErrorCode, OktoNexusError

#: Substrate vocabulary for ``kind="claude_code"`` ONLY (see module docstring
#: - the port's ``HARNESS_KINDS`` has no room for a fourth member). Every
#: other kind's ``substrate`` is ``None``.
SUBSTRATE_STREAM = "stream"
SUBSTRATE_ATTACH = "attach"
CLAUDE_CODE_SUBSTRATES: tuple[str, ...] = (SUBSTRATE_STREAM, SUBSTRATE_ATTACH)

#: Reused parameter descriptions (kept DRY across the harness tools).
_P_HARNESS_AGENT_ID = (
    "The agent_id this NEW harness session registers/upserts as (D3) - "
    "existing or fresh; other agents then address it via the normal target "
    "grammar (direct/capability/role/tag). NOT the caller's own agent_id. "
    "REQUIRED."
)
_P_KIND = 'Harness kind, one of: pi, codex, claude_code. REQUIRED.'
_P_ROOT = "Absolute path to the project (defines the workspace scope for this session's persistence + notable-event messages)."
_P_SUBSTRATE = (
    'Only meaningful when kind="claude_code" (rejected otherwise): one of '
    'stream (D7a - Nexus spawns and owns a "claude -p" child; default), '
    "attach (D7b, cc-socks - send-only injection into an ALREADY-RUNNING "
    "interactive session identified by target_pid; steering/interrupt are "
    "unsupported on this substrate - see harness_list)."
)
_P_TARGET_PID = (
    'Only valid with kind="claude_code", substrate="attach" (REQUIRED there, '
    "rejected otherwise): the OS pid of the already-running interactive "
    "Claude Code session to inject into."
)
_P_ROLE = "Logical role to store on the registered agent (optional); matched exactly/case-sensitively by role-strategy targets."
_P_METADATA = "Free-form JSON object of extra attributes stored on the registered agent (optional)."
_P_NOTIFY_TARGET = (
    "Routing target (optional; raw JSON object, same grammar as "
    "message_create/handoff_create) for the D10 notable-event messages "
    "(turn_completed, error) this session's activity generates. Default when "
    'omitted: {"strategy":"broadcast"} (this session\'s own workspace).'
)
_P_SESSION_ID = "The harness session_id returned by harness_open. REQUIRED."
_P_PAYLOAD_TURN = (
    "The turn content, as a raw JSON object (REQUIRED) - shape is "
    "HARNESS-NATIVE and opaque to Nexus (D2), and is NOT uniform across "
    'connectors: pi and codex read {"text": "<prompt>"}; both claude_code '
    'substrates read {"content": "<prompt>"}. Check harness_list\'s kind for '
    "which one this session's connector expects."
)
_P_PAYLOAD_STEER = _P_PAYLOAD_TURN.replace("The turn content", "The steer content")
_P_PAYLOAD_INTERRUPT = (
    "Extra JSON object passed through to the connector (optional; most "
    "connectors ignore it - interrupt is abort, not a reprompt)."
)
_P_AFTER_SEQUENCE = "Only return events with sequence > this value (optional; default 0 = from the start)."
_P_EVENTS_LIMIT = "Max events to return, oldest first (optional; default 200)."


# --------------------------------------------------------------------------- #
# Serialisation helpers (shared with REST routes.py - see module docstring)
# --------------------------------------------------------------------------- #
def capabilities_to_dict(caps: HarnessCapabilities) -> dict[str, Any]:
    return {
        "send_only": caps.send_only,
        "steer_timing": caps.steer_timing,
        "interrupt_requires_settle_wait": caps.interrupt_requires_settle_wait,
        "multiplexes_sessions": caps.multiplexes_sessions,
        "observes_session_end": caps.observes_session_end,
    }


def session_to_dict(session: HarnessSession) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "kind": session.harness_kind,
        "owning_agent_id": session.owning_agent_id,
        "status": session.status,
        "capabilities": capabilities_to_dict(session.capabilities),
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "metadata": dict(session.metadata),
    }


def event_to_dict(event: HarnessEvent) -> dict[str, Any]:
    return {
        "session_id": event.session_id,
        "harness_kind": event.harness_kind,
        "kind": event.kind,
        "native_event": event.native_event,
        "occurred_at": event.occurred_at,
        "payload": dict(event.payload),
        "thread_id": event.thread_id,
        "turn_id": event.turn_id,
    }


def capabilities_catalog() -> list[dict[str, Any]]:
    """List every (kind, substrate) this server can open, with capabilities
    read straight off each REAL connector class (never hand-typed into a
    table - the task's explicit "from each connector's OWN declaration"
    requirement). Safe to call freely: every connector's ``__init__`` only
    sets instance attributes (locks/queues/config) - nothing here spawns a
    process or opens a socket (verified against all four connector modules;
    ``claude_code_attach`` skips construction entirely and reads its
    module-level ``CAPABILITIES`` constant, which its own ``__init__`` also
    just assigns unchanged).
    """
    entries: list[dict[str, Any]] = []
    for kind in sorted(HARNESS_KINDS):
        if kind == "pi":
            entries.append(
                {
                    "kind": kind,
                    "substrate": None,
                    "capabilities": capabilities_to_dict(PiRpcConnector().capabilities),
                }
            )
        elif kind == "codex":
            entries.append(
                {
                    "kind": kind,
                    "substrate": None,
                    "capabilities": capabilities_to_dict(
                        CodexAppServerConnector().capabilities
                    ),
                }
            )
        elif kind == "claude_code":
            entries.append(
                {
                    "kind": kind,
                    "substrate": SUBSTRATE_STREAM,
                    "capabilities": capabilities_to_dict(
                        ClaudeCodeStreamConnector().capabilities
                    ),
                }
            )
            entries.append(
                {
                    "kind": kind,
                    "substrate": SUBSTRATE_ATTACH,
                    "capabilities": capabilities_to_dict(
                        _CLAUDE_CODE_ATTACH_CAPABILITIES
                    ),
                }
            )
        else:  # pragma: no cover - defensive: HARNESS_KINDS is frozen at these 3
            continue
    return entries


def normalize_payload(value: Any, *, required: bool) -> dict[str, Any]:
    """Validate a tool/route payload parameter: a JSON object, or ``None``
    when not ``required`` (-> ``{}``). Deliberately narrower than
    :func:`~okto_nexus.envelope.require_json_object_param` (which also
    accepts a JSON-ENCODED STRING for slices whose application layer parses
    one): :class:`~okto_nexus.domain.harness.HarnessCommand`/the connectors'
    own ``payload.get(...)`` reads expect a real mapping, not a string, so
    accepting one here would only defer the failure to a less legible spot
    inside the connector.
    """
    if value is None:
        if required:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "payload is required and must be a JSON object (shape is "
                "harness-native - see the tool/route description).",
                {},
            )
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    raise OktoNexusError(
        ErrorCode.VALIDATION_ERROR,
        f"payload must be a JSON object (got {type(value).__name__}).",
        {"payload_type": type(value).__name__},
    )


# --------------------------------------------------------------------------- #
# Composition root
# --------------------------------------------------------------------------- #
def build_service(deps: Any) -> HarnessSupervisor:
    """Wire the SQLite harness repos + in-memory subscriber registry (D1)
    into ``deps.repos`` and build the ONE process-wide
    :class:`HarnessSupervisor`.

    Idempotent and cached on ``deps`` (the ``tools/_guardrails.py`` shape -
    see module docstring): the SAME instance is returned whether this
    module's :func:`register` runs once (production) or twice against the
    same ``deps`` (``tests/test_http_parity.py``, which builds BOTH the
    stdio and the HTTP-mounted MCP server from one ``bootstrap()`` result),
    and REST routes (``routes.py``) call this same function to reuse it too.
    """
    existing = getattr(deps, "harness_supervisor", None)
    if existing is not None:
        return existing

    repos = deps.repos
    if getattr(repos, "harness_sessions", None) is None:
        repos.harness_sessions = SqliteHarnessSessionRepo(deps.clock)
    if getattr(repos, "harness_events", None) is None:
        repos.harness_events = SqliteHarnessEventRepo(deps.clock)
    if getattr(repos, "agents", None) is None:
        repos.agents = SqliteAgentRepo(deps.clock)

    # D10: notable events (turn_completed, error) are ALSO delivered through
    # the existing per-recipient inbox. Reuse the messages slice's OWN
    # composition root rather than re-wiring a second MessageService here -
    # both then share the identical governance/approvals/policy composition.
    messages = build_message_service(deps)

    supervisor = HarnessSupervisor(
        connection_factory=deps.connection_factory,
        clock=deps.clock,
        agents=repos.agents,
        sessions=repos.harness_sessions,
        events=repos.harness_events,
        subscribers=InMemoryHarnessSubscriberRegistry(),
        messages=messages,
    )
    deps.harness_supervisor = supervisor
    return supervisor


def _default_connector_factories() -> dict[str, Any]:
    def _pi(*, project_root: str, **_ignored: Any) -> HarnessConnector:
        return PiRpcConnector(cwd=project_root)

    def _codex(*, project_root: str, **_ignored: Any) -> HarnessConnector:
        return CodexAppServerConnector(cwd=project_root)

    def _claude_code(
        *,
        project_root: str,
        substrate: str,
        target_pid: int | None,
        **_ignored: Any,
    ) -> HarnessConnector:
        if substrate == SUBSTRATE_ATTACH:
            # build_connector() already enforced target_pid is not None for
            # this substrate; a defensive re-check would only duplicate that
            # message, so this branch trusts its caller (private helper).
            return ClaudeCodeAttachConnector(target_pid)  # type: ignore[arg-type]
        return ClaudeCodeStreamConnector(cwd=project_root)

    return {"pi": _pi, "codex": _codex, "claude_code": _claude_code}


def build_connector_factories(deps: Any) -> Mapping[str, Any]:
    """Idempotent ``kind -> connector-factory`` table, cached on ``deps``
    (the same shape as :func:`build_service`).

    This IS the composition-root extension point
    :class:`~okto_nexus.application.harness_supervisor.HarnessBootSpec`'s
    docstring says does not exist yet ("nothing analogous wires connectors
    here, deliberately") - a future config-driven boot sequence, or an
    operator wanting non-default connector construction (a specific
    ``pi``/``codex`` provider, a pinned binary path), overrides this
    dictionary on ``deps`` before the first tool/route call. Tests use the
    SAME override point to inject a fake connector instead of spawning a
    real ``pi``/``codex``/``claude`` binary.
    """
    factories = getattr(deps, "harness_connector_factories", None)
    if factories is None:
        factories = _default_connector_factories()
        deps.harness_connector_factories = factories
    return factories


def build_connector(
    factories: Mapping[str, Any],
    *,
    kind: str,
    project_root: str,
    substrate: str | None,
    target_pid: int | None,
) -> HarnessConnector:
    """Validate ``substrate``/``target_pid`` against ``kind`` (fail-closed,
    BEFORE touching the factory table - see module docstring's substrate
    note) and construct the connector. Shared verbatim by ``harness_open``
    and its REST mirror so the two surfaces can never disagree on this
    validation.
    """
    resolved_substrate: str | None
    if kind != "claude_code":
        if substrate is not None:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "substrate only applies to kind='claude_code'.",
                {"kind": kind, "substrate": substrate},
            )
        if target_pid is not None:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "target_pid only applies to kind='claude_code', substrate='attach'.",
                {"kind": kind, "target_pid": target_pid},
            )
        resolved_substrate = None
    else:
        resolved_substrate = substrate or SUBSTRATE_STREAM
        if resolved_substrate not in CLAUDE_CODE_SUBSTRATES:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "substrate must be one of {stream, attach}.",
                {"substrate": substrate, "supported": list(CLAUDE_CODE_SUBSTRATES)},
            )
        if resolved_substrate == SUBSTRATE_STREAM and target_pid is not None:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "target_pid only applies to substrate='attach'.",
                {"substrate": resolved_substrate, "target_pid": target_pid},
            )
        if resolved_substrate == SUBSTRATE_ATTACH and target_pid is None:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "target_pid is required when substrate='attach'.",
                {"substrate": resolved_substrate},
            )

    factory = factories.get(kind)
    if factory is None:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"no connector factory registered for kind='{kind}'.",
            {"kind": kind},
        )
    return factory(
        project_root=project_root,
        substrate=resolved_substrate,
        target_pid=target_pid,
    )


def _durable_session_or_404(deps: Any, session_id: str) -> HarnessSession:
    repos = deps.repos
    with deps.connection_factory.unit_of_work(write=False) as uow:
        durable = repos.harness_sessions.get(uow, session_id=session_id)
    if durable is None:
        raise OktoNexusError(
            ErrorCode.NOT_FOUND,
            "no harness session with this id.",
            {"session_id": session_id},
        )
    return durable


def read_session(deps: Any, supervisor: HarnessSupervisor, session_id: str) -> dict[str, Any]:
    """Shared ``harness_get`` body: LIVE in-memory view if still tracked,
    else the last durable row (never a fabricated liveness signal - a row
    left ``RUNNING`` after an unclean exit is NOT proof of liveness, per
    ``HarnessSessionRepo``'s own docstring)."""
    session = supervisor.get(session_id)
    if session is not None:
        return {**session_to_dict(session), "live": True}
    durable = _durable_session_or_404(deps, session_id)
    return {**session_to_dict(durable), "live": False}


# --------------------------------------------------------------------------- #
# MCP tools
# --------------------------------------------------------------------------- #
def register(server: Any, deps: Any) -> None:
    supervisor = build_service(deps)
    factories = build_connector_factories(deps)

    @server.tool()
    @tool_envelope
    def harness_list() -> dict[str, Any]:
        """List available harness kinds/substrates and their DECLARED capabilities (send_only, steer_timing, etc.), read from each connector's own declaration. Check before harness_steer/harness_interrupt."""
        return {"harnesses": capabilities_catalog()}

    @server.tool()
    @async_tool_envelope
    async def harness_open(
        agent_id: Annotated[str, Field(description=_P_HARNESS_AGENT_ID)],
        kind: Annotated[str, Field(description=_P_KIND)],
        project_root: Annotated[str, Field(description=_P_ROOT)],
        substrate: Annotated[str | None, Field(description=_P_SUBSTRATE)] = None,
        target_pid: Annotated[int | None, Field(description=_P_TARGET_PID)] = None,
        role: Annotated[str | None, Field(description=_P_ROLE)] = None,
        metadata: Annotated[Any, Field(description=_P_METADATA)] = None,
        notify_target: Annotated[Any, Field(description=_P_NOTIFY_TARGET)] = None,
    ) -> dict[str, Any]:
        """Open a harness session (spawn or attach), register it as an agent (D3), and track it. Bounded - a wedged connector raises INTERNAL_ERROR after the start timeout, never hangs (D8)."""
        validate_harness_kind(kind)
        connector = build_connector(
            factories,
            kind=kind,
            project_root=project_root,
            substrate=substrate,
            target_pid=target_pid,
        )
        metadata_obj = require_json_object_param("metadata", metadata)
        notify_target_obj = require_json_object_param("notify_target", notify_target)
        session = await anyio.to_thread.run_sync(
            functools.partial(
                supervisor.open,
                kind=kind,
                connector=connector,
                owning_agent_id=agent_id,
                project_root=project_root,
                role=role,
                metadata=dict(metadata_obj) if isinstance(metadata_obj, Mapping) else None,
                notify_target=dict(notify_target_obj)
                if isinstance(notify_target_obj, Mapping)
                else None,
            )
        )
        return session_to_dict(session)

    @server.tool()
    @async_tool_envelope
    async def harness_send(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
        payload: Annotated[Any, Field(description=_P_PAYLOAD_TURN)],
    ) -> dict[str, Any]:
        """Send a turn to a live session (send_turn). Never blocks for a reply - the answer arrives later as harness events (subscribe out-of-band, or poll harness_event_list)."""
        body = normalize_payload(payload, required=True)
        await anyio.to_thread.run_sync(
            functools.partial(supervisor.send, session_id, "send_turn", body)
        )
        return {"session_id": session_id, "verb": "send_turn"}

    @server.tool()
    @async_tool_envelope
    async def harness_steer(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
        payload: Annotated[Any, Field(description=_P_PAYLOAD_STEER)],
    ) -> dict[str, Any]:
        """Steer a live session's in-flight turn. Rejected if the connector's steer_timing is null (unsupported - check harness_list). NEXT_TURN_BOUNDARY buffers until the next turn; IMMEDIATE can land mid-turn."""
        body = normalize_payload(payload, required=True)
        await anyio.to_thread.run_sync(
            functools.partial(supervisor.send, session_id, "steer", body)
        )
        return {"session_id": session_id, "verb": "steer"}

    @server.tool()
    @async_tool_envelope
    async def harness_interrupt(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
        payload: Annotated[Any, Field(description=_P_PAYLOAD_INTERRUPT)] = None,
    ) -> dict[str, Any]:
        """Interrupt a live session's in-flight turn (abort). If interrupt_requires_settle_wait is true, a send/steer right after may be refused (CONFLICT) until the aborted turn's settle event lands."""
        body = normalize_payload(payload, required=False)
        await anyio.to_thread.run_sync(
            functools.partial(supervisor.send, session_id, "interrupt", body)
        )
        return {"session_id": session_id, "verb": "interrupt"}

    @server.tool()
    @async_tool_envelope
    async def harness_close(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
    ) -> dict[str, Any]:
        """End a live session (best-effort teardown: send(end) then close()) and stop tracking it. Always returns the final session state, even if teardown failed - close() never hangs (D8)."""
        session = await anyio.to_thread.run_sync(
            functools.partial(supervisor.close, session_id)
        )
        return session_to_dict(session)

    @server.tool()
    @tool_envelope
    def harness_get(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
    ) -> dict[str, Any]:
        """Read one harness session: the LIVE in-memory view if still tracked (live:true), else the last durable row (live:false - RUNNING there is NOT proof of liveness). NOT_FOUND if never opened."""
        return read_session(deps, supervisor, session_id)

    @server.tool()
    @tool_envelope
    def harness_event_list(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
        after_sequence: Annotated[int, Field(description=_P_AFTER_SEQUENCE)] = 0,
        limit: Annotated[int, Field(description=_P_EVENTS_LIMIT)] = 200,
    ) -> dict[str, Any]:
        """Durable replay of a session's events (D10), oldest first, independent of liveness. Makes the no-polling push claim checkable after the fact; native_event is the harness's own verbatim name."""
        events = supervisor.replay_events(
            session_id, after_sequence=after_sequence, limit=limit
        )
        return {"events": [event_to_dict(event) for event in events], "count": len(events)}
