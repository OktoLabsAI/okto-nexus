"""Reuse only the established opening under its still-applied authority."""
import json
import time
from datetime import datetime, timezone

from ..errors import ErrorCode, OktoNexusError
from .execution_capabilities import ExecutionCapabilityService
from .execution_semantics import execution_intent_hash


def reusable_opening(uow, *, factory, access, context, server_id, executor_id,
                     binding_id, session_id=None, payload=None, fresh_publications=None):
    if access is None or context is None:
        raise OktoNexusError(ErrorCode.CONFLICT, "Session reuse authorization is unavailable.", {})
    access.authenticate(context, uow=uow, require_feature=False)
    conn = uow.connection
    rows = conn.execute(
        "SELECT s.*,o.expected_revisions_json,o.semantic_payload,o.intent_hash "
        "FROM execution_sessions s JOIN execution_operations o ON o.server_id=s.server_id "
        "AND o.executor_id=s.executor_id AND o.operation_id=s.open_operation_id "
        "WHERE s.server_id=? AND s.executor_id=? AND s.binding_id=? "
        "AND s.lifecycle_state NOT IN ('CLOSED','FAILED') AND s.lease_state<>'REVOKED' "
        "AND (? IS NULL OR s.session_id=?) LIMIT 2",
        (server_id, executor_id, binding_id, session_id, session_id)).fetchall()
    if not rows:
        if session_id is not None:
            raise OktoNexusError(ErrorCode.CONFLICT, "The selected session is not reusable.", {})
        return None
    if len(rows) != 1:
        raise OktoNexusError(ErrorCode.CONFLICT, "Session selection is ambiguous; select a session or request a new one.", {})
    session = rows[0]
    scope = json.loads(session["expected_revisions_json"])
    semantic = json.loads(session["semantic_payload"])
    from .execution_operator_authority import require_operator_request
    require_operator_request(uow, actor=context.actor_agent_id, subject=scope['agent_id'],
                             access=access, context=context)
    if (session["lifecycle_state"] != "READY" or session["lease_state"] != "ACTIVE"
            or semantic["action"] != "runtime.open"
            or execution_intent_hash(semantic) != session["intent_hash"]
            or (payload is not None and semantic["payload"] != payload)):
        raise OktoNexusError(ErrorCode.CONFLICT, "The existing opening is unresolved or incompatible.", {})
    service = ExecutionCapabilityService(factory=factory, access=access)
    lease = service.repo.effective(uow, scope)
    if (lease is None or lease["status"] != "ACTIVE" or lease["applied_at"] is None
            or "runtime.open" not in json.loads(lease["allowed_actions_json"])
            or json.loads(lease["scope_json"]) != scope
            or datetime.fromisoformat(lease["valid_until_server"].replace("Z", "+00:00")) <= datetime.now(timezone.utc)):
        raise OktoNexusError(ErrorCode.CONFLICT, "An applied current lease is required for session reuse.", {})
    authority, grant = service._authority(uow, scope, grant_id=lease["grant_id"],
                                         grant_revision=lease["source_grant_revision"])
    if (authority["control_state"] != "CONTROL_READY"
            or authority["generation"] != lease["connection_generation"]
            or authority["owner_instance_id"] != lease["connection_id"]):
        raise OktoNexusError(ErrorCode.CONFLICT, "The session connection requires reconciliation.", {})
    current = service.repo.inventory(uow, scope)
    fresh = (fresh_publications or {}).get((server_id, executor_id))
    from .execution_inventory_revalidation import accepts_binding
    if (current is None or fresh is None
            or authority['inventory_revision'] != semantic['payload']['inventory_revision']
            or not accepts_binding(conn, authority, current['inventory_revision'], server_id, executor_id)
            or fresh[0] != current["publication_sequence"]
            or current["observation_age_ms"] + max(0, int((time.monotonic() - fresh[1]) * 1000)) >= 120_000):
        raise OktoNexusError(ErrorCode.CONFLICT, "The reusable installation inventory is no longer fresh.", {})
    if any(semantic["payload"][name] != authority[name] for name in
           ("candidate_ref", "realization_revision")):
        raise OktoNexusError(ErrorCode.CONFLICT, "The reusable realization has changed.", {})
    if conn.execute(
        "SELECT 1 FROM execution_operations WHERE server_id=? AND executor_id=? AND session_id=? "
        "AND action='runtime.close' LIMIT 1", (server_id, executor_id, session["session_id"])).fetchone():
        raise OktoNexusError(ErrorCode.CONFLICT, "The session has a pending close intent.", {})
    return dict(operation_id=session["open_operation_id"], session_id=session["session_id"],
                scope=scope, semantic_intent=semantic, intent_hash=session["intent_hash"])
