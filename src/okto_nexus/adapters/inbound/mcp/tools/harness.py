"""Authenticated runtime tools shared with REST and internal dispatch.

An existing canonical agent owns configured endpoints and approved profiles.
Runtime opens never create or rewrite that identity. The serve owner supervises
native resources; the inbox and durable outbox govern logical delivery and
transport attempts. Event results require separate publication authorization.
All enabled surfaces use the same authorization and application services.
"""

from __future__ import annotations

import functools
import inspect
import json
import os
import sys
from typing import Annotated, Any, Mapping

import anyio.to_thread
from pydantic import Field

from okto_nexus.application.runtime_authorization import require_runtime_agent
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.adapters.inbound.http.identity_ctx import get_authenticated_agent, trusted_local_operator


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
from okto_nexus.application.adapter_registry import AdapterRegistry, AdapterDescriptor
from okto_nexus.application.endpoints import EndpointService
from okto_nexus.application.runtime_access import RuntimeAccessService
from okto_nexus.application.runtime_control import RuntimeControlService, validate_runtime_payload
from okto_nexus.application.runtime_dispatcher import RuntimeDispatcher
from okto_nexus.application.runtime_open import RuntimeOpenService
from okto_nexus.adapters.outbound.sqlite.runtime_requests_repo import SqliteRuntimeRequestRepo
from okto_nexus.application.runtime_delivery import RuntimeDeliveryPlanner
from okto_nexus.adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
from okto_nexus.adapters.outbound.runtime_wake import RuntimeWakeChannel
from okto_nexus.adapters.outbound.runtime_owner_client import call_runtime_owner
from urllib.parse import quote
from okto_nexus.domain.base import new_id
from okto_nexus.adapters.outbound.sqlite.runtime_grants_repo import SqliteRuntimeGrantRepo
from okto_nexus.adapters.outbound.sqlite.endpoints_repo import SqliteEndpointRepo
from okto_nexus.adapters.outbound.harness.environment import profile_environment
from okto_nexus.domain.endpoints import EndpointCapabilities
from okto_nexus.adapters.outbound.harness.envelope import EnvelopeConnector
from okto_nexus.application.ports import HarnessConnector
from okto_nexus.domain.harness import (
    HARNESS_KINDS,
    HarnessCapabilities,
    HarnessEvent,
    HarnessSession,
)
from okto_nexus.envelope import (
    async_tool_envelope,
    tool_envelope,
)
from okto_nexus.errors import ErrorCode, OktoNexusError

def build_access_service(deps):
    return RuntimeAccessService(connection_factory=deps.connection_factory, agents=deps.repos.agents,
        endpoints=SqliteEndpointRepo(), grants=SqliteRuntimeGrantRepo(), config=deps.config, clock=deps.clock,
        registry=build_connector_factories(deps))


def authorize_request(deps, *, substrate=None, action="admin", session_id=None, endpoint_id=None,
                      represented_agent_id=None, workspace_id=None, consume=False):
    """Same authenticated admission policy for MCP, REST and local HTTP."""
    actor = get_authenticated_agent()
    local = trusted_local_operator.get()
    context = RuntimeRequestContext(
        actor.agent_id if actor else None,
        "http_loopback" if local else "agent_key" if actor else "unauthenticated",
        trusted_local_operator=local,
        credential_binding=actor.api_key_hash if actor else None,
    )
    build_access_service(deps).authorize(context, action=action, substrate=substrate,
        session_id=session_id, endpoint_id=endpoint_id, represented_agent_id=represented_agent_id,
        workspace_id=workspace_id, consume=consume)
    return context


def authorized_send(deps, supervisor, session_id, verb, payload):
    context = authorize_request(deps, action="send" if verb == "send_turn" else verb, session_id=session_id)
    if not is_local_runtime_owner(deps):
        action = "send" if verb == "send_turn" else verb
        return call_runtime_owner(deps.config.home_dir, f"/api/v1/harness/sessions/{quote(session_id, safe='')}/{action}", {"payload": payload})
    return RuntimeControlService(access=build_access_service(deps), supervisor=supervisor,
                                 owner_guard=lambda: is_local_runtime_owner(deps)).send(
        context, session_id=session_id, verb=verb, payload=payload)


