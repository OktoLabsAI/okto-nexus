"""Retry logical conversations only after authenticated durable no-effect proof."""
import json

from ..domain.base import iso_plus, utc_now_iso
from ..errors import OktoNexusError
from .runtime_policy import defaults


def no_effect_receipt(conn, domain_operation_id):
    return conn.execute(
        "SELECT r.* FROM execution_domain_deliveries m "
        "JOIN execution_operations p USING(server_id,executor_id,operation_id) "
        "JOIN execution_receipts r USING(server_id,executor_id,operation_id) "
        "WHERE m.domain_operation_id=? AND p.action='turn.submit' "
        "AND r.receipt_revision=(SELECT max(latest.receipt_revision) FROM execution_receipts latest "
        "WHERE latest.server_id=r.server_id AND latest.executor_id=r.executor_id AND latest.operation_id=r.operation_id) "
        "AND r.stage='FAILED' AND r.possible_effect=0 AND r.retry_safe=1 "
        "AND NOT EXISTS (SELECT 1 FROM execution_results result WHERE result.server_id=r.server_id "
        "AND result.executor_id=r.executor_id AND result.operation_id=r.operation_id) LIMIT 1",
        (domain_operation_id,)).fetchone()


def unsent_closed_proof(conn, domain_operation_id):
    return conn.execute("SELECT f.*,p.parent_operation_id,json_extract(d.last_error,'$.code') AS reason "
        "FROM execution_domain_deliveries m "
        "JOIN execution_operations p USING(server_id,executor_id,operation_id) "
        "JOIN execution_dispatch_outbox d USING(server_id,executor_id,operation_id) "
        "JOIN execution_unsent_dispatch_proofs f USING(server_id,executor_id,operation_id,attempt_no) "
        "JOIN execution_sessions s ON s.server_id=p.server_id AND s.executor_id=p.executor_id AND s.session_id=p.session_id "
        "WHERE m.domain_operation_id=? AND p.action='turn.submit' AND p.admission_state='RESOLVED_TERMINAL' "
        "AND d.dispatch_state='RESOLVED_TERMINAL' "
        "AND ((json_extract(d.last_error,'$.code')='SESSION_CLOSED' AND s.lifecycle_state='CLOSED' AND s.lease_state='CLOSED') "
        "OR (json_extract(d.last_error,'$.code')='INITIAL_OPEN_FAILED' AND s.lifecycle_state IN ('CLOSED','FAILED') "
        "AND s.lease_state IN ('NONE','CLOSED'))) "
        "AND NOT EXISTS (SELECT 1 FROM execution_receipts r WHERE r.server_id=p.server_id AND r.executor_id=p.executor_id AND r.operation_id=p.operation_id) "
        "AND NOT EXISTS (SELECT 1 FROM execution_local_publications r WHERE r.server_id=p.server_id AND r.executor_id=p.executor_id AND r.operation_id=p.operation_id) "
        "AND NOT EXISTS (SELECT 1 FROM execution_results r WHERE r.server_id=p.server_id AND r.executor_id=p.executor_id AND r.operation_id=p.operation_id)",
        (domain_operation_id,)).fetchone()


def mark_unsent_closed_retry(conn, server_id, executor_id, operation_id):
    """A fenced pre-send reservation may retry the same logical conversation."""
    row = conn.execute('SELECT d.* FROM execution_domain_deliveries m JOIN delivery_outbox d '
        'ON d.operation_id=m.domain_operation_id WHERE m.server_id=? AND m.executor_id=? AND m.operation_id=?',
        (server_id, executor_id, operation_id)).fetchone()
    if (row is None or row['status'] not in ('PENDING', 'CLAIMED', 'FAILED_FINAL') or row['ack_level'] != 'NONE'
            or row['reconciliation_id'] or row['terminal_event_id']
            or row['external_completed_at'] or not defaults(conn)['automatic_recovery']):
        return
    envelope = json.loads(row['envelope'])
    proof = unsent_closed_proof(conn, row['operation_id'])
    if (envelope.get('intent') != 'conversation' or envelope.get('handoff_id')
            or proof is None or (row['canonical_terminal_operation_id'] is not None
                and row['canonical_terminal_operation_id'] != proof['parent_operation_id'])):
        return
    conn.execute("UPDATE delivery_outbox SET status='RETRY_WAIT',reason='host_dispatch_not_started',"
        "canonical_terminal_operation_id=?,next_attempt_at=?,retry_basis='HOST_NO_SEND' WHERE operation_id=?",
        (operation_id, utc_now_iso(), row['operation_id']))


