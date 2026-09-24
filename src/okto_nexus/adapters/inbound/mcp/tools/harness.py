"""Authenticated runtime tools shared with REST and internal dispatch.

An existing canonical agent owns configured endpoints and approved profiles.
Runtime opens never create or rewrite that identity. The serve owner supervises
native resources; the inbox and durable outbox govern logical delivery and
transport attempts. Event results require separate publication authorization.
All enabled surfaces use the same authorization and application services.
"""

from __future__ import annotations

import functools
import hashlib
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


def request_context():
    """Resolve only middleware identity; payload identifiers are never principals."""
    actor = get_authenticated_agent()
    local = trusted_local_operator.get()
    return RuntimeRequestContext(
        actor.agent_id if actor else None,
        "http_loopback" if local else "agent_key" if actor else "unauthenticated",
        trusted_local_operator=local,
        credential_binding=actor.api_key_hash if actor else None,
    )


def authorize_request(deps, *, substrate=None, action="admin", session_id=None, endpoint_id=None,
                      represented_agent_id=None, workspace_id=None, consume=False, check_budget=True):
    """Same authenticated admission policy for MCP, REST and local HTTP."""
    context = request_context()
    build_access_service(deps).authorize(context, action=action, substrate=substrate,
        session_id=session_id, endpoint_id=endpoint_id, represented_agent_id=represented_agent_id,
        workspace_id=workspace_id, consume=consume, check_budget=check_budget)
    return context


def authorized_send(deps, supervisor, session_id, verb, payload, **options):
    context = authorize_request(deps, action="send" if verb == "send_turn" else verb, session_id=session_id, check_budget=False)
    if not is_local_runtime_owner(deps):
        action = "send" if verb == "send_turn" else verb
        if not options.get("idempotency_key"):
            options["idempotency_key"] = new_id("command-key")
        return call_runtime_owner(deps.config.home_dir, f"/api/v1/harness/sessions/{quote(session_id, safe='')}/{action}", {"payload": payload, **options})
    return deps.runtime_dispatcher.command_dispatcher.service.send(context,
        session_id=session_id, verb=verb, payload=payload, **options)


def authorized_close(deps, supervisor, session_id, **options):
    context = authorize_request(deps, action="close", session_id=session_id)
    if not is_local_runtime_owner(deps):
        return call_runtime_owner(deps.config.home_dir, f"/api/v1/harness/sessions/{quote(session_id, safe='')}/close", options)
    return deps.runtime_dispatcher.command_dispatcher.service.close(context, session_id=session_id, **options)


def read_operation(deps, operation_id):
    from okto_nexus.adapters.outbound.sqlite.runtime_commands_repo import SqliteRuntimeCommandRepo
    context = authorize_request(deps, action="access")
    service = RuntimeControlService(access=build_access_service(deps), supervisor=None, commands=SqliteRuntimeCommandRepo())
    return service.get_operation(context, operation_id=operation_id)


def maintain_journal(deps, *, compact=False):
    from okto_nexus.application.runtime_maintenance import RuntimeMaintenanceService
    context = authorize_request(deps)
    if not is_local_runtime_owner(deps):
        return call_runtime_owner(deps.config.home_dir, "/api/v1/harness/journal", {"compact": compact})
    return RuntimeMaintenanceService(access=build_access_service(deps),
        dispatcher=deps.runtime_dispatcher).journal(context, compact=compact)


def maintain_artifacts(deps, parameters=None):
    from okto_nexus.application.runtime_maintenance import RuntimeMaintenanceService
    context = authorize_request(deps)
    parameters = runtime_object("maintenance", parameters if parameters is not None else {})
    if set(parameters) - {"action", "result_id", "quota_bytes", "idempotency_key", "reason"}:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Unknown artifact maintenance parameter.", {})
    if not is_local_runtime_owner(deps):
        return call_runtime_owner(deps.config.home_dir, "/api/v1/harness/artifacts", parameters)
    return RuntimeMaintenanceService(access=build_access_service(deps), dispatcher=deps.runtime_dispatcher,
        artifact_store=deps.repos.artifact_store).artifacts(context, **parameters)


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
            if fn.__name__ == "harness_list" and arguments.get("view") in {"bindings", "outbox"}:
                # Shared services authenticate their own scoped reads/recovery.
                # Operator outbox recovery survives admission being disabled.
                return
            if fn.__name__ == "harness_get" and arguments.get("operation_id"):
                # The service resolves the stored resource before authorizing
                # its session; caller-supplied IDs never supply identity.
                return
            authorize_request(deps, action=action, substrate=arguments.get("substrate"),
                              session_id=arguments.get("session_id"), check_budget=action not in {"send", "steer"})
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