def authorized_close(deps, supervisor, session_id):
    context = authorize_request(deps, action="close", session_id=session_id)
    if not is_local_runtime_owner(deps):
        return call_runtime_owner(deps.config.home_dir, f"/api/v1/harness/sessions/{quote(session_id, safe='')}/close", {})
    session = RuntimeControlService(access=build_access_service(deps), supervisor=supervisor,
                                    owner_guard=lambda: is_local_runtime_owner(deps)).close(context, session_id=session_id)
    return session_to_dict(session)


def is_local_runtime_owner(deps):
    dispatcher = getattr(deps, "runtime_dispatcher", None)
    if not dispatcher or dispatcher.epoch is None or dispatcher._stop.is_set():
        return False
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return dispatcher.repo.owns(uow, owner_id=dispatcher.owner_id, epoch=dispatcher.epoch, now=deps.clock.now_iso())


def runtime_tool_guard(deps):
    def decorate(fn):
        action = {"harness_open": "access", "harness_send": "send", "harness_steer": "steer",
                  "harness_interrupt": "interrupt", "harness_close": "close", "harness_get": "read",
                  "harness_event_list": "events"}.get(fn.__name__, "admin")
        def check(args, kwargs):
            arguments = inspect.signature(fn).bind(*args, **kwargs).arguments
            authorize_request(deps, action=action, substrate=arguments.get("substrate"),
                              session_id=arguments.get("session_id"))
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def guarded(*args, **kwargs):
                check(args, kwargs)
                return await fn(*args, **kwargs)
        else:
            @functools.wraps(fn)
            def guarded(*args, **kwargs):
                check(args, kwargs)
                return fn(*args, **kwargs)
        return guarded
    return decorate


def runtime_object(name, value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                                f"{name} must contain a JSON object.", {}) from None
    if value is not None and not isinstance(value, Mapping):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                            f"{name} must be a JSON object.", {})
    return dict(value) if value is not None else None


def build_endpoint_service(deps):
    return EndpointService(connection_factory=deps.connection_factory, agents=deps.repos.agents,
        workspaces=deps.repos.workspaces, repo=SqliteEndpointRepo(), registry=build_connector_factories(deps),
        config=deps.config, clock=deps.clock, access=build_access_service(deps))


def prepare_runtime(deps, *, agent_id, kind, project_root, substrate=None, endpoint_id=None,
                    backend=None, target_pid=None, role=None):
    context = authorize_request(deps, substrate=substrate, action="access")
    if backend:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                            "Configure backend options in an approved runtime profile; per-call overrides are disabled.", {})
    service = build_endpoint_service(deps)
    endpoint, profile = service.resolve(context, endpoint_id=endpoint_id, agent_id=agent_id,
        kind=kind, substrate=resolve_substrate(kind, substrate), project_root=project_root)
    require_runtime_agent(agents=deps.repos.agents, connection_factory=deps.connection_factory,
                          agent_id=agent_id, role=role)
    return construct_profile_connector(deps, endpoint=endpoint, profile=profile, kind=kind,
                                       project_root=project_root, substrate=substrate, target_pid=target_pid)


def open_runtime(deps, **arguments):
    context = authorize_request(deps, action="access", substrate=arguments.get("substrate"))
    for name in ("metadata", "notify_target", "backend"):
        arguments[name] = runtime_object(name, arguments.get(name))
    arguments["substrate"] = resolve_substrate(arguments["kind"], arguments.get("substrate"))
    if not is_local_runtime_owner(deps):
        if not arguments.get("idempotency_key"):
            arguments["idempotency_key"] = new_id("open-key")
        return call_runtime_owner(deps.config.home_dir, "/api/v1/harness/sessions", arguments)
    service = build_open_service(deps)
    session, profile, reused, request_id = service.open(context, **arguments)
    result = {**session_to_dict(session), "backend": profile}
    if request_id:
        result.update(request_id=request_id, reused=reused)
    return result


def build_open_service(deps):
    return RuntimeOpenService(connection_factory=deps.connection_factory, endpoints=build_endpoint_service(deps),
        agents=deps.repos.agents, sessions=deps.repos.harness_sessions, requests=SqliteRuntimeRequestRepo(),
        supervisor=build_service(deps), construct=functools.partial(construct_profile_connector, deps), clock=deps.clock,
        owner_guard=lambda: is_local_runtime_owner(deps),
        owner_identity=(deps.runtime_dispatcher.owner_id, deps.runtime_dispatcher.epoch))


