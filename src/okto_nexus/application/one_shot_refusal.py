"""Server-side no-send proof for a pool opening refused before Core admission."""


def opening_refused_before_core(conn, slot):
    # FAILED/NONE alone is insufficient: require the exact terminal opening
    # and its pre-send dispatch refusal, without any competing Core evidence.
    key = slot['server_id'], slot['executor_id'], slot['session_id'], slot['open_operation_id']
    return conn.execute(
        'SELECT 1 FROM execution_sessions s JOIN execution_operations o '
        'ON o.server_id=s.server_id AND o.executor_id=s.executor_id AND o.session_id=s.session_id '
        'AND o.operation_id=s.open_operation_id '
        'JOIN execution_dispatch_outbox d USING(server_id,executor_id,operation_id) '
        'WHERE s.server_id=? AND s.executor_id=? AND s.session_id=? AND s.open_operation_id=? '
        "AND s.lifecycle_state='FAILED' AND s.lease_state='NONE' AND s.stream_epoch IS NULL "
        "AND o.action='runtime.open' AND o.admission_state='RESOLVED_TERMINAL' "
        "AND d.dispatch_state='RESOLVED_TERMINAL' AND d.last_receipt_revision IS NULL "
        "AND json_extract(d.last_error,'$.operation_id')=o.operation_id "
        "AND json_extract(d.last_error,'$.stage')='dispatch' "
        "AND json_type(d.last_error,'$.possible_effect')='false' "
        'AND NOT EXISTS (SELECT 1 FROM execution_receipts r JOIN execution_operations ro '
        'USING(server_id,executor_id,operation_id) WHERE ro.server_id=s.server_id '
        'AND ro.executor_id=s.executor_id AND ro.session_id=s.session_id) '
        'AND NOT EXISTS (SELECT 1 FROM execution_local_publications p WHERE p.server_id=s.server_id '
        'AND p.executor_id=s.executor_id AND p.session_id=s.session_id)', key).fetchone() is not None
