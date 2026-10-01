"""Durable start-prompt children, released only after canonical session readiness."""
import json
import secrets

from nexus_connector_core.protocol import canonical_json

from .execution_semantics import execution_intent_hash
from ..errors import ErrorCode, OktoNexusError


def plan_initial_turn(conn, *, resolved, text):
    child = {**resolved, "operation_id": "op_" + secrets.token_hex(16),
             "client_intent_id": "initial_" + secrets.token_hex(16),
             "intent_id": "r4intent_" + secrets.token_hex(16), "reuse": False}
    child["semantic_intent"] = {**resolved["semantic_intent"], "action": "turn.submit",
                                "target": {"kind": "none", "expected_turn_id": None},
                                "payload": {"text": text}}
    child["intent_hash"] = execution_intent_hash(child["semantic_intent"])
    conn.execute("UPDATE execution_client_intents SET initial_turn_json=? WHERE server_id=? "
                 "AND actor_agent_id=? AND client_intent_id=?",
                 (canonical_json(child).decode(), resolved["scope"]["server_id"],
                  resolved["scope"]["agent_id"], resolved["client_intent_id"]))


def admit_initial_turn(conn, *, server_id, actor_agent_id, client_intent_id):
    source = conn.execute("SELECT * FROM execution_client_intents WHERE server_id=? "
                          "AND actor_agent_id=? AND client_intent_id=?",
                          (server_id, actor_agent_id, client_intent_id)).fetchone()
    if source["initial_turn_json"] is None:
        return
    child = json.loads(source["initial_turn_json"])
    scope = child["scope"]
    key = (server_id, scope["executor_id"], child["operation_id"])
    if conn.execute("SELECT 1 FROM execution_operations WHERE server_id=? AND executor_id=? "
                    "AND operation_id=?", key).fetchone():
        return
    from .execution_capacity import require_admission_capacity
    encoded_semantic = canonical_json(child["semantic_intent"])
    require_admission_capacity(conn, server_id=server_id, executor_id=scope["executor_id"],
                               action="turn.submit", byte_cost=len(encoded_semantic))
    conn.execute(
        "INSERT INTO execution_client_intents(server_id,actor_agent_id,client_intent_id,body_hash,"
        "intent_id,operation_id,resolution_revision,resolved_json,created_at,source_guard_digest) "
        "VALUES (?,?,?,?,?,?,1,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'),?)",
        (server_id, actor_agent_id, child["client_intent_id"], child["intent_hash"],
         child["intent_id"], child["operation_id"], canonical_json(child).decode(), source["source_guard_digest"]))
    conn.execute(
        "INSERT INTO execution_operations(server_id,executor_id,operation_id,subject_agent_id,"
        "actor_agent_id,binding_id,workspace_id,workspace_binding_id,session_id,action,intent_hash,"
        "semantic_payload,expected_revisions_json,delivery_id,admission_state,created_at,parent_operation_id,admission_bytes) "
        "VALUES (?,?,?,?,?,?,?,?,?,'turn.submit',?,?,?,?, 'ACCEPTED',strftime('%Y-%m-%dT%H:%M:%fZ','now'),?,?)",
        (*key, scope["agent_id"], actor_agent_id, scope["binding_id"], scope["workspace_id"],
         scope["workspace_binding_id"], scope["session_id"], child["intent_hash"],
         encoded_semantic.decode(), canonical_json(scope).decode(),
         "delivery_" + secrets.token_hex(16), source["operation_id"], len(encoded_semantic)))


def release_ready_initial_turns(conn, *, server_id, executor_id):
    # READY is projected only from an authenticated correlated opening receipt.
    # The existing pre-send path rechecks source authority, lease and generation.
    conn.execute(
        "INSERT INTO execution_dispatch_outbox(server_id,executor_id,operation_id,dispatch_state,next_attempt_at) "
        "SELECT p.server_id,p.executor_id,p.operation_id,'PENDING',NULL "
        "FROM execution_operations p JOIN execution_sessions s ON s.server_id=p.server_id "
        "AND s.executor_id=p.executor_id AND s.session_id=p.session_id "
        "AND s.open_operation_id=p.parent_operation_id "
        "WHERE p.server_id=? AND p.executor_id=? AND p.action='turn.submit' "
        "AND (SELECT r.stage FROM execution_receipts r WHERE r.server_id=p.server_id "
        "AND r.executor_id=p.executor_id AND r.operation_id=p.parent_operation_id "
        "ORDER BY r.receipt_revision DESC LIMIT 1) IN ('SUBMITTED','SUCCEEDED') "
        "AND p.admission_state='ACCEPTED' AND s.lifecycle_state='READY' AND s.lease_state='ACTIVE' "
        "AND NOT EXISTS (SELECT 1 FROM execution_dispatch_outbox o WHERE o.server_id=p.server_id "
        "AND o.executor_id=p.executor_id AND o.operation_id=p.operation_id)",
        (server_id, executor_id))


def require_current_parent_readiness(conn, *, server_id, executor_id, operation_id):
    child = conn.execute("SELECT parent_operation_id FROM execution_operations WHERE server_id=? "
                         "AND executor_id=? AND operation_id=?", (server_id, executor_id, operation_id)).fetchone()
    if child is None or child["parent_operation_id"] is None:
        return
    receipt = conn.execute("SELECT stage,native_id FROM execution_receipts WHERE server_id=? "
                           "AND executor_id=? AND operation_id=? ORDER BY receipt_revision DESC LIMIT 1",
                           (server_id, executor_id, child["parent_operation_id"])).fetchone()
    if receipt is None or receipt["stage"] not in {"SUBMITTED", "SUCCEEDED"} or not receipt["native_id"]:
        raise OktoNexusError(ErrorCode.CONFLICT, "The opening no longer proves readiness for its initial turn.", {})