def run_runtime_boot(deps):
    from okto_nexus.application.runtime_boot import RuntimeBootService
    service = RuntimeBootService(connection_factory=deps.connection_factory, endpoints=SqliteEndpointRepo(),
        registry=build_connector_factories(deps), open_service=build_open_service(deps),
        owner_id=deps.runtime_dispatcher.owner_id, owner_epoch=deps.runtime_dispatcher.epoch)
    deps.runtime_boot_status = service.run()
    return deps.runtime_boot_status


def construct_profile_connector(deps, *, endpoint, profile, kind, project_root, substrate, target_pid=None):
    """Low-level construction, only after explicit control or durable delivery admission."""
    effective_backend = {}
    if profile is not None:
        config = profile["config"]
        if kind != "codex" and set(config) & {"sandbox", "approval_policy"}:
            raise OktoNexusError(ErrorCode.CONFIG_ERROR,
                "This profile claims controls unsupported by its adapter; review the profile before opening.", {})
        effective_backend["env"] = profile_environment(profile, deps.config.home_dir)
        if kind == "codex":
            effective_backend["thread_start_overrides"] = {
                "sandbox": config.get("sandbox", "read-only"),
                "approvalPolicy": config.get("approval_policy", "on-request"),
            }
            if config.get("command"):
                effective_backend["command"] = config["command"]
        elif kind == "pi":
            effective_backend.update({k: config[k] for k in ("command", "provider", "model", "extra_args") if k in config})
        elif kind == "claude_code" and config.get("command"):
            if len(config["command"]) != 1:
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Claude profile command must name one executable.", {})
            effective_backend["binary"] = config["command"][0]
    configured_pid = endpoint["public_config"].get("target_pid")
    if target_pid is not None and target_pid != configured_pid:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Attach target does not match the approved endpoint.", {})
    connector = build_connector(build_connector_factories(deps), kind=kind, project_root=project_root,
                                substrate=substrate, target_pid=configured_pid, backend=effective_backend)
    return connector, endpoint, {"profile_id": endpoint["profile_id"],
        "inherit_ambient": bool(profile and profile["inherit_ambient"]),
        "revision": profile["revision"] if profile else None}


