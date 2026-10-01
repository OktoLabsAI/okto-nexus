"""Route existing harness session callers through canonical R4 admission."""
import json
from pathlib import Path

from nexus_connector_core import CoreError, get_runtime_catalog, validate_control_target

from ..adapters.outbound.execution.core_inventory import protocol_info
from ..adapters.outbound.sqlite.execution_identity import ensure_execution_installation
from ..application.execution_admission import submit_execution_operation
from ..application.execution_intents import resolve_execution_intent
from ..application.execution_session_views import read_execution_session
from ..errors import ErrorCode, OktoNexusError
from .execution_authority import build_execution_access


def canonical_endpoint(deps, endpoint_id):
    if not endpoint_id:
        return None
    with deps.connection_factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute(
            "SELECT b.*,ep.agent_id,ep.adapter_id,l.local_record_json FROM execution_bindings b "
            "JOIN execution_installation i ON i.server_id=b.server_id "
            "JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id "
            "LEFT JOIN execution_local_realizations l ON l.server_id=b.server_id "
            "AND l.executor_id=b.executor_id AND l.realization_ref=b.realization_ref "
            "WHERE b.endpoint_id=? LIMIT 2", (endpoint_id,)).fetchall()
    if len(rows) > 1:
        raise OktoNexusError(ErrorCode.CONFLICT,
            "Ambiguous endpoint binding; use the scoped R4 API.", {})
    return dict(rows[0]) if rows else None


def open_session(deps, context, binding, arguments):
    access = build_execution_access(deps)
    access.authorize(context, action="open", endpoint_id=binding["endpoint_id"],
                     represented_agent_id=arguments["agent_id"])
    if arguments["agent_id"] != binding["agent_id"] or context.actor_agent_id != binding["agent_id"]:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
            "Open the canonical binding with its subject identity.", {})
    if any(arguments.get(name) is not None for name in
           ("backend", "metadata", "notify_target", "target_pid")):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
            "Canonical opening uses the approved realization, without per-call runtime overrides.", {})
    descriptor = next((item for item in get_runtime_catalog().runtimes
                       if item.adapter_id == binding["adapter_id"]), None)
    if (descriptor is None or arguments["kind"] != descriptor.native_kind or
            descriptor.connection_mode != "managed" or
            arguments.get("substrate") not in (None, "stream")):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
            "The requested runtime does not match the canonical binding.", {})
    if not binding["local_record_json"]:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
            "Remote bindings require the path-free R4 intent API.", {})
    root = json.loads(binding["local_record_json"])["root"]["path"]
    if Path(arguments["project_root"]).resolve() != Path(root):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
            "The project root does not match the approved realization.", {})
    from ..application.runtime_authorization import require_runtime_agent
    require_runtime_agent(agents=deps.repos.agents, connection_factory=deps.connection_factory,
                          agent_id=arguments["agent_id"], role=arguments.get("role"))
    return _start(deps, context, access, binding, arguments.get("idempotency_key"))


def connect_endpoint(deps, context, binding, key):
    """Path-free endpoint connect uses the same approved local/remote binding."""
    access = build_execution_access(deps)
    access.authorize(context, action="open", endpoint_id=binding["endpoint_id"],
                     represented_agent_id=binding["agent_id"])
    if context.actor_agent_id != binding["agent_id"]:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
            "Connect with the canonical binding's subject identity.", {})
    return _start(deps, context, access, binding, key)


def _start(deps, context, access, binding, key):
    if not isinstance(key, str) or not 1 <= len(key) <= 160 or key == "<unique-key-for-this-opening>":
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
            "A stable idempotency_key is required for an R4 opening.", {})
    return _admit(deps, context, access, dict(client_intent_id=key,
        intent="runtime.start", binding_id=binding["binding_id"],
        workspace_binding_id=binding["workspace_binding_id"], new_session=True))


def canonical_session(deps, session_id):
    if not session_id:
        return None
    with deps.connection_factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute(
            "SELECT s.*,ep.adapter_id,b.endpoint_id FROM execution_sessions s "
            "JOIN execution_installation i ON i.server_id=s.server_id "
            "LEFT JOIN execution_bindings b ON b.server_id=s.server_id "
            "AND b.executor_id=s.executor_id AND b.binding_id=s.binding_id "
            "LEFT JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id "
            "WHERE s.session_id=? LIMIT 2", (session_id,)).fetchall()
    if len(rows) > 1:
        raise OktoNexusError(ErrorCode.CONFLICT,
            "Ambiguous session ID; use the scoped R4 API.", {})
    return dict(rows[0]) if rows else None


def session_view(deps, context, session_id):
    return read_execution_session(deps.connection_factory,
        server_id=ensure_execution_installation(deps.connection_factory).server_id,
        session_id=session_id, context=context, access=build_execution_access(deps))


def command(deps, context, session, verb, payload, options):
    """Translate product verbs only; Core owns native targeting and execution."""
    access = build_execution_access(deps)
    access.authorize(context, action="send" if verb == "send_turn" else verb,
                     endpoint_id=session["endpoint_id"])
    if any(value is not None for key, value in options.items()
           if key not in {"idempotency_key", "expected_turn_id"}):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
            "Legacy operation/owner guards cannot address an R4 session.", {})
    key = options.get("idempotency_key")
    if not isinstance(key, str) or not 1 <= len(key) <= 160:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
            "A stable idempotency_key is required for an R4 command.", {})
    intent = {"send_turn": "turn.submit", "steer": "turn.steer",
              "interrupt": "turn.interrupt", "close": "runtime.close"}[verb]
    request = dict(client_intent_id=key, intent=intent,
        binding_id=session["binding_id"], workspace_binding_id=session["workspace_binding_id"],
        session_id=session["session_id"])
    if verb in {"send_turn", "steer"}:
        if not isinstance(payload, dict) or set(payload) != {"text"}:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                "R4 turn payload must contain exactly text.", {})
        request["text"] = payload["text"]
    elif payload not in (None, {}):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
            "This R4 command does not accept a payload.", {})
    turn = options.get("expected_turn_id")
    if verb in {"steer", "interrupt"}:
        try:
            target = validate_control_target(session["adapter_id"], intent, turn)
        except CoreError as exc:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                "Invalid Core control target.", {}) from exc
        request["target"] = dict(kind="native_turn_id" if turn is not None else
            "current_run" if target.requires_active_run else "none", expected_turn_id=turn)
    elif turn is not None:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
            "This R4 command cannot target a turn.", {})
    return _admit(deps, context, access, request)


def _admit(deps, context, access, request):
    common = dict(actor_agent_id=context.actor_agent_id, context=context,
        access=access,
        fresh_publications=deps.execution_fresh_publications,
        remote_ready=protocol_info()["remote_execution_ready"])
    resolved = resolve_execution_intent(deps.connection_factory, request=request, **common)
    view, reused = submit_execution_operation(deps.connection_factory,
        request={name: resolved[name] for name in
                 ("client_intent_id", "operation_id", "resolution_revision", "intent_hash")},
        **common)
    return {**view, "reused": reused}
