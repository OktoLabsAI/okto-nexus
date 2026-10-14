"""Atomic unsent cancellation; never invents executor receipts or stop proofs."""
import json

from ....errors import ErrorCode, OktoNexusError


class SqlitePendingExecutionCancellation:
    def cancel(self, uow, operation_id, *, code='OPERATOR_CANCELLED', preserve_started_openings=False):
        if code not in {'OPERATOR_CANCELLED', 'COMPETITIVE_NOTICE_RETIRED'}:
            raise ValueError('Unsupported pending cancellation cause.')
        conn = uow.connection
        rows = conn.execute(
            'SELECT p.server_id,p.executor_id,p.operation_id,p.action,p.admission_state,x.dispatch_state,x.last_receipt_revision, '
            'EXISTS(SELECT 1 FROM execution_receipts r WHERE r.server_id=p.server_id '
            'AND r.executor_id=p.executor_id AND r.operation_id=p.operation_id) AS has_receipt '
            'FROM execution_domain_deliveries m JOIN execution_operations p '
            'USING(server_id,executor_id,operation_id) LEFT JOIN execution_dispatch_outbox x '
            'USING(server_id,executor_id,operation_id) WHERE m.domain_operation_id=?',
            (operation_id,)).fetchall()
        # Validate the whole group before touching any row. The caller shares
        # this writer with its logical disposition and inbox ownership release.
        def unsent(row):
            return (row['dispatch_state'] in (None, 'PENDING', 'RESERVED')
                and row['admission_state'] in ('ACCEPTED', 'DISPATCH_PENDING')
                and row['last_receipt_revision'] is None and not row['has_receipt'])
        if preserve_started_openings:
            rows = [row for row in rows if row['action'] != 'runtime.open' or unsent(row)]
        if any(not unsent(row) for row in rows):
            raise OktoNexusError(ErrorCode.CONFLICT,
                'Canonical dispatch crossed its send fence; pending cancellation is unavailable.', {})
        for row in rows:
            key = (row['server_id'], row['executor_id'], row['operation_id'])
            error = json.dumps(dict(code=code, stage='dispatch',
                message='Cancelled before native dispatch.', possible_effect=False,
                retry_safe=False, operation_id=row['operation_id']))
            conn.execute("INSERT INTO execution_dispatch_outbox(server_id,executor_id,operation_id,dispatch_state,last_error) "
                "VALUES(?,?,?,'RESOLVED_TERMINAL',?) ON CONFLICT(server_id,executor_id,operation_id) DO UPDATE SET "
                "dispatch_state='RESOLVED_TERMINAL',last_error=excluded.last_error,"
                "reservation_class=NULL,reserved_bytes=0,reserved_at=NULL", (*key, error))
            conn.execute("UPDATE execution_operations SET admission_state='RESOLVED_TERMINAL' "
                "WHERE server_id=? AND executor_id=? AND operation_id=?", key)
            conn.execute("UPDATE execution_sessions SET lifecycle_state='FAILED',lease_state='CLOSED' WHERE server_id=? AND executor_id=? "
                "AND open_operation_id=? AND lifecycle_state='OPEN_PENDING' AND lease_state='NONE'", key)