def build_dispatcher(deps):
    existing = getattr(deps, "runtime_dispatcher", None)
    if existing:
        return existing
    outbox, endpoints = SqliteRuntimeOutboxRepo(), SqliteEndpointRepo()
    planner = RuntimeDeliveryPlanner(endpoints=endpoints, outbox=outbox, agents=deps.repos.agents)
    supervisor = build_service(deps)
    registry = build_connector_factories(deps)
    messages = build_message_service(deps)

    def validate(uow, operation):
        endpoint, _ = planner.revalidate(uow, operation=operation, config=deps.config)
        messages.revalidate_runtime_delivery(uow, operation)
        if registry.get(endpoint["adapter_id"]).substrate == "attach" and not deps.config.feature_harness_attach:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Attach is disabled.", {})

    def dispatch(operation):
        with deps.connection_factory.unit_of_work(write=False) as uow:
            endpoint, profile = planner.revalidate(uow, operation=operation, config=deps.config)
            workspace = deps.repos.workspaces.get(uow, operation["workspace_id"])
        descriptor = registry.get(endpoint["adapter_id"])
        session_id = operation["runtime_session_id"]
        if session_id is None:
            live = [s for s in supervisor.list_live() if s.endpoint_id == endpoint["endpoint_id"]]
            if len(live) > 1:
                raise OktoNexusError(ErrorCode.CONFLICT, "AMBIGUOUS_BINDING", {})
            if live:
                session_id = live[0].session_id
            else:
                requests = SqliteRuntimeRequestRepo()
                with deps.connection_factory.unit_of_work() as uow:
                    request_id, existing_session = requests.reserve(uow, actor_id=operation["actor_agent_id"],
                        key="delivery:" + operation["operation_id"], request_hash=operation["request_hash"],
                        now=deps.clock.now_iso(), endpoint=endpoint, profile=profile,
                        owner=(operation["owner_id"], operation["owner_epoch"]))
                    if existing_session:
                        raise OktoNexusError(ErrorCode.CONFLICT, "Historical runtime requires reconciliation.", {})
                try:
                    connector, _, _ = construct_profile_connector(deps, endpoint=endpoint, profile=profile,
                        kind=descriptor.kind, substrate=descriptor.substrate, project_root=workspace.root_realpath)
                    session = supervisor.open(kind=descriptor.kind, connector=connector,
                        owning_agent_id=endpoint["agent_id"], project_root=workspace.root_realpath,
                        endpoint_id=endpoint["endpoint_id"], workspace_id=endpoint["workspace_id"],
                        profile_revision=profile["revision"] if profile else None, open_request_id=request_id)
                except Exception:
                    with deps.connection_factory.unit_of_work() as uow:
                        requests.finish(uow, request_id=request_id, status="OUTCOME_UNKNOWN")
                    raise
                session_id = session.session_id
                with deps.connection_factory.unit_of_work() as uow:
                    requests.finish(uow, request_id=request_id, status="COMPLETED")
            with deps.connection_factory.unit_of_work() as uow:
                if not outbox.bind_runtime(uow, operation_id=operation["operation_id"], session_id=session_id,
                        epoch=operation["owner_epoch"], attempt_id=operation["attempt_id"]):
                    raise OktoNexusError(ErrorCode.CONFLICT, "Runtime operation lost ownership.", {})
        operation = operation | {"runtime_session_id": session_id}
        with deps.connection_factory.unit_of_work(write=False) as uow:
            validate(uow, operation)
            current = outbox.get(uow, operation["operation_id"])
            if (not current or current["status"] != "SENDING" or current["owner_epoch"] != operation["owner_epoch"] or
                    not outbox.owns(uow, owner_id=operation["owner_id"], epoch=operation["owner_epoch"], now=deps.clock.now_iso())):
                raise OktoNexusError(ErrorCode.CONFLICT, "Runtime operation lost ownership.", {})
        supervisor.send(session_id, "send_turn", {"envelope": outbox.decode(operation)},
            _transport_attempt={key: operation[key] for key in ("operation_id", "attempt_id", "owner_epoch")})

    dispatcher = RuntimeDispatcher(connection_factory=deps.connection_factory, repo=outbox, clock=deps.clock,
                                  validate=validate, dispatch=dispatch)
    dispatcher.event_ingress = supervisor.event_ingress
    dispatcher.event_ingress.wake_dispatch = dispatcher.wake
    dispatcher.wake_channel = RuntimeWakeChannel(deps.config.home_dir, getattr(deps, "runtime_owner_api_url", None))
    deps.runtime_dispatcher = dispatcher
    return dispatcher


#: Substrate vocabulary for ``kind="claude_code"`` ONLY (see module docstring
#: - the port's ``HARNESS_KINDS`` has no room for a fourth member). Every
#: other kind's ``substrate`` is ``None``.
SUBSTRATE_STREAM = "stream"
SUBSTRATE_ATTACH = "attach"
CLAUDE_CODE_SUBSTRATES: tuple[str, ...] = (SUBSTRATE_STREAM, SUBSTRATE_ATTACH)

#: harness_open's ``backend`` override, per kind - EXACTLY the kwargs each
#: FROZEN connector's own ``__init__`` already accepts (see module docstring
#: on why connector files are not touched here): pi's only override path is
#: argv (``provider``/``model``/``extra_args``); codex and the claude_code
#: "stream" substrate take no such argv, only ``env`` (matches D5/EV-SYS-002:
#: codex's own provider/model/base_url selection is CODEX_HOME + config.toml,
#: read from the process environment, not a flag). claude_code "attach" has
#: no entry here on purpose - it spawns nothing (see
#: :func:`_backend_not_applicable`).
_BACKEND_FIELDS_BY_KIND: dict[str, frozenset[str]] = {
    "pi": frozenset({"command", "provider", "model", "extra_args", "env"}),
    "codex": frozenset({"env", "command", "thread_start_overrides"}),
    "claude_code": frozenset({"env", "binary"}),
}