def discover_bindings(deps, parameters=None):
    from okto_nexus.application.runtime_discovery import RuntimeDiscoveryService
    args = runtime_object("maintenance", parameters) or {}
    if set(args) - {"agent_id", "after_endpoint_id", "limit"}:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Unsupported discovery parameters.", {})
    return RuntimeDiscoveryService(access=build_access_service(deps)).list(request_context(), **args)


def maintain_operations(deps, parameters=None):
    from pydantic import ValidationError
    from ...runtime_admin import RuntimeOperationMaintenanceBody
    from okto_nexus.application.runtime_operation_maintenance import RuntimeOperationMaintenanceService
    from .inbox import build_service as build_inbox
    from .handoff import build_service as build_handoffs
    context = request_context()
    access = build_access_service(deps)
    access.authorize_maintenance(context)
    try:
        args = RuntimeOperationMaintenanceBody.model_validate(runtime_object("maintenance", parameters) or {}).model_dump()
    except ValidationError:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid operation maintenance fields.", {}) from None
    owner = getattr(deps, "runtime_dispatcher", None)
    if owner is None and args["action"] != "inspect":
        return call_runtime_owner(deps.config.home_dir, "/api/v1/harness/outbox", args)
    return RuntimeOperationMaintenanceService(access=access, owner=owner,
        inbox=build_inbox(deps), handoffs=build_handoffs(deps)).run(context, **args)


def administer_endpoints(deps, view, parameters):
    from pydantic import ValidationError
    from ...runtime_admin import (RuntimeProfileBody, RuntimeEndpointBody, RuntimeBootBody,
        RuntimeEndpointUpdateBody, RuntimeReconcileBody, RuntimeProfileUpdateBody)
    context = authorize_request(deps)
    service = build_endpoint_service(deps)
    args = runtime_object("maintenance", parameters) or {}
    action = args.pop("action", "list")
    if action == "list":
        if set(args) - ({"agent_id"} if view == "endpoints" else set()):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Unsupported listing parameters.", {})
        if "agent_id" in args and not isinstance(args["agent_id"], str):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "agent_id must be a string.", {})
        return {"items": service.list(context, **args) if view == "endpoints" else service.profiles(context)}
    actions = {("profiles", "create"): (RuntimeProfileBody, service.create_profile),
        ("profiles", "update"): (RuntimeProfileUpdateBody, service.update_profile),
        ("endpoints", "create"): (RuntimeEndpointBody, service.create_endpoint),
        ("endpoints", "update"): (RuntimeEndpointUpdateBody, service.update_endpoint),
        ("endpoints", "boot"): (RuntimeBootBody, service.configure_boot),
        ("endpoints", "reconcile"): (RuntimeReconcileBody, service.reconcile)}
    if not isinstance(action, str) or (view, action) not in actions:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Unsupported runtime administration action.", {})
    model, execute = actions[(view, action)]
    resource = {}
    if view == "profiles" and action == "update":
        profile_id = args.pop("profile_id", None)
        if not isinstance(profile_id, str) or not 1 <= len(profile_id) <= 128:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "A profile_id is required.", {})
        resource["profile_id"] = profile_id
    if view == "endpoints" and action != "create":
        endpoint_id = args.pop("endpoint_id", None)
        if not isinstance(endpoint_id, str) or not 1 <= len(endpoint_id) <= 128:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "An endpoint_id is required.", {})
        resource["endpoint_id"] = endpoint_id
    try:
        parsed = model.model_validate(args).model_dump(exclude_unset=action == "update")
    except ValidationError:
        # Never return input values from a profile/secret validation error.
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid runtime administration parameters.", {}) from None
    return execute(context, **resource, **parsed)


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
        from okto_nexus.application.runtime_requirements import validate_native_requirements
        validate_native_requirements(config, build_connector_factories(deps).get(endpoint["adapter_id"]),
                                     hitl_enabled=deps.config.feature_hitl)
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
    required = profile["config"].get("required_native_requests", ()) if profile else ()
    if required:
        configure_requirements = getattr(connector, "configure_native_requirements", None)
        if not callable(configure_requirements):
            raise OktoNexusError(ErrorCode.CONFIG_ERROR, "Adapter cannot verify required native contracts.", {})
        configure_requirements(required)
    configure_reuse = getattr(connector, "configure_connection_reuse", None)
    if profile and callable(configure_reuse):
        # Include resolved environment so rotating a secret cannot silently reuse
        # an old process. The digest is private memory, never an API/store field.
        material = [endpoint["agent_id"], endpoint["workspace_id"], endpoint["adapter_id"],
                    project_root, profile["profile_id"], profile["revision"],
                    effective_backend, list(required), bool(deps.config.feature_hitl)]
        configure_reuse(hashlib.sha256(json.dumps(material, sort_keys=True).encode()).digest())
    return connector, endpoint, {"profile_id": endpoint["profile_id"],
        "inherit_ambient": bool(profile and profile["inherit_ambient"]),
        "revision": profile["revision"] if profile else None}