def mark_retry_wait(conn, domain_operation_id):
    """Retain lane ordering as soon as the authenticated refusal commits."""
    row = conn.execute('SELECT * FROM delivery_outbox WHERE operation_id=?', (domain_operation_id,)).fetchone()
    if (row is None or row['status'] != 'FAILED_FINAL' or row['ack_level'] != 'NONE'
            or row['reconciliation_id'] or row['terminal_event_id'] or row['external_completed_at']
            or row['source_result_id']
            or not defaults(conn)['automatic_recovery']):
        return
    envelope = json.loads(row['envelope'])
    if (envelope.get('intent') != 'conversation' or envelope.get('handoff_id')
            or no_effect_receipt(conn, domain_operation_id) is None):
        return
    # A continuation may retry its original binding after durable no-write
    # proof. Endpoint selection still forbids moving that context elsewhere;
    # result relays and managed work remain excluded above.
    # A terminal receipt belongs to one immutable attempt. It must never be
    # changed back to pending or reused as the new Core operation identity.
    conn.execute("UPDATE delivery_outbox SET status='RETRY_WAIT',reason='canonical_no_effect',"
        "next_attempt_at=?,retry_basis='CORE_NO_EFFECT' WHERE operation_id=?",
        (iso_plus(utc_now_iso(), 2 ** max(0, row['attempt_count'] - 1)), domain_operation_id))


def prepare_retries(uow, owner, now):
    """Owner-fenced, bounded transaction; no runtime calls or network waits."""
    conn = uow.connection
    if not defaults(conn)['automatic_recovery']:
        return
    rows = conn.execute("SELECT * FROM delivery_outbox WHERE status='RETRY_WAIT' "
        "AND reason IN ('canonical_no_effect','host_dispatch_not_started') AND reconciliation_id IS NULL "
        "ORDER BY created_at,operation_id LIMIT 32").fetchall()
    for raw in rows:
        operation = dict(raw)
        host_proof = operation['reason'] == 'host_dispatch_not_started'
        proof = (unsent_closed_proof if host_proof else no_effect_receipt)(conn, operation['operation_id'])
        if proof is None:
            continue
        try:
            owner.validate(uow, operation)
            fallback_allowed = not host_proof or proof['reason'] == 'INITIAL_OPEN_FAILED'
            fallback = owner.select_fallback(uow, operation) if fallback_allowed and owner.select_fallback and operation['attempt_count'] < 3 else None
        except OktoNexusError:
            conn.execute("UPDATE delivery_outbox SET status='REJECTED',reason='authorization_changed',"
                "next_attempt_at=NULL WHERE operation_id=?", (operation['operation_id'],))
            continue
        history = 'execution_unsent_delivery_history' if host_proof else 'execution_delivery_attempt_history'
        conn.execute('INSERT INTO ' + history + ' '
            'SELECT server_id,executor_id,operation_id,domain_operation_id,?,?,?,?,? '
            'FROM execution_domain_deliveries WHERE domain_operation_id=?',
            (operation['attempt_count'], operation['endpoint_id'], proof['operation_id'],
             proof['attempt_no'] if host_proof else proof['receipt_revision'], now, operation['operation_id']))
        conn.execute('DELETE FROM execution_domain_deliveries WHERE domain_operation_id=?', (operation['operation_id'],))
        conn.execute("UPDATE delivery_outbox SET canonical_terminal_operation_id=NULL,"
            "reason='native_write_not_started',next_binding=?,admission_binding=COALESCE(admission_binding,?),"
            "attempt_id=?,retry_basis=?,status=CASE WHEN attempt_count>=3 THEN 'REJECTED' ELSE status END,"
            "next_attempt_at=CASE WHEN attempt_count>=3 THEN NULL ELSE next_attempt_at END WHERE operation_id=?",
            (json.dumps(fallback, sort_keys=True) if fallback else None,
             json.dumps(fallback['admission'], sort_keys=True) if fallback else None,
             proof['operation_id'],
             'HOST_NO_SEND' if host_proof else ('APPROVED_ENDPOINT_BEFORE_WRITE' if fallback else 'CORE_NO_EFFECT'), operation['operation_id']))
