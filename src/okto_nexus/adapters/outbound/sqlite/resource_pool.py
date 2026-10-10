"""Internal durable pool and FIFO queue adapters.

The existing tables are retained for upgrade compatibility. Their agent and
executor keys implement the generic pool/host identities. Connection ownership
and BEGIN IMMEDIATE belong to the Nexus unit of work, never to this adapter.
"""
import json

from ....domain.resource_pool import PoolInstance, PoolPolicy, PoolRequest


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def request(row):
    if row is None:
        return None
    return PoolRequest(row['call_id'], row['agent_id'], row['executor_id'], row['caller_id'],
        row['request_hash'], row['configuration_digest'], PoolPolicy(**json.loads(row['policy_json'])),
        row['state'], row['enqueued_at'], row['queue_deadline'], row['started_at'],
        row['execution_deadline'], row['admission_deadline'],
        json.loads(row['outcome_json']) if row['outcome_json'] is not None else None)


def instance(row):
    if row is None:
        return None
    return PoolInstance(row['slot_id'], row['agent_id'], row['executor_id'], row['configuration_digest'],
                        row['state'], row['created_at'], row['call_id'], row['session_id'])


def scope(pool_id=None, host_id=None):
    filters, args = [], []
    if pool_id is not None:
        filters.append('agent_id=?')
        args.append(pool_id)
    if host_id is not None:
        filters.append('executor_id=?')
        args.append(host_id)
    return ' AND '.join(filters) or '1', args


class SQLiteRequestQueue:
    def __init__(self, conn):
        self.conn = conn

    def get(self, request_id):
        return request(self.conn.execute('SELECT * FROM one_shot_calls WHERE call_id=?', (request_id,)).fetchone())

    def add(self, row):
        self.conn.execute('INSERT INTO one_shot_calls(call_id,agent_id,executor_id,caller_id,request_hash,'
            'configuration_digest,policy_json,state,enqueued_at,queue_deadline) VALUES(?,?,?,?,?,?,?,?,?,?)',
            (row.request_id, row.pool_id, row.host_id, row.caller_id, row.request_hash, row.configuration,
             encode(row.policy.to_dict()), row.state, row.enqueued_at, row.queue_deadline))

    def save(self, row):
        self.conn.execute('UPDATE one_shot_calls SET state=?,started_at=?,execution_deadline=?,admission_deadline=?,'
            'outcome_json=? WHERE call_id=?', (row.state, row.started_at, row.execution_deadline,
            row.admission_deadline, encode(row.outcome) if row.outcome is not None else None, row.request_id))

    def waiting(self, *, host_id, limit):
        # Interleave pools before taking a bounded page; FIFO remains strict
        # within each pool. A saturated pool cannot hide all other pools.
        return [request(r) for r in self.conn.execute("SELECT * FROM (SELECT *, ROW_NUMBER() OVER "
            "(PARTITION BY agent_id ORDER BY enqueued_at,call_id) AS ordinal FROM one_shot_calls "
            "WHERE executor_id=? AND (state='QUEUED' OR (state='ADMITTED' AND NOT EXISTS "
            "(SELECT 1 FROM one_shot_slots p WHERE p.call_id=one_shot_calls.call_id)))) "
            "ORDER BY ordinal,enqueued_at,call_id LIMIT ?", (host_id, limit))]

    def preparing_count(self, *, pool_id, host_id=None, configuration=None):
        where, args = scope(pool_id, host_id)
        if configuration is not None:
            where += ' AND configuration_digest=?'
            args.append(configuration)
        return self.conn.execute("SELECT count(*) FROM one_shot_calls WHERE state='ADMITTED' AND "
            "NOT EXISTS (SELECT 1 FROM one_shot_slots p WHERE p.call_id=one_shot_calls.call_id) AND "
            + where, args).fetchone()[0]

    def waiting_count(self, *, pool_id=None, host_id=None):
        where, args = scope(pool_id, host_id)
        return self.conn.execute("SELECT count(*) FROM one_shot_calls WHERE state='QUEUED' AND " + where, args).fetchone()[0]

    def expired(self, *, host_id, now, limit):
        return [request(r) for r in self.conn.execute("SELECT * FROM one_shot_calls WHERE executor_id=? "
            "AND state='QUEUED' AND queue_deadline<=? ORDER BY queue_deadline,call_id LIMIT ?", (host_id, now, limit))]

    def timed_out(self, *, host_id, now, limit):
        return [request(r) for r in self.conn.execute("SELECT * FROM one_shot_calls WHERE executor_id=? AND "
            "((state='RUNNING' AND execution_deadline<=?) OR (state='ADMITTED' AND admission_deadline<=?)) "
            "ORDER BY enqueued_at,call_id LIMIT ?", (host_id, now, now, limit))]

    def outcomes(self, *, caller_id, limit=100):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Invalid outcome page size.')
        return [json.loads(r[0]) for r in self.conn.execute('SELECT outcome_json FROM one_shot_calls WHERE caller_id=? '
            'AND outcome_json IS NOT NULL AND outcome_delivered_at IS NULL ORDER BY enqueued_at,call_id LIMIT ?', (caller_id, limit))]

    def acknowledge(self, *, caller_id, request_id, now):
        return bool(self.conn.execute('UPDATE one_shot_calls SET outcome_delivered_at=coalesce(outcome_delivered_at,?) '
            'WHERE caller_id=? AND call_id=? AND outcome_json IS NOT NULL', (now, caller_id, request_id)).rowcount)