def build_dispatcher(deps):
    existing = getattr(deps, "runtime_dispatcher", None)
    if existing:
        return existing
    outbox, endpoints = SqliteRuntimeOutboxRepo(), SqliteEndpointRepo()
    planner = RuntimeDeliveryPlanner(endpoints=endpoints, outbox=outbox, agents=deps.repos.agents,
                                    registry=build_connector_factories(deps), config=deps.config)
    supervisor = build_service(deps)
    registry = build_connector_factories(deps)
    messages = build_message_service(deps)
    from .handoff import build_service as build_handoff_service
    handoffs = build_handoff_service(deps)
    work = handoffs.runtime_work

    def managed(uow, operation):
        return uow.connection.execute("SELECT 1 FROM runtime_handoff_bindings WHERE operation_id=?",
                                      (operation["operation_id"],)).fetchone() is not None

    def revalidate(uow, operation):
        return (work.revalidate(uow, operation=operation) if managed(uow, operation)
                else planner.revalidate(uow, operation=operation, config=deps.config))

    def validate(uow, operation):
        endpoint, _ = revalidate(uow, operation)
        if operation.get("source_result_id"):
            messages._runtime_results.validate_relay(uow, operation["source_result_id"])
        if not managed(uow, operation):
            messages.revalidate_runtime_delivery(uow, operation)
        if registry.get(endpoint["adapter_id"]).substrate == "attach" and not deps.config.feature_harness_attach:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Attach is disabled.", {})

    def validate_dispatch(uow, operation):
        validate(uow, operation)
        planner.causality.validate_dispatch(uow, operation=operation, now=deps.clock.now_iso())

    def dispatch(operation):
        with deps.connection_factory.unit_of_work(write=False) as uow:
            validate_dispatch(uow, operation)
            endpoint, profile = revalidate(uow, operation)
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
            validate_dispatch(uow, operation)
            current = outbox.get(uow, operation["operation_id"])
            if (not current or current["status"] != "SENDING" or current["owner_epoch"] != operation["owner_epoch"] or
                    not outbox.owns(uow, owner_id=operation["owner_id"], epoch=operation["owner_epoch"], now=deps.clock.now_iso())):
                raise OktoNexusError(ErrorCode.CONFLICT, "Runtime operation lost ownership.", {})
        supervisor.send(session_id, "send_turn", {"envelope": outbox.decode(operation)},
            _transport_attempt={key: operation[key] for key in ("operation_id", "attempt_id", "owner_epoch")})

    dispatcher = RuntimeDispatcher(connection_factory=deps.connection_factory, repo=outbox, clock=deps.clock,
                                  validate=validate_dispatch, dispatch=dispatch)
    dispatcher.event_ingress = supervisor.event_ingress
    def publish_results():
        return native_approvals.scan_once() + handoffs.process_runtime_results() + messages._runtime_results.scan_once(messages)
    dispatcher.publish_results = publish_results
    dispatcher.event_ingress.wake_dispatch = dispatcher.wake
    dispatcher.wake_channel = RuntimeWakeChannel(deps.config.home_dir, getattr(deps, "runtime_owner_api_url", None))
    deps.runtime_dispatcher = dispatcher
    from okto_nexus.adapters.outbound.sqlite.runtime_commands_repo import SqliteRuntimeCommandRepo
    from okto_nexus.application.runtime_command_dispatcher import RuntimeCommandDispatcher
    commands = SqliteRuntimeCommandRepo()
    control_service = RuntimeControlService(access=build_access_service(deps), supervisor=supervisor,
        owner_guard=lambda: is_local_runtime_owner(deps) and not dispatcher._quiescing.is_set(), commands=commands, wake=dispatcher.wake)
    dispatcher.command_dispatcher = RuntimeCommandDispatcher(owner=dispatcher, repo=commands, service=control_service)
    from okto_nexus.application.runtime_native_approvals import RuntimeNativeApprovalService
    native_approvals = RuntimeNativeApprovalService(owner=dispatcher, supervisor=supervisor,
        approvals=deps.approvals, config=deps.config, validate_delivery=validate, validate_command=control_service.validate)
    dispatcher.native_approvals = native_approvals
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
_P_SESSION_ID = "Runtime session returned by harness_open; harness_get may select operation_id instead."
_P_PAYLOAD_TURN = (
    'One nonempty text/content string, e.g. {"text":"prompt"}. '
    "The adapter translates it; arbitrary native options are rejected."
)
_P_PAYLOAD_STEER = _P_PAYLOAD_TURN
_P_PAYLOAD_INTERRUPT = "Omit or use an empty object; interrupt does not accept native options."
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
        "compatibility_report": dict(session.compatibility_report),
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
        "operation_id": event.operation_id,
        "attempt_id": event.attempt_id,
        "owner_epoch": event.owner_epoch,
        "delivery_phase": event.delivery_phase,
        "delivery_outcome": event.delivery_outcome,
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
            if hasattr(native, "native_approvals_enabled"):
                native.native_approvals_enabled = bool(deps.config.feature_hitl)
            return EnvelopeConnector(native, payload_key="content" if kind == "claude_code" else "text")
        registry.register(AdapterDescriptor(
            adapter_id=kind + ("." + substrate if substrate else ""),
            kind=kind, substrate=substrate,
            protocol={"pi": "rpc-jsonl", "codex": "json-rpc-stdio"}.get(kind, substrate),
            factory=factory, config_validator=lambda config: runtime_object("backend", config),
            capabilities=EndpointCapabilities(conversation=True, events=not caps.send_only, managed_work=not caps.send_only,
                correlated_results=not caps.send_only,
                multiplexing=caps.multiplexes_sessions, steer_timing=caps.steer_timing,
                interrupt=not caps.send_only, interrupt_requires_settle=caps.interrupt_requires_settle_wait,
                observes_stop=caps.observes_session_end, approvals=kind == "codex" or (kind == "claude_code" and substrate == "stream")),
            input_schema=({"native_approval_contract": 1, "requires_feature_hitl": True,
                "methods": ["item/commandExecution/requestApproval", "item/fileChange/requestApproval",
                            "item/tool/requestUserInput", "mcpServer/elicitation/request"],
                "decisions": ["accept", "decline"], "input_contract": 1,
                "input_limits": "blocking non-secret questions; correlated form elicitation with flat primitive fields only; no URL or remote schema resolution"} if kind == "codex" else
                {"native_approval_contract": 1, "requires_feature_hitl": True,
                 "methods": ["control_request:can_use_tool"], "tools": ["Write", "Edit", "Bash", "AskUserQuestion"],
                 "decisions": ["accept", "decline"], "correlation": "operation_and_local_generation"}
                if kind == "claude_code" and substrate == "stream" else {}),
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
    def harness_list(view: str = "adapters", compact: bool = False,
                     maintenance: Annotated[Any, Field(description="Object for selected view: profile/endpoint admin; outbox inspect/cancel_pending/release_to_inbox/abandon_command/recover_handoff; artifact maintenance. Fields: okto-nexus://reference/tool-docs/identity.")] = None) -> dict[str, Any]:
        """Discover authorized runtimes with view=bindings. Operator views: adapters, endpoints, profiles, outbox, journal, artifacts. Outbox recovery never replays native calls. compact requires journal."""
        if view == "bindings" and not compact:
            return discover_bindings(deps, maintenance)
        if view == "outbox" and not compact:
            return maintain_operations(deps, maintenance)
        if view in {"endpoints", "profiles"} and not compact:
            return administer_endpoints(deps, view, maintenance)
        if view == "artifacts" and not compact:
            return maintain_artifacts(deps, maintenance)
        if maintenance is not None:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Maintenance requires artifacts view.", {})
        if view == "journal":
            return maintain_journal(deps, compact=compact)
        if view != "adapters" or compact:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Use adapters, journal or artifacts view; compact requires journal.", {})
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
        idempotency_key: str | None = None,
        expected_operation_id: str | None = None,
        expected_turn_id: str | None = None,
        expected_owner_epoch: int | None = None,
    ) -> dict[str, Any]:
        """Durably queue a turn. Supply idempotency_key for safe request retries. Admission does not confirm native acceptance; results arrive as correlated events."""
        body = normalize_payload(payload, required=True)
        return await anyio.to_thread.run_sync(
            functools.partial(authorized_send, deps, supervisor, session_id, "send_turn", body, idempotency_key=idempotency_key,
                expected_operation_id=expected_operation_id, expected_turn_id=expected_turn_id, expected_owner_epoch=expected_owner_epoch)
        )

    @server.tool()
    @async_tool_envelope
    @runtime_tool_guard(deps)
    async def harness_steer(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
        payload: Annotated[Any, Field(description=_P_PAYLOAD_STEER)],
        idempotency_key: str | None = None,
        expected_operation_id: str | None = None,
        expected_turn_id: str | None = None,
        expected_owner_epoch: int | None = None,
    ) -> dict[str, Any]:
        """Steer a live session's in-flight turn. Rejected if the connector's steer_timing is null (unsupported - check harness_list). NEXT_TURN_BOUNDARY buffers until the next turn; IMMEDIATE can land mid-turn."""
        body = normalize_payload(payload, required=True)
        return await anyio.to_thread.run_sync(
            functools.partial(authorized_send, deps, supervisor, session_id, "steer", body, idempotency_key=idempotency_key,
                expected_operation_id=expected_operation_id, expected_turn_id=expected_turn_id, expected_owner_epoch=expected_owner_epoch)
        )

    @server.tool()
    @async_tool_envelope
    @runtime_tool_guard(deps)
    async def harness_interrupt(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
        payload: Annotated[Any, Field(description=_P_PAYLOAD_INTERRUPT)] = None,
        idempotency_key: str | None = None,
        expected_operation_id: str | None = None,
        expected_turn_id: str | None = None,
        expected_owner_epoch: int | None = None,
    ) -> dict[str, Any]:
        """Interrupt a live session's in-flight turn (abort). If interrupt_requires_settle_wait is true, a send/steer right after may be refused (CONFLICT) until the aborted turn's settle event lands."""
        body = normalize_payload(payload, required=False)
        return await anyio.to_thread.run_sync(
            functools.partial(authorized_send, deps, supervisor, session_id, "interrupt", body, idempotency_key=idempotency_key,
                expected_operation_id=expected_operation_id, expected_turn_id=expected_turn_id, expected_owner_epoch=expected_owner_epoch)
        )

    @server.tool()
    @async_tool_envelope
    @runtime_tool_guard(deps)
    async def harness_close(
        session_id: Annotated[str, Field(description=_P_SESSION_ID)],
        idempotency_key: str | None = None,
        expected_owner_epoch: int | None = None,
    ) -> dict[str, Any]:
        """Durably request closure. The operation tracks stop/detach/unknown; admission does not claim native termination."""
        session = await anyio.to_thread.run_sync(
            functools.partial(authorized_close, deps, supervisor, session_id,
                idempotency_key=idempotency_key, expected_owner_epoch=expected_owner_epoch)
        )
        return session

    @server.tool()
    @tool_envelope
    @runtime_tool_guard(deps)
    def harness_get(
        session_id: Annotated[str | None, Field(description=_P_SESSION_ID)] = None,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        """Read exactly one session_id or operation_id. Operation state separates queueing, native acceptance and durable result; historical session rows do not prove liveness."""
        if bool(session_id) == bool(operation_id):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Specify exactly one session_id or operation_id.", {})
        return read_operation(deps, operation_id) if operation_id else read_session(deps, supervisor, session_id)

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
