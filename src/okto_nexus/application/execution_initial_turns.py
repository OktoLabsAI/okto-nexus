"""Durable start-prompt children, released only after canonical session readiness."""
import json
import secrets

from nexus_connector_core.protocol import canonical_json

from .execution_semantics import execution_intent_hash
from ..errors import ErrorCode, OktoNexusError


def plan_initial_turn(conn, *, resolved, text, actor_agent_id=None):
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
                  actor_agent_id or resolved["scope"]["agent_id"], resolved["client_intent_id"]))


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
        "intent_id,operation_id,resolution_revision,resolved_json,created_at,source_guard_digest,actor_guard_digest) "
        "VALUES (?,?,?,?,?,?,1,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'),?,?)",
        (server_id, actor_agent_id, child["client_intent_id"], child["intent_hash"],
         child["intent_id"], child["operation_id"], canonical_json(child).decode(), source["source_guard_digest"], source['actor_guard_digest']))
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


def settle_failed_initial_turns(conn, *, server_id, executor_id):
    """Resolve unsent children of failed openings; no executor receipt is invented."""
    children = conn.execute(
        "SELECT c.operation_id FROM execution_operations c "
        "JOIN execution_operations p ON p.server_id=c.server_id AND p.executor_id=c.executor_id "
        "AND p.operation_id=c.parent_operation_id "
        "JOIN execution_sessions s ON s.server_id=p.server_id AND s.executor_id=p.executor_id "
        "AND s.open_operation_id=p.operation_id AND s.session_id=c.session_id "
        "WHERE c.server_id=? AND c.executor_id=? AND c.action='turn.submit' "
        "AND c.admission_state='ACCEPTED' AND p.action='runtime.open' "
        "AND p.admission_state='RESOLVED_TERMINAL' AND s.lifecycle_state IN ('FAILED','CLOSED') "
        "AND s.lease_state IN ('NONE','CLOSED') "
        "AND NOT EXISTS (SELECT 1 FROM execution_dispatch_outbox d WHERE d.server_id=c.server_id "
        "AND d.executor_id=c.executor_id AND d.operation_id=c.operation_id) "
        "AND NOT EXISTS (SELECT 1 FROM execution_receipts r WHERE r.server_id=c.server_id "
        "AND r.executor_id=c.executor_id AND r.operation_id=c.operation_id)",
        (server_id, executor_id)).fetchall()
    for child in children:
        key = (server_id, executor_id, child['operation_id'])
        error = json.dumps(dict(code='INITIAL_OPEN_FAILED', stage='dispatch',
            message='The opening failed before its initial message was dispatched.',
            possible_effect=False, retry_safe=False, operation_id=child['operation_id']))
        conn.execute("INSERT INTO execution_dispatch_outbox(server_id,executor_id,operation_id,dispatch_state,last_error) "
                     "VALUES (?,?,?,'RESOLVED_TERMINAL',?)", (*key, error))
        conn.execute("UPDATE execution_operations SET admission_state='RESOLVED_TERMINAL' "
                     "WHERE server_id=? AND executor_id=? AND operation_id=?", key)
        conn.execute("INSERT INTO execution_unsent_dispatch_proofs(server_id,executor_id,operation_id,attempt_no,recorded_at) "
            "VALUES(?,?,?,0,strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT DO NOTHING", key)
        from .execution_delivery_retry import mark_unsent_closed_retry
        mark_unsent_closed_retry(conn, *key)


def settle_unsent_closed_session_operations(conn, *, server_id, executor_id, agent_id=None):
    """A proved closed session cannot execute its never-dispatched queue."""
    rows = conn.execute(
        "SELECT o.operation_id,d.attempt_no FROM execution_operations o "
        "JOIN execution_sessions s USING(server_id,executor_id,session_id) "
        "JOIN execution_dispatch_outbox d USING(server_id,executor_id,operation_id) "
        "WHERE o.server_id=? AND o.executor_id=? AND (? IS NULL OR o.subject_agent_id=?) "
        "AND s.lifecycle_state='CLOSED' AND s.lease_state='CLOSED' "
        "AND o.admission_state='ACCEPTED' AND d.dispatch_state='PENDING' "
        "AND (d.attempt_no=0 OR EXISTS (SELECT 1 FROM execution_unsent_dispatch_proofs f "
        "WHERE f.server_id=o.server_id AND f.executor_id=o.executor_id AND f.operation_id=o.operation_id "
        "AND f.attempt_no=d.attempt_no)) "
        "AND NOT EXISTS (SELECT 1 FROM execution_receipts r WHERE r.server_id=o.server_id "
        "AND r.executor_id=o.executor_id AND r.operation_id=o.operation_id) "
        "AND NOT EXISTS (SELECT 1 FROM execution_local_publications p WHERE p.server_id=o.server_id "
        "AND p.executor_id=o.executor_id AND p.operation_id=o.operation_id)",
        (server_id, executor_id, agent_id, agent_id)).fetchall()
    for row in rows:
        key = (server_id, executor_id, row['operation_id'])
        if row['attempt_no'] == 0:
            conn.execute("INSERT INTO execution_unsent_dispatch_proofs(server_id,executor_id,operation_id,attempt_no,recorded_at) "
                "VALUES(?,?,?,0,strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT DO NOTHING", key)
        error = json.dumps(dict(code='SESSION_CLOSED', stage='dispatch',
            message='The session closed before this operation was dispatched.',
            possible_effect=False, retry_safe=False, operation_id=row['operation_id']))
        conn.execute("UPDATE execution_dispatch_outbox SET dispatch_state='RESOLVED_TERMINAL',last_error=?,"
            "reserved_bytes=0,reservation_class=NULL,reserved_at=NULL "
            "WHERE server_id=? AND executor_id=? AND operation_id=?", (error, *key))
        conn.execute("UPDATE execution_operations SET admission_state='RESOLVED_TERMINAL' "
            "WHERE server_id=? AND executor_id=? AND operation_id=?", key)
        from .execution_delivery_retry import mark_unsent_closed_retry
        mark_unsent_closed_retry(conn, *key)


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
