"""Durable bounded agenda; scheduling tokens grant no canonical claim rights."""
import json
import math
import uuid

from ....application.handoff_runtime_scheduler import HandoffScheduleLease, schedule_backoff


def arguments(now, limit):
    if (type(now) not in (float, int) or not math.isfinite(now) or now < 0
            or type(limit) is not int or not 1 <= limit <= 256):
        raise ValueError('Invalid schedule page bounds.')


class SqliteHandoffScheduleRepository:
    def wake(self, uow):
        uow.connection.execute('UPDATE handoff_runtime_schedule_scan SET wake_generation=wake_generation+1 WHERE singleton=1')

    def _ensure(self, conn, *, handoff_id, workspace_id, generation, now, notify=False):
        conn.execute('INSERT INTO handoff_runtime_schedule(handoff_id,claim_generation,workspace_id,state,due_at) '
            "VALUES(?,?,?,'PENDING',?) ON CONFLICT(handoff_id,claim_generation) DO NOTHING",
            (handoff_id, generation, workspace_id, now))
        if notify:
            conn.execute("UPDATE handoff_runtime_schedule SET state='PENDING',due_at=min(due_at,?),"
                'wake_revision=wake_revision+1 WHERE handoff_id=? AND claim_generation=?', (now, handoff_id, generation))
        else:
            # The fallback scan revives retired work only if canonical facts or
            # unresolved attempt records still require it. It never resets the
            # backoff of a pending row on each visit.
            conn.execute("UPDATE handoff_runtime_schedule SET state='PENDING',due_at=? "
                "WHERE handoff_id=? AND claim_generation=? AND state='IDLE'", (now, handoff_id, generation))

    def notify(self, uow, *, handoff_id, now):
        arguments(now, 1)
        row = uow.connection.execute('SELECT workspace_id,claim_epoch,status,target FROM handoffs WHERE handoff_id=?',
                                     (handoff_id,)).fetchone()
        try:
            competitive = bool(row and json.loads(row['target']).get('strategy') == 'broadcast')
        except (ValueError, TypeError, AttributeError):
            competitive = False
        if competitive:
            if row['status'] == 'OPEN':
                self._ensure(uow.connection, handoff_id=handoff_id, workspace_id=row['workspace_id'],
                             generation=row['claim_epoch'], now=now, notify=True)
            else:
                # Claim/cancellation wakes cleanup of the original generation,
                # not a new acquisition for the already owned/terminal work.
                uow.connection.execute("UPDATE handoff_runtime_schedule SET state='PENDING',due_at=min(due_at,?),"
                    "wake_revision=wake_revision+1 WHERE handoff_id=? AND EXISTS ("
                    "SELECT 1 FROM handoff_runtime_attempts a LEFT JOIN execution_capacity_admissions c "
                    "ON c.domain_operation_id=a.operation_id WHERE a.handoff_id=handoff_runtime_schedule.handoff_id "
                    "AND a.claim_generation=handoff_runtime_schedule.claim_generation AND a.active=1 "
                    "AND (a.operation_id IS NULL OR c.state IS NULL OR c.state<>'CONSUMED'))", (now, handoff_id))

    def sweep(self, uow, *, now, limit):
        arguments(now, limit)
        conn = uow.connection
        cursors = conn.execute('SELECT handoff_cursor,attempt_cursor FROM handoff_runtime_schedule_scan WHERE singleton=1').fetchone()
        rows = conn.execute('SELECT rowid AS scan_id,handoff_id,workspace_id,claim_epoch,status,target '
            "FROM handoffs WHERE rowid>? AND status='OPEN' AND "
            "CASE WHEN json_valid(target) THEN json_extract(target,'$.strategy') END='broadcast' "
            'ORDER BY rowid LIMIT ?', (cursors[0], limit)).fetchall()
        for row in rows:
            try:
                competitive = json.loads(row['target']).get('strategy') == 'broadcast'
            except (ValueError, TypeError, AttributeError):
                competitive = False
            if row['status'] == 'OPEN' and competitive:
                self._ensure(conn, handoff_id=row['handoff_id'], workspace_id=row['workspace_id'],
                             generation=row['claim_epoch'], now=now)
        pending = conn.execute('SELECT a.rowid AS scan_id,a.handoff_id,a.workspace_id,a.claim_generation,a.active,a.state,'
            'c.state AS capacity_state FROM handoff_runtime_attempts a LEFT JOIN execution_capacity_admissions c '
            "ON c.domain_operation_id=a.operation_id WHERE a.rowid>? AND a.active=1 "
            "AND (a.state<>'CLAIM_COMMITTED' OR c.state IS NULL OR c.state<>'CONSUMED') "
            'ORDER BY a.rowid LIMIT ?', (cursors[1], limit)).fetchall()
        for row in pending:
            if row['active'] and (row['state'] != 'CLAIM_COMMITTED' or row['capacity_state'] != 'CONSUMED'):
                self._ensure(conn, handoff_id=row['handoff_id'], workspace_id=row['workspace_id'],
                             generation=row['claim_generation'], now=now)
        conn.execute('UPDATE handoff_runtime_schedule_scan SET handoff_cursor=?,attempt_cursor=? WHERE singleton=1',
            (rows[-1]['scan_id'] if len(rows) == limit else 0, pending[-1]['scan_id'] if len(pending) == limit else 0))
        return len(rows), len(pending)

    def lease_due(self, uow, *, now, limit, lease_seconds):
        arguments(now, limit)
        if type(lease_seconds) not in (float, int) or not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError('Invalid schedule lease.')
        conn = uow.connection
        generation = conn.execute('SELECT wake_generation FROM handoff_runtime_schedule_scan WHERE singleton=1').fetchone()[0]
        rows = conn.execute("SELECT * FROM handoff_runtime_schedule WHERE state='PENDING' AND lease_until<=? "
            'AND (due_at<=? OR seen_wake_generation<?) ORDER BY due_at,handoff_id,claim_generation LIMIT ?',
            (now, now, generation, limit)).fetchall()
        result = []
        for row in rows:
            token = uuid.uuid4().hex
            conn.execute('UPDATE handoff_runtime_schedule SET lease_token=?,lease_until=? '
                'WHERE handoff_id=? AND claim_generation=?', (token, now + lease_seconds, row['handoff_id'], row['claim_generation']))
            result.append(HandoffScheduleLease(row['handoff_id'], row['workspace_id'], row['claim_generation'],
                token, row['wake_revision'], generation, row['candidate_cursor']))
        return tuple(result)

    def renew(self, uow, lease, *, now, lease_seconds):
        arguments(now, 1)
        # Even after expiry the same token can renew if no other scanner took
        # it. Replacement changes the token and makes this update a no-op.
        return bool(uow.connection.execute('UPDATE handoff_runtime_schedule SET lease_until=? '
            "WHERE handoff_id=? AND claim_generation=? AND lease_token=? AND state='PENDING'",
            (now + lease_seconds, lease.handoff_id, lease.claim_generation, lease.token)).rowcount)

    def finish(self, uow, lease, outcome, *, now):
        arguments(now, 1)
        conn = uow.connection
        row = conn.execute('SELECT * FROM handoff_runtime_schedule WHERE handoff_id=? AND claim_generation=? AND lease_token=?',
                           (lease.handoff_id, lease.claim_generation, lease.token)).fetchone()
        if row is None:
            return False
        count = min(row['backoff_count'] + 1, 8) if row['reason'] == outcome.reason else 1
        notified = row['wake_revision'] != lease.wake_revision
        due = now if notified else now + schedule_backoff(outcome.reason, count)
        conn.execute('UPDATE handoff_runtime_schedule SET state=?,due_at=?,reason=?,backoff_count=?,candidate_cursor=?,'
            'seen_wake_generation=?,lease_token=NULL,lease_until=0 WHERE handoff_id=? AND claim_generation=? AND lease_token=?',
            ('IDLE' if outcome.done and not notified else 'PENDING', due, outcome.reason, count,
             outcome.candidate_cursor, lease.wake_generation, lease.handoff_id, lease.claim_generation, lease.token))
        return True