#: Reused parameter descriptions (kept DRY across the harness tools).
#: _P_HARNESS_AGENT_ID below was last rewritten by the SYS-03/UAT-05 fix
#: (target-grammar-reaches-a-harness), superseding the surface task's own
#: H-2 disclosure text - see docs/harness-integrations/evidence/
#: EV-SYS-003-FOLLOWUP-target-grammar-fix.md.
_P_HARNESS_AGENT_ID = (
    "Existing canonical agent to connect. Requires authorized runtime control; "
    "does not create identity or change its profile."
)
_P_KIND = "Registered adapter kind; discover allowed choices with harness_list."
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
_P_BACKEND = (
    "Deprecated compatibility parameter. Nonempty per-call overrides are rejected; "
    "configure backend options in an approved runtime profile bound to the endpoint."
)
_P_ROLE = "Deprecated compatibility field: must match the existing agent role; never modifies it."
_P_METADATA = "Compatibility metadata; never updates the canonical agent profile."
_P_NOTIFY_TARGET = (
    "Optional result routing intent; it does not authorize publication. "
    "Captured events remain private until a separately authorized publication."
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
        "endpoint_id": session.endpoint_id,
        "workspace_id": session.workspace_id,
        "presence_session_id": session.presence_session_id,
        "lifecycle_state": session.lifecycle_state,
        "connection_id": session.connection_id,
        "owner_epoch": session.owner_epoch,
    }


def event_to_dict(event: HarnessEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "origin": event.origin,
        "sequence": event.sequence,
        "session_id": event.session_id,
        "harness_kind": event.harness_kind,
        "kind": event.kind,
        "native_event": event.native_event,
        "occurred_at": event.occurred_at,
        "payload": dict(event.payload),
        "thread_id": event.thread_id,
        "turn_id": event.turn_id,
    }


def capabilities_catalog(registry=None) -> list[dict[str, Any]]:
    if isinstance(registry, AdapterRegistry):
        return [{"adapter_id": d.adapter_id, "kind": d.kind, "substrate": d.substrate,
                 "contract_version": d.contract_version, "protocol": d.protocol,
                 "supported_platforms": list(d.supported_platforms),
                 "platform_compatible": bool({os.name, sys.platform}.intersection(d.supported_platforms)) if d.supported_platforms else None,
                 "capabilities": capabilities_to_dict(d.legacy_capabilities)}
                for d in registry.descriptors()]
    return _legacy_capabilities_catalog()


def _legacy_capabilities_catalog() -> list[dict[str, Any]]:
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
    return validate_runtime_payload(value, required=required)


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
    # This SAME call also wires (idempotently, cached on deps) the shared
    # InboxDeliveryNotifier this supervisor subscribes to below.
    messages = build_message_service(deps)

    supervisor = HarnessSupervisor(
        connection_factory=deps.connection_factory,
        clock=deps.clock,
        agents=repos.agents,
        sessions=repos.harness_sessions,
        events=repos.harness_events,
        subscribers=InMemoryHarnessSubscriberRegistry(),
        messages=messages,
        # SYS-03/UAT-05 follow-up: the SAME shared notifier build_message_
        # service (above) just wired/reused on deps - this is what makes an
        # ordinary target-grammar delivery (direct/capability/role/tag)
        # addressed at a live session's owning_agent_id actually reach it.
        # Production delivery now reserves the canonical inbox through outbox.
        # Never retain the old per-session fanout alongside that reservation.
        inbox_notifier=None,
        runtime_enabled=lambda: deps.config.feature_harness_integrations,
        endpoint_repo=SqliteEndpointRepo(),
        presence_sessions=deps.repos.sessions,
    )
    from .....application.runtime_event_ingress import RuntimeEventIngress
    from ....outbound.harness.event_journal import FileRuntimeEventJournal
    from ....outbound.sqlite.runtime_journal_repo import SqliteRuntimeJournalRepo
    supervisor.event_ingress = RuntimeEventIngress(
        journal=FileRuntimeEventJournal(deps.config.home_dir), connection_factory=deps.connection_factory,
        repo=SqliteRuntimeJournalRepo(presence=deps.repos.sessions, sessions=repos.harness_sessions),
        events=repos.harness_events, clock=deps.clock,
        publish=supervisor.publish_projected_event)
    from .inbox import build_service as build_inbox_service
    supervisor.event_ingress.consume_terminal = build_inbox_service(deps).consume_runtime_terminal
    deps.harness_supervisor = supervisor
    return supervisor


