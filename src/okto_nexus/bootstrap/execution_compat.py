"""Route existing harness session callers through canonical R4 admission."""
from nexus_connector_core import CoreError, validate_control_target

from ..adapters.outbound.execution.core_inventory import protocol_info
from ..adapters.outbound.sqlite.execution_identity import ensure_execution_installation
from ..application.execution_admission import submit_execution_operation
from ..application.execution_intents import resolve_execution_intent
from ..application.execution_session_views import read_execution_session
from ..errors import ErrorCode, OktoNexusError
from .execution_authority import build_execution_access


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
