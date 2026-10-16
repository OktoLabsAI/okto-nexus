"""Retire an uncertain close after independent session containment proof."""
import json


def settle_released_closes(conn, *, server_id, executor_id, session_id, proof):
    # The caller has validated Core ownership and drained the event stream.
    # This is not a successful close receipt: the original outcome stays unknown.
    rows = conn.execute(
        "SELECT o.operation_id FROM execution_operations o "
        "JOIN execution_sessions s USING(server_id,executor_id,session_id) "
        "JOIN execution_dispatch_outbox d USING(server_id,executor_id,operation_id) "
        "WHERE o.server_id=? AND o.executor_id=? AND o.session_id=? "
        "AND o.action='runtime.close' AND o.admission_state='RECONCILING' "
        "AND d.dispatch_state='RECONCILING' "
        "AND json_extract(d.last_error,'$.code')='DISPATCH_CONNECTION_LOST' "
        "AND s.lifecycle_state='CLOSED' AND s.lease_state='CLOSED' "
        "AND json_extract(o.expected_revisions_json,'$.session_owner_generation')=s.owner_generation "
        "AND NOT EXISTS(SELECT 1 FROM execution_receipts r WHERE r.server_id=o.server_id "
        "AND r.executor_id=o.executor_id AND r.operation_id=o.operation_id)",
        (server_id, executor_id, session_id)).fetchall()
    for row in rows:
        key = (server_id, executor_id, row['operation_id'])
        error = json.dumps(dict(code='CLOSE_OUTCOME_UNKNOWN_SESSION_RELEASED', stage='reconciliation',
            message='The close receipt was lost; independent containment proved the session stopped. The close outcome remains unknown.',
            possible_effect=True, retry_safe=False, operation_id=row['operation_id'], proof=proof), sort_keys=True)
        conn.execute("UPDATE execution_dispatch_outbox SET dispatch_state='RESOLVED_TERMINAL',last_error=?,"
            "reserved_bytes=0,reservation_class=NULL,reserved_at=NULL "
            "WHERE server_id=? AND executor_id=? AND operation_id=?", (error, *key))
        conn.execute("UPDATE execution_operations SET admission_state='RESOLVED_TERMINAL' "
            "WHERE server_id=? AND executor_id=? AND operation_id=?", key)