def _default_connector_factories() -> dict[str, Any]:
    def _pi(
        *, project_root: str, backend: Mapping[str, Any] | None = None, **_ignored: Any
    ) -> HarnessConnector:
        backend = backend or {}
        return PiRpcConnector(
            command=backend.get("command", ("pi", "--mode", "rpc")),
            cwd=project_root,
            provider=backend.get("provider"),
            model=backend.get("model"),
            extra_args=backend.get("extra_args") or (),
            env=backend.get("env"),
        )

    def _codex(
        *, project_root: str, backend: Mapping[str, Any] | None = None, **_ignored: Any
    ) -> HarnessConnector:
        backend = backend or {}
        return CodexAppServerConnector(cwd=project_root, env=backend.get("env"),
            command=backend.get("command", ("codex", "app-server")),
            thread_start_overrides=backend.get("thread_start_overrides"))

    def _claude_code(
        *,
        project_root: str,
        substrate: str,
        target_pid: int | None,
        backend: Mapping[str, Any] | None = None,
        **_ignored: Any,
    ) -> HarnessConnector:
        if substrate == SUBSTRATE_ATTACH:
            # build_connector() already enforced target_pid is not None (and
            # backend is empty) for this substrate; a defensive re-check
            # would only duplicate that message, so this branch trusts its
            # caller (private helper).
            return ClaudeCodeAttachConnector(target_pid)  # type: ignore[arg-type]
        backend = backend or {}
        return ClaudeCodeStreamConnector(cwd=project_root, env=backend.get("env"),
            binary=backend.get("binary", "claude"))

    return {"pi": _pi, "codex": _codex, "claude_code": _claude_code}


def build_connector_factories(deps: Any):
    """Trusted registry in production; explicit legacy injection stays compatible."""
    registry = getattr(deps, "harness_adapter_registry", None)
    if registry is not None:
        return registry
    factories = getattr(deps, "harness_connector_factories", None)
    registry = AdapterRegistry()
    native_factories = factories if factories is not None else _default_connector_factories()
    for entry in _legacy_capabilities_catalog():
        kind, substrate = entry["kind"], entry["substrate"]
        caps = HarnessCapabilities(**entry["capabilities"])
        def factory(*, project_root, target_pid=None, backend=None, kind=kind, substrate=substrate, **_):
            native = build_connector(native_factories, kind=kind, substrate=substrate,
                                     project_root=project_root, target_pid=target_pid, backend=backend)
            return EnvelopeConnector(native, payload_key="content" if kind == "claude_code" else "text")
        registry.register(AdapterDescriptor(
            adapter_id=kind + ("." + substrate if substrate else ""),
            kind=kind, substrate=substrate,
            protocol={"pi": "rpc-jsonl", "codex": "json-rpc-stdio"}.get(kind, substrate),
            factory=factory, config_validator=lambda config: runtime_object("backend", config),
            capabilities=EndpointCapabilities(conversation=True, events=not caps.send_only,
                multiplexing=caps.multiplexes_sessions, steer_timing=caps.steer_timing,
                interrupt=not caps.send_only, interrupt_requires_settle=caps.interrupt_requires_settle_wait,
                observes_stop=caps.observes_session_end),
            legacy_capabilities=caps,
            supported_platforms=("posix",) if substrate == SUBSTRATE_ATTACH else ("nt", "linux"),
        ))
    deps.harness_adapter_registry = registry
    return registry


def resolve_substrate(kind: str, substrate: str | None) -> str | None:
    """The same ``kind='claude_code'``-only substrate default
    (``stream`` when omitted) :func:`build_connector` applies internally,
    exposed so callers that need it for a DIFFERENT purpose (currently
    :func:`describe_backend`) never re-derive it differently. Not a
    validator - :func:`build_connector` still owns fail-closed validation.
    """
    if kind != "claude_code":
        if substrate is not None:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Substrate only applies to claude_code.", {})
        return None
    return substrate or SUBSTRATE_STREAM