class SQLiteInstancePool:
    def __init__(self, conn):
        self.conn = conn

    def get(self, instance_id):
        return instance(self.conn.execute('SELECT * FROM one_shot_slots WHERE slot_id=?', (instance_id,)).fetchone())

    def for_request(self, request_id):
        return instance(self.conn.execute('SELECT * FROM one_shot_slots WHERE call_id=?', (request_id,)).fetchone())

    def add(self, row):
        self.conn.execute('INSERT INTO one_shot_slots(slot_id,executor_id,agent_id,configuration_digest,state,call_id,created_at) '
            'VALUES(?,?,?,?,?,?,?)', (row.instance_id, row.host_id, row.pool_id, row.configuration, row.state, row.request_id, row.created_at))

    def save(self, row):
        self.conn.execute('UPDATE one_shot_slots SET state=?,call_id=?,session_id=? WHERE slot_id=?',
                          (row.state, row.request_id, row.resource_id, row.instance_id))

    def remove(self, instance_id):
        self.conn.execute('DELETE FROM one_shot_slots WHERE slot_id=?', (instance_id,))

    def count(self, *, pool_id=None, host_id=None):
        where, args = scope(pool_id, host_id)
        return self.conn.execute('SELECT count(*) FROM one_shot_slots WHERE ' + where, args).fetchone()[0]

    def warm(self, *, pool_id, host_id, configuration):
        return instance(self.conn.execute("SELECT * FROM one_shot_slots WHERE executor_id=? AND agent_id=? AND state='WARM' "
            'AND configuration_digest=? ORDER BY created_at,slot_id LIMIT 1', (host_id, pool_id, configuration)).fetchone())

    def idle(self, *, pool_id):
        return [instance(r) for r in self.conn.execute("SELECT * FROM one_shot_slots WHERE agent_id=? "
            "AND call_id IS NULL AND state IN ('STARTING','WARM') ORDER BY created_at DESC,slot_id DESC", (pool_id,))]

    def incompatible(self, *, pool_id, host_id, configuration, binding_id=None):
        params = (pool_id, host_id, configuration)
        extra = ''
        if binding_id is not None:
            extra = ' AND binding_id=?'
            params += (binding_id,)
        return [instance(r) for r in self.conn.execute("SELECT * FROM one_shot_slots WHERE agent_id=? AND executor_id=? "
            "AND call_id IS NULL AND state IN ('STARTING','WARM') AND configuration_digest<>?" + extra, params)]

    def states(self, *, pool_id, host_id):
        return dict(self.conn.execute('SELECT state,count(*) FROM one_shot_slots WHERE executor_id=? AND agent_id=? GROUP BY state',
                                      (host_id, pool_id)).fetchall())

    def closing_count(self, *, pool_id):
        return self.conn.execute("SELECT count(*) FROM one_shot_slots WHERE agent_id=? AND state='CLOSING'", (pool_id,)).fetchone()[0]


class SQLitePoolTransaction:
    def __init__(self, conn):
        self.conn = conn
        self.requests = SQLiteRequestQueue(conn)
        self.instances = SQLiteInstancePool(conn)

    def require_write(self):
        if not self.conn.in_transaction:
            raise RuntimeError('Pool mutations require a serializable write transaction.')

    def policy(self, pool_id):
        base = json.loads(self.conn.execute("SELECT policy_json FROM one_shot_policy_settings WHERE scope='global'").fetchone()[0])
        row = self.conn.execute('SELECT policy_json FROM one_shot_policy_settings WHERE scope=?', ('agent:' + pool_id,)).fetchone()
        if row:
            base.update(json.loads(row[0]))
        return PoolPolicy(**base)

    def backoff(self, *, pool_id, host_id):
        row = self.conn.execute('SELECT failures,next_attempt_at FROM one_shot_warm_backoff WHERE executor_id=? AND agent_id=?',
                                (host_id, pool_id)).fetchone()
        return tuple(row) if row else (0, 0)

    def save_backoff(self, *, pool_id, host_id, failures, until):
        self.conn.execute('INSERT INTO one_shot_warm_backoff VALUES(?,?,?,?) ON CONFLICT(executor_id,agent_id) DO UPDATE SET '
            'failures=excluded.failures,next_attempt_at=excluded.next_attempt_at', (host_id, pool_id, failures, until))

    def clear_backoff(self, *, pool_id, host_id):
        self.conn.execute('DELETE FROM one_shot_warm_backoff WHERE executor_id=? AND agent_id=?', (host_id, pool_id))
