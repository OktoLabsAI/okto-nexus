"""Conservative backlog conversion under the same writer as the send fence."""
import math


class SqliteHandoffNoticeRetirement:
    def __init__(self, *, cancellations, inbox, schedule, pool_factory):
        self.cancellations, self.inbox, self.schedule = cancellations, inbox, schedule
        self.pool_factory = pool_factory

    def retire_page(self, uow, *, now, limit):
        if type(limit) is not int or not 1 <= limit <= 256 or not math.isfinite(now):
            raise ValueError('Invalid notice retirement page.')
        conn = uow.connection
        cursor = conn.execute('SELECT notice_cursor FROM handoff_runtime_schedule_scan WHERE singleton=1').fetchone()[0]
        rows = conn.execute("SELECT d.*,n.handoff_id FROM runtime_handoff_notifications n "
            "JOIN delivery_outbox d USING(message_id) WHERE n.runtime_route='legacy_admitted' "
            "AND d.operation_id>? ORDER BY d.operation_id LIMIT ?", (cursor, limit)).fetchall()
        retired = 0
        for row in rows:
            if not self._unsent(conn, row):
                continue
            identity = row['operation_id']
            self.cancellations.cancel(uow, identity, code='COMPETITIVE_NOTICE_RETIRED', preserve_started_openings=True)
            conn.execute('INSERT INTO runtime_handoff_notice_retirements VALUES(?,?,?,?,?,?)',
                (identity, row['message_id'], 'system_migration', row['status'], 'competitive_notice_before_send', now))
            if conn.execute('SELECT 1 FROM one_shot_calls WHERE call_id=?', (identity,)).fetchone():
                # Finish the logical call; the existing pool owner still closes
                # any warm/native resource and proves disposal separately.
                self.pool_factory(conn).fail(request_id=identity, code='COMPETITIVE_NOTICE_RETIRED',
                    stage='dispatch', message='Competitive notice retired before execution.',
                    now=now, cancelled=True)
            conn.execute("UPDATE delivery_outbox SET status='CANCELLED',reason='competitive_notice_before_send' "
                         'WHERE operation_id=?', (identity,))
            # Release only this producer's ownership. No MCP read/ACK is made.
            self.inbox.release_runtime_reservation(uow, operation_id=identity)
            conn.execute("UPDATE runtime_pending_deliveries SET status='resolved',reason='competitive_handoff_control' "
                         "WHERE delivery_id=? AND status='waiting'", (row['delivery_id'],))
            conn.execute("UPDATE runtime_handoff_notifications SET runtime_route='competitive' WHERE message_id=?",
                         (row['message_id'],))
            self.schedule.notify(uow, handoff_id=row['handoff_id'], now=now)
            retired += 1
        # Rotate even across uncertain rows; they must not starve later safe work.
        conn.execute('UPDATE handoff_runtime_schedule_scan SET notice_cursor=? WHERE singleton=1',
                     (rows[-1]['operation_id'] if len(rows) == limit else '',))
        return retired

    @staticmethod
    def _unsent(conn, row):
        call = conn.execute('SELECT state,started_at,outcome_json FROM one_shot_calls WHERE call_id=?',
                            (row['operation_id'],)).fetchone()
        if call and (call['state'] not in {'QUEUED', 'ADMITTED'} or call['started_at'] is not None or call['outcome_json'] is not None):
            return False
        if (row['status'] not in ({'PENDING', 'CLAIMED', 'ACCEPTED'} if call else {'PENDING', 'CLAIMED'}) or row['ack_level'] != 'NONE'
                or any(row[field] is not None for field in ('reconciliation_id', 'terminal_event_id',
                    'canonical_terminal_operation_id', 'native_thread_id', 'native_turn_id', 'external_completed_at'))):
            return False
        identity = row['operation_id']
        for table, column in (('runtime_handoff_bindings', 'operation_id'), ('runtime_results', 'operation_id'),
                ('execution_delivery_attempt_history', 'domain_operation_id'),
                ('execution_unsent_delivery_history', 'domain_operation_id')):
            if conn.execute(f'SELECT 1 FROM {table} WHERE {column}=? LIMIT 1', (identity,)).fetchone():
                return False
        refs = conn.execute('SELECT p.action,p.admission_state,x.dispatch_state,x.last_receipt_revision, '
            'EXISTS(SELECT 1 FROM execution_receipts r WHERE r.server_id=p.server_id '
            'AND r.executor_id=p.executor_id AND r.operation_id=p.operation_id) AS has_receipt '
            'FROM execution_domain_deliveries m JOIN execution_operations p USING(server_id,executor_id,operation_id) '
            'LEFT JOIN execution_dispatch_outbox x USING(server_id,executor_id,operation_id) '
            'WHERE m.domain_operation_id=?', (identity,)).fetchall()
        if not refs:
            # An old attempt without canonical linkage cannot be inferred safe
            # merely from an acknowledgement level of NONE.
            return row['attempt_id'] is None and row['attempt_count'] == 0
        if any(ref['action'] not in {'runtime.open', 'turn.submit'} for ref in refs):
            return False
        turns = [ref for ref in refs if ref['action'] == 'turn.submit']
        # Starting a provider does not dispatch this notice. Preserve that
        # opening and its physical resource while fencing the unsent prompt.
        return bool(turns) and all(ref['admission_state'] in {'ACCEPTED', 'DISPATCH_PENDING'}
            and ref['dispatch_state'] in (None, 'PENDING', 'RESERVED')
            and ref['last_receipt_revision'] is None and not ref['has_receipt'] for ref in turns)
