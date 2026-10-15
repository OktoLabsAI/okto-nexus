"""Select active native handoff work without treating history as live work."""
import json

from ....application.execution_work_leases import RunningHandoff


class SqliteRunningHandoffRepository:
    def startup_deadline(self, uow, scope):
        row = uow.connection.execute(
            'SELECT c.admission_deadline,o.expected_revisions_json FROM one_shot_slots p '
            'JOIN one_shot_calls c ON c.call_id=p.call_id '
            'JOIN execution_capacity_admissions a ON a.domain_operation_id=c.call_id '
            'JOIN execution_operations o ON o.server_id=p.server_id AND o.executor_id=p.executor_id '
            'AND o.operation_id=p.open_operation_id AND o.session_id=p.session_id '
            "WHERE p.server_id=? AND p.executor_id=? AND p.session_id=? AND o.action='runtime.open' "
            'AND c.started_at IS NULL',
            (scope['server_id'], scope['executor_id'], scope['session_id'])).fetchone()
        if row is not None and json.loads(row['expected_revisions_json']) == scope:
            return row['admission_deadline']
        return None

    def running(self, uow, scope):
        rows = uow.connection.execute(
            "SELECT d.*,p.expected_revisions_json AS work_scope,b.claim_epoch AS work_epoch,"
            "h.claim_epoch AS current_epoch,h.status AS handoff_status,h.claimed_by AS claimant "
            "FROM execution_operations p "
            "JOIN execution_dispatch_outbox x USING(server_id,executor_id,operation_id) "
            "JOIN execution_domain_deliveries m USING(server_id,executor_id,operation_id) "
            "JOIN delivery_outbox d ON d.operation_id=m.domain_operation_id "
            "JOIN runtime_handoff_bindings b ON b.operation_id=d.operation_id "
            "LEFT JOIN handoffs h ON h.handoff_id=b.handoff_id AND h.workspace_id=d.workspace_id "
            "WHERE p.server_id=? AND p.executor_id=? AND p.session_id=? AND p.action='turn.submit' "
            "AND x.dispatch_state IN ('SENDING','DISPATCHED','RECONCILING') "
            "AND COALESCE("
            "(SELECT r.stage FROM execution_receipts r WHERE r.server_id=p.server_id "
            "AND r.executor_id=p.executor_id AND r.operation_id=p.operation_id "
            "ORDER BY r.receipt_revision DESC LIMIT 1) "
            "IN ('SUBMISSION_STARTED','SUBMITTED','RUNNING','OUTCOME_UNKNOWN'),"
            "x.dispatch_state IN ('SENDING','RECONCILING'))",
            (scope['server_id'], scope['executor_id'], scope['session_id'])).fetchall()
        return tuple(RunningHandoff(dict(row), row['work_epoch'], row['current_epoch'],
                                    row['handoff_status'], row['claimant'])
                     for row in rows if json.loads(row['work_scope']) == scope)