def describe_backend(
    kind: str, substrate: str | None, backend: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Build the ``backend`` field ``harness_open`` returns (H-1 fix): make
    the resolved backend choice VISIBLE in the response, whether the caller
    supplied one or not - never a silent inherit. Called AFTER
    :func:`build_connector` already validated ``backend`` against ``kind``,
    so this never re-raises; it only describes.
    """
    resolved_substrate = resolve_substrate(kind, substrate)
    if kind == "claude_code" and resolved_substrate == SUBSTRATE_ATTACH:
        return {
            "explicit": False,
            "applied": {},
            "note": (
                "not applicable: substrate='attach' injects into an "
                "already-running process and spawns nothing to configure."
            ),
        }
    allowed = sorted(_BACKEND_FIELDS_BY_KIND.get(kind, ()))
    if not backend:
        return {
            "explicit": False,
            "applied": {},
            "note": (
                f"no backend override supplied - this '{kind}' session "
                "inherits its connector's own ambient default (its own "
                "config file, or the okto-nexus serve process's own "
                "environment), NOT a choice okto-nexus made. Supported "
                f"override fields for this kind: {allowed}."
            ),
        }
    return {
        "explicit": True,
        "applied": {key: value if key in {"provider", "model"} else "[REDACTED]"
                    for key, value in backend.items()},
        "note": "Backend override applied; environment and arguments are redacted.",
    }


def build_connector(
    factories: Mapping[str, Any],
    *,
    kind: str,
    project_root: str,
    substrate: str | None,
    target_pid: int | None,
    backend: Mapping[str, Any] | None = None,
) -> HarnessConnector:
    """Validate ``substrate``/``target_pid``/``backend`` against ``kind``
    (fail-closed, BEFORE touching the factory table - see module docstring's
    substrate note) and construct the connector. Shared verbatim by
    ``harness_open`` and its REST mirror so the two surfaces can never
    disagree on this validation.

    ``backend`` (H-1 fix, EV-SYS-002): an explicit, per-kind override
    instead of silently inheriting the operator's own ambient CLI config -
    see :data:`_P_BACKEND`/:data:`_BACKEND_FIELDS_BY_KIND`. A field this
    kind does not support is a VALIDATION_ERROR, never a silent drop (that
    silent-drop shape is exactly the H-2 defect class, not repeated here).
    """
    if isinstance(factories, AdapterRegistry):
        descriptor = factories.resolve(kind, resolve_substrate(kind, substrate))
        descriptor.config_validator(dict(backend or {}))
        return descriptor.factory(project_root=project_root, substrate=substrate,
                                  target_pid=target_pid, backend=backend)
    if backend is None:
        backend_obj: dict[str, Any] = {}
    elif isinstance(backend, Mapping):
        backend_obj = dict(backend)
    else:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"backend must be a JSON object (got {type(backend).__name__}).",
            {"backend_type": type(backend).__name__},
        )
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

    # H-1 fix: backend is validated fail-closed, per kind/substrate - an
    # unsupported field is a VALIDATION_ERROR naming what IS supported,
    # never a silent drop (build_connector is the ONE place both surfaces
    # construct a connector, so this can't drift between them - module
    # docstring).
    if kind == "claude_code" and resolved_substrate == SUBSTRATE_ATTACH:
        if backend_obj:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "backend does not apply to substrate='attach' - it injects "
                "into an already-running process and spawns nothing to "
                "configure.",
                {"kind": kind, "substrate": resolved_substrate},
            )
    else:
        allowed = _BACKEND_FIELDS_BY_KIND.get(kind, frozenset())
        unsupported = set(backend_obj) - allowed
        if unsupported:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"backend field(s) {sorted(unsupported)} are not supported "
                f"for kind='{kind}'; supported: {sorted(allowed)}.",
                {"kind": kind, "unsupported": sorted(unsupported), "supported": sorted(allowed)},
            )
        extra_args = backend_obj.get("extra_args")
        if extra_args is not None and (
            not isinstance(extra_args, (list, tuple))
            or not all(isinstance(item, str) for item in extra_args)
        ):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "backend.extra_args must be a JSON array of strings.",
                {"kind": kind, "extra_args": extra_args},
            )
        env = backend_obj.get("env")
        if env is not None and (
            not isinstance(env, Mapping)
            or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items())
        ):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "backend.env must be a JSON object of string -> string.",
                {"kind": kind, "env": env},
            )
        for str_field in ("provider", "model"):
            value = backend_obj.get(str_field)
            if value is not None and not isinstance(value, str):
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    f"backend.{str_field} must be a string.",
                    {"kind": kind, str_field: value},
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
        backend=backend_obj,
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
    if not deps.config.feature_harness_integrations:
        return
    supervisor = build_service(deps)
    factories = build_connector_factories(deps)

    @server.tool()
    @tool_envelope
    @runtime_tool_guard(deps)
    def harness_list() -> dict[str, Any]:
        """List available harness kinds/substrates and their DECLARED capabilities (send_only, steer_timing, etc.), read from each connector's own declaration. Check before harness_steer/harness_interrupt."""
        return {"harnesses": capabilities_catalog(factories)}

    @server.tool()
    @async_tool_envelope
    @runtime_tool_guard(deps)
    async def harness_open(
        agent_id: Annotated[str, Field(description=_P_HARNESS_AGENT_ID)],
        kind: Annotated[str, Field(description=_P_KIND)],
        project_root: Annotated[str, Field(description=_P_ROOT)],
        substrate: Annotated[str | None, Field(description=_P_SUBSTRATE)] = None,
        target_pid: Annotated[int | None, Field(description=_P_TARGET_PID)] = None,
        backend: Annotated[Any, Field(description=_P_BACKEND)] = None,
        endpoint_id: Annotated[str | None, Field(description="Approved endpoint binding; required when selection is ambiguous.")] = None,
        role: Annotated[str | None, Field(description=_P_ROLE)] = None,
        metadata: Annotated[Any, Field(description=_P_METADATA)] = None,
        notify_target: Annotated[Any, Field(description=_P_NOTIFY_TARGET)] = None,
        idempotency_key: Annotated[str | None, Field(description="Stable key for this open request; retries never create another runtime.")] = None,
    ) -> dict[str, Any]:
        """Open a runtime for an existing agent. Requires operator authority and opt-in; never changes the agent profile."""
        return await anyio.to_thread.run_sync(functools.partial(
            open_runtime, deps, agent_id=agent_id, kind=kind, project_root=project_root,
            substrate=substrate, target_pid=target_pid, backend=backend, endpoint_id=endpoint_id,
            role=role, metadata=metadata, notify_target=notify_target, idempotency_key=idempotency_key))

    @server.tool()
    @async_tool_envelope
    @runtime_tool_guard(deps)
    async def harness_send(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
        payload: Annotated[Any, Field(description=_P_PAYLOAD_TURN)],
    ) -> dict[str, Any]:
        """Send a turn to a live session (send_turn). Never blocks for a reply - the answer arrives later as harness events (subscribe out-of-band, or poll harness_event_list)."""
        body = normalize_payload(payload, required=True)
        await anyio.to_thread.run_sync(
            functools.partial(authorized_send, deps, supervisor, session_id, "send_turn", body)
        )
        return {"session_id": session_id, "verb": "send_turn"}

    @server.tool()
    @async_tool_envelope
    @runtime_tool_guard(deps)
    async def harness_steer(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
        payload: Annotated[Any, Field(description=_P_PAYLOAD_STEER)],
    ) -> dict[str, Any]:
        """Steer a live session's in-flight turn. Rejected if the connector's steer_timing is null (unsupported - check harness_list). NEXT_TURN_BOUNDARY buffers until the next turn; IMMEDIATE can land mid-turn."""
        body = normalize_payload(payload, required=True)
        await anyio.to_thread.run_sync(
            functools.partial(authorized_send, deps, supervisor, session_id, "steer", body)
        )
        return {"session_id": session_id, "verb": "steer"}

    @server.tool()
    @async_tool_envelope
    @runtime_tool_guard(deps)
    async def harness_interrupt(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
        payload: Annotated[Any, Field(description=_P_PAYLOAD_INTERRUPT)] = None,
    ) -> dict[str, Any]:
        """Interrupt a live session's in-flight turn (abort). If interrupt_requires_settle_wait is true, a send/steer right after may be refused (CONFLICT) until the aborted turn's settle event lands."""
        body = normalize_payload(payload, required=False)
        await anyio.to_thread.run_sync(
            functools.partial(authorized_send, deps, supervisor, session_id, "interrupt", body)
        )
        return {"session_id": session_id, "verb": "interrupt"}

    @server.tool()
    @async_tool_envelope
    @runtime_tool_guard(deps)
    async def harness_close(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
    ) -> dict[str, Any]:
        """End a live session (best-effort teardown: send(end) then close()) and stop tracking it. Always returns the final session state, even if teardown failed - close() never hangs (D8)."""
        session = await anyio.to_thread.run_sync(
            functools.partial(authorized_close, deps, supervisor, session_id)
        )
        return session

    @server.tool()
    @tool_envelope
    @runtime_tool_guard(deps)
    def harness_get(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
    ) -> dict[str, Any]:
        """Read one harness session: the LIVE in-memory view if still tracked (live:true), else the last durable row (live:false - RUNNING there is NOT proof of liveness). NOT_FOUND if never opened."""
        return read_session(deps, supervisor, session_id)

    @server.tool()
    @tool_envelope
    @runtime_tool_guard(deps)
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
