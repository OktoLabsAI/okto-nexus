from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3

import pytest

from okto_nexus.application import one_shot_capacity as capacity
from okto_nexus.errors import OktoNexusError


def database(path=':memory:'):
    conn = sqlite3.connect(path, isolation_level=None, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def initialize(conn):
    conn.executescript('CREATE TABLE agents(agent_id TEXT PRIMARY KEY); '
        "INSERT INTO agents VALUES('agent'),('other'); CREATE TABLE agent_endpoints(endpoint_id TEXT PRIMARY KEY);")
    migration = Path(__file__).parents[2] / 'src/okto_nexus/migrations/126_one_shot_capacity.sql'
    conn.executescript(migration.read_text())


@pytest.fixture
def conn():
    result = database()
    initialize(result)
    result.execute('BEGIN IMMEDIATE')
    yield result
    result.close()


def configure(conn, **changes):
    settings = capacity.policy(conn, 'agent').to_dict() | changes
    conn.execute("UPDATE one_shot_policy_settings SET policy_json=? WHERE scope='global'", (json.dumps(settings),))


def call(conn, identity='call', **kwargs):
    return capacity.admit(conn, **(dict(call_id=identity, agent_id='agent', executor_id='host',
        caller_id='caller', request_hash=identity, configuration_digest='config', host_limit=10, now=10) | kwargs))


def slot(conn, call_id):
    return dict(conn.execute('SELECT * FROM one_shot_slots WHERE call_id=?', (call_id,)).fetchone())


def run(conn, identity='call'):
    resource = conn.execute("SELECT * FROM one_shot_slots WHERE call_id IS NULL AND state='STARTING' "
                            'ORDER BY created_at,slot_id LIMIT 1').fetchone()
    capacity.ready(conn, slot_id=resource['slot_id'], session_id='session-' + identity)
    capacity.advance_queue(conn, executor_id='host', host_limit=10, now=11)
    capacity.started(conn, call_id=identity, now=11)


def test_ten_parallel_and_five_warm_share_capacity(conn):
    configure(conn, max_parallel=10, warm_instances=5)
    for n in range(5):
        warm = capacity.reserve_warm(conn, agent_id='agent', executor_id='host', configuration_digest='config', host_limit=10, now=n)
        capacity.ready(conn, slot_id=warm, session_id=f'warm-{n}')
    assert capacity.reserve_warm(conn, agent_id='agent', executor_id='host', configuration_digest='config', host_limit=10, now=6) is None
    for n in range(10):
        assert call(conn, f'call-{n}')['state'] == 'ADMITTED'
    assert conn.execute('SELECT count(*) FROM one_shot_slots').fetchone()[0] == 10
    assert conn.execute("SELECT count(*) FROM one_shot_slots WHERE state='CLAIMED'").fetchone()[0] == 5
    assert call(conn, 'overflow')['state'] == 'QUEUED'


def test_agent_parallel_budget_is_shared_across_hosts(conn):
    configure(conn, max_parallel=2, warm_instances=0, queue_capacity=1)
    assert call(conn, 'local', executor_id='local')['state'] == 'ADMITTED'
    assert call(conn, 'remote', executor_id='remote')['state'] == 'ADMITTED'
    assert call(conn, 'queued-local', executor_id='local')['state'] == 'QUEUED'
    assert call(conn, 'rejected-remote', executor_id='remote')['state'] == 'FAILED'


def test_unlimited_pool_still_respects_host_capacity_and_release(conn):
    configure(conn, max_parallel=0, warm_instances=4)
    for n in range(10):
        assert call(conn, f'call-{n}')['state'] == 'ADMITTED'
    assert call(conn, 'waiting')['state'] == 'QUEUED'
    run(conn, 'call-0')
    capacity.finish(conn, call_id='call-0', outcome={'response': 'done'}, now=12)
    assert capacity.advance_queue(conn, executor_id='host', host_limit=10, now=13) == []
    assert capacity.dispose_confirmed(conn, slot_id=slot(conn, 'call-0')['slot_id'], session_id='session-call-0')
    assert capacity.advance_queue(conn, executor_id='host', host_limit=10, now=14) == ['waiting']


def test_blocked_pool_does_not_hide_another_queue(conn):
    configure(conn, max_parallel=1, queue_capacity=2000)
    call(conn, 'occupant')
    for n in range(1050):
        call(conn, f'waiting-{n}', now=11)
    # Enqueue another pool while the host is full, then restore host room.
    assert call(conn, 'other-request', agent_id='other', host_limit=1, now=12)['state'] == 'QUEUED'
    assert capacity.advance_queue(conn, executor_id='host', host_limit=10, now=13) == ['other-request']


def test_idempotency_uses_no_extra_slot_and_rejects_other_payload(conn):
    first = call(conn)
    assert call(conn, configuration_digest='new-config') == first
    assert conn.execute('SELECT count(*) FROM one_shot_slots').fetchone()[0] == 1
    with pytest.raises(OktoNexusError):
        call(conn, request_hash='changed')


def test_reject_excess_is_durable_for_caller(conn):
    configure(conn, overflow='reject')
    call(conn, 'first')
    assert call(conn, 'second')['state'] == 'FAILED'
    result = capacity.pending_outcomes(conn, caller_id='caller')[0]
    assert result['error']['code'] == 'ONE_SHOT_CAPACITY_EXCEEDED'
    assert result['error']['retry_safe'] and not result['error']['execution_started']
    assert capacity.pending_outcomes(conn, caller_id='another') == []


def test_bounded_fifo_and_expiry(conn):
    configure(conn, queue_capacity=1, queue_timeout_seconds=5)
    call(conn, 'first')
    assert call(conn, 'second')['state'] == 'QUEUED'
    assert call(conn, 'third')['state'] == 'FAILED'
    assert capacity.advance_queue(conn, executor_id='host', host_limit=10, now=15) == []
    result = capacity.pending_outcomes(conn, caller_id='caller')
    assert next(v for v in result if v['call_id'] == 'second')['error']['code'] == 'ONE_SHOT_QUEUE_EXPIRED'


def test_success_persisted_before_resource_release(conn):
    call(conn)
    run(conn)
    resource = slot(conn, 'call')
    success = capacity.finish(conn, call_id='call', outcome={'response': 'done'}, now=12)
    # Cleanup failure must never replace an already persisted success.
    assert capacity.fail(conn, call_id='call', code='CLEANUP', stage='cleanup', message='Failed cleanup', now=13) == success
    assert call(conn, 'next')['state'] == 'QUEUED'
    assert not capacity.dispose_confirmed(conn, slot_id=resource['slot_id'], session_id='wrong')
    assert capacity.dispose_confirmed(conn, slot_id=resource['slot_id'], session_id=resource['session_id'])
    assert capacity.advance_queue(conn, executor_id='host', host_limit=10, now=14) == ['next']
    assert conn.execute('SELECT slot_id FROM one_shot_slots').fetchone()[0] != resource['slot_id']
    assert conn.execute('SELECT 1 FROM one_shot_slots WHERE call_id=?', ('next',)).fetchone() is None


def test_running_failure_is_not_safe_to_replay(conn):
    call(conn)
    run(conn)
    result = capacity.fail(conn, call_id='call', code='HOST_LOST', stage='execution', message='Connection lost.', now=12, retry_safe=True)
    assert result['error']['execution_started']
    assert result['error']['possible_effect']
    assert not result['error']['retry_safe']


def test_queued_cancel_has_no_effect(conn):
    call(conn, 'first')
    call(conn, 'waiting')
    result = capacity.fail(conn, call_id='waiting', code='CANCELLED', stage='queue', message='Cancelled.', now=11, cancelled=True, retry_safe=True)
    assert result['state'] == 'CANCELLED' and not result['error']['possible_effect']


def test_outcome_ack_requires_correct_caller(conn):
    call(conn)
    capacity.fail(conn, call_id='call', code='OPEN_FAILED', stage='opening', message='Opening failed.', now=11)
    assert not capacity.acknowledge_outcome(conn, caller_id='other', call_id='call', now=12)
    assert len(capacity.pending_outcomes(conn, caller_id='caller')) == 1
    assert capacity.acknowledge_outcome(conn, caller_id='caller', call_id='call', now=12)
    assert capacity.pending_outcomes(conn, caller_id='caller') == []


def test_host_cap_includes_other_agents(conn):
    configure(conn, max_parallel=10)
    call(conn, 'first', agent_id='other', host_limit=1)
    assert call(conn, 'second', host_limit=1)['state'] == 'QUEUED'


def test_queued_calls_prevent_warm_replenishment(conn):
    configure(conn, max_parallel=2, warm_instances=1)
    call(conn, 'first', host_limit=1)
    call(conn, 'second', host_limit=1)
    assert capacity.reserve_warm(conn, agent_id='other', executor_id='host', configuration_digest='config', host_limit=10, now=12) is None


def test_configuration_change_retires_only_unused_warm_instances(conn):
    configure(conn, max_parallel=3, warm_instances=2)
    resources = [capacity.reserve_warm(conn, agent_id='agent', executor_id='host', configuration_digest='config', host_limit=10, now=n) for n in range(2)]
    for resource in resources:
        capacity.ready(conn, slot_id=resource, session_id=resource)
    call(conn)
    assert capacity.retire_warm(conn, agent_id='agent', executor_id='host', configuration_digest='changed') == 1
    assert slot(conn, 'call')['state'] == 'CLAIMED'


def test_requires_transaction():
    conn = database()
    initialize(conn)
    with pytest.raises(RuntimeError):
        call(conn)
    conn.close()


def test_waiter_uses_first_ready_resource_not_a_specific_cold_open(conn):
    configure(conn, max_parallel=5, warm_instances=4)
    resources = [capacity.reserve_warm(conn, agent_id='agent', executor_id='host',
        configuration_digest='config', host_limit=10, now=n) for n in range(4)]
    for n in range(4):
        assert call(conn, f'call-{n}', now=10+n)['state'] == 'ADMITTED'
    assert conn.execute('SELECT count(*) FROM one_shot_slots').fetchone()[0] == 4
    assert not conn.execute('SELECT 1 FROM one_shot_slots WHERE call_id IS NOT NULL').fetchone()
    capacity.ready(conn, slot_id=resources[-1], session_id='fastest')
    assert capacity.advance_queue(conn, executor_id='host', host_limit=10, now=15) == ['call-0']
    assert slot(conn, 'call-0')['session_id'] == 'fastest'
    assert call(conn, 'later', now=16)['state'] == 'ADMITTED'
    capacity.ready(conn, slot_id=resources[0], session_id='next-ready')
    assert capacity.advance_queue(conn, executor_id='host', host_limit=10, now=17) == ['call-1']
    assert slot(conn, 'call-1')['session_id'] == 'next-ready'


def test_preparing_call_keeps_its_admission_deadline_after_queue_wait(conn):
    configure(conn, queue_timeout_seconds=5)
    call(conn, 'first')
    run(conn, 'first')
    call(conn, 'second', now=11)
    capacity.finish(conn, call_id='first', outcome={'response': 'done'}, now=13)
    capacity.dispose_confirmed(conn, slot_id=slot(conn, 'first')['slot_id'], session_id='session-first')
    assert capacity.advance_queue(conn, executor_id='host', host_limit=10, now=14) == ['second']
    resource = conn.execute("SELECT slot_id FROM one_shot_slots WHERE state='STARTING'").fetchone()[0]
    capacity.ready(conn, slot_id=resource, session_id='second-ready')
    assert capacity.advance_queue(conn, executor_id='host', host_limit=10, now=17) == ['second']
    assert slot(conn, 'second')['session_id'] == 'second-ready'


def test_cancelled_waiter_never_receives_late_ready_instance(conn):
    call(conn)
    resource = dict(conn.execute('SELECT * FROM one_shot_slots').fetchone())
    capacity.fail(conn, call_id='call', code='CANCELLED', stage='opening', message='Cancelled.', now=11, cancelled=True)
    assert capacity.trim_warm(conn, agent_id='agent', executor_id='host') == 1
    capacity.ready(conn, slot_id=resource['slot_id'], session_id='late-session')
    assert capacity.advance_queue(conn, executor_id='host', host_limit=10, now=12) == []
    assert conn.execute('SELECT state FROM one_shot_slots').fetchone()[0] == 'CLOSING'
    assert capacity.dispose_confirmed(conn, slot_id=resource['slot_id'], session_id='late-session')


@pytest.mark.parametrize('began', [False, True])
def test_deadline_preserves_capacity_and_publishes_error(conn, began):
    configure(conn, queue_timeout_seconds=2, execution_timeout_seconds=2)
    call(conn)
    if began:
        run(conn)
    assert capacity.expire_executions(conn, executor_id='host', now=14) == 1
    result = capacity.pending_outcomes(conn, caller_id='caller')[0]
    assert result['error']['code'] == ('ONE_SHOT_EXECUTION_TIMEOUT' if began else 'ONE_SHOT_START_TIMEOUT')
    assert result['error']['retry_safe'] is not began
    capacity.trim_warm(conn, agent_id='agent', executor_id='host')
    assert capacity.statistics(conn, executor_id='host', agent_id='agent')['closing'] == 1
    assert capacity.expire_executions(conn, executor_id='host', now=15) == 0


def test_warm_failure_backoff_does_not_block_other_agents_or_calls(conn):
    configure(conn, max_parallel=3, warm_instances=1)
    resource = capacity.reserve_warm(conn, agent_id='agent', executor_id='host', configuration_digest='config', host_limit=10, now=0)
    capacity.warm_failed(conn, slot_id=resource, now=1)
    assert capacity.reserve_warm(conn, agent_id='agent', executor_id='host', configuration_digest='config', host_limit=10, now=2) is None
    assert capacity.reserve_warm(conn, agent_id='other', executor_id='host', configuration_digest='config', host_limit=10, now=2)
    assert call(conn, now=2)['state'] == 'ADMITTED'
    assert capacity.dispose_confirmed(conn, slot_id=resource, session_id=None)
    assert capacity.reserve_warm(conn, agent_id='agent', executor_id='host', configuration_digest='config', host_limit=10, now=4)


def test_warm_target_is_shared_between_workspace_configurations(conn):
    configure(conn, max_parallel=4, warm_instances=1)
    assert capacity.reserve_warm(conn, agent_id='agent', executor_id='host', configuration_digest='workspace-a', host_limit=10, now=0)
    assert capacity.reserve_warm(conn, agent_id='agent', executor_id='host', configuration_digest='workspace-b', host_limit=10, now=0) is None


def test_reduced_capacity_requires_disposal_of_excess_warm_slots(conn):
    configure(conn, max_parallel=4, warm_instances=3)
    resources = [capacity.reserve_warm(conn, agent_id='agent', executor_id='host', configuration_digest='config', host_limit=10, now=n) for n in range(3)]
    for resource in resources:
        capacity.ready(conn, slot_id=resource, session_id=resource)
    configure(conn, max_parallel=2, warm_instances=1)
    assert call(conn)['state'] == 'QUEUED'
    assert capacity.trim_warm(conn, agent_id='agent', executor_id='host') == 2
    assert capacity.trim_warm(conn, agent_id='agent', executor_id='another-host') == 0
    closing = conn.execute("SELECT slot_id,session_id FROM one_shot_slots WHERE state='CLOSING'").fetchall()
    for row in closing:
        assert capacity.dispose_confirmed(conn, slot_id=row[0], session_id=row[1])
    assert capacity.advance_queue(conn, executor_id='host', host_limit=10, now=11) == ['call']


def test_simultaneous_admission_cannot_overbook_and_survives_restart(tmp_path):
    path = str(tmp_path / 'capacity.db')
    conn = database(path)
    initialize(conn)
    configure(conn, max_parallel=5, queue_capacity=20)
    conn.close()
    def submit(n):
        local = database(path)
        try:
            local.execute('BEGIN IMMEDIATE')
            result = call(local, f'call-{n}')
            local.commit()
            return result['state']
        finally:
            local.close()
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(submit, range(20)))
    assert results.count('ADMITTED') == 5
    assert results.count('QUEUED') == 15
    reopened = database(path)
    assert reopened.execute('SELECT count(*) FROM one_shot_slots').fetchone()[0] == 5
    assert reopened.execute('SELECT count(*) FROM one_shot_calls').fetchone()[0] == 20
    reopened.close()
