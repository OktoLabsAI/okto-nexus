"""Bounded operator samples report canonical winners, not fabricated totals."""
import json

from okto_nexus.bootstrap.handoff_runtime_views import build_handoff_runtime_views
from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, call
from test_handoff_runtime_attempts import prepared
from test_canonical_result_publication import current_turn


def metrics(setup, actor='operator'):
    response = setup[2].get('/api/v1/metrics/local/summary', headers=setup[3][actor])
    assert response.status_code == 200, response.text
    if actor == 'operator':
        assert response.headers['cache-control'] == 'no-store'
    return response.json()['data']


def test_real_reservation_claim_and_readonly_sample_are_reported_without_identity_labels(runtime):
    setup = runtime[0]
    service, port, attempt, hid, _ = prepared(runtime)
    aid = attempt.request.attempt_id
    before = metrics(setup)['broadcast_handoffs']
    assert before['winner_channels'] == dict(runtime=0, explicit=0, unclaimed=1)
    assert before['recorded_attempt_states']['WAITING'] == 1
    assert before['claim_latency'] == dict(count=0, min_ms=None, max_ms=None, mean_ms=None)
    setup[2].portal.call(service.reserve, aid)
    held = metrics(setup)['broadcast_handoffs']
    assert held['recorded_reservation_states']['HELD'] == 1
    claimed = service.claim(aid)
    setup[2].portal.call(build_capacity_admission(setup[0], capacity=port).consume, claimed.operation_id)
    wait_receipt(setup, current_turn(setup))
    current = metrics(setup)['broadcast_handoffs']
    assert current['recorded_reservation_states']['CONSUMED'] == 1
    assert current['winner_channels'] == dict(runtime=1, explicit=0, unclaimed=0)
    assert current['claim_latency']['count'] == 1 and current['claim_latency']['min_ms'] >= 0
    raw = json.dumps(current)
    for private in (hid, aid, attempt.request.affinity_key, attempt.request.scope.executor_id,
                    'Perform the authorized broadcast work',
                    *(headers['Authorization'].removeprefix('Bearer ') for headers in setup[3].values())):
        assert private not in raw
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        statements = []
        uow.connection.set_trace_callback(statements.append)
        changes = uow.connection.total_changes
        assert build_handoff_runtime_views(setup[0]).metrics(uow) == current
        assert uow.connection.total_changes == changes
        assert len(statements) == 3
    assert 'broadcast_handoffs' not in metrics(setup, 'subject')


def test_samples_are_limited_and_truncation_and_unknown_labels_are_explicit(runtime):
    setup = runtime[0]
    _, _, attempt, hid, _ = prepared(runtime)
    with setup[0].connection_factory.unit_of_work() as uow:
        conn = uow.connection
        handoff = dict(conn.execute('SELECT * FROM handoffs WHERE handoff_id=?', (hid,)).fetchone())
        row = dict(conn.execute('SELECT * FROM handoff_runtime_attempts WHERE attempt_id=?',
                               (attempt.request.attempt_id,)).fetchone())
        for table, original, make in [
            ('handoffs', handoff, lambda i: dict(handoff_id=f'private-handoff-{i:04}', created_at='2030-01-01T00:00:00Z')),
            ('handoff_runtime_attempts', row, lambda i: dict(attempt_id=f'private-attempt-{i:04}', active=0,
                state='NOT_AVAILABLE', reason='private dynamic diagnostic', updated_at='2030-01-01T00:00:00Z',
                reservation_json=json.dumps(dict(state='private dynamic reservation', payload='private payload')))),
        ]:
            fields = ','.join(original)
            placeholders = ','.join('?' for _ in original)
            conn.executemany(f'INSERT INTO {table}({fields}) VALUES({placeholders})',
                             [tuple((original | make(i)).values()) for i in range(1002)])
    view = metrics(setup)['broadcast_handoffs']
    assert view['sample_limit'] == 1000
    assert view['attempt_sample'] == view['handoff_sample'] == dict(size=1000, truncated=True)
    assert view['recorded_attempt_states']['NOT_AVAILABLE'] == 1000
    assert view['recorded_reasons']['UNKNOWN'] == view['recorded_reservation_states']['UNKNOWN'] == 1000
    assert view['winner_channels'] == dict(runtime=0, explicit=0, unclaimed=1000)
    assert 'private' not in json.dumps(view)
    # The two top-level page queries use their bounded order indexes.
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        statements = []
        uow.connection.set_trace_callback(statements.append)
        repo = build_handoff_runtime_views(setup[0]).repository
        repo.sample_attempts(uow, limit=1001)
        repo.sample_handoff_ids(uow, limit=1001)
        uow.connection.set_trace_callback(None)
        plans = [' '.join(str(tuple(row)) for row in uow.connection.execute('EXPLAIN QUERY PLAN '+sql)) for sql in statements]
        assert 'handoff_runtime_attempts_recent' in plans[0]
        assert 'handoff_broadcast_recent' in plans[1]
        assert all('TEMP B-TREE' not in plan for plan in plans)


def test_explicit_winner_is_counted_and_storage_failure_is_not_zero(runtime, monkeypatch):
    setup = runtime[0]
    _, _, _, hid, _ = prepared(runtime)
    claimed = call(runtime, 'handoff_claim', actor='subject', agent_id='subject', handoff_id=hid)
    assert claimed['ok'], claimed
    view = metrics(setup)['broadcast_handoffs']
    assert view['winner_channels'] == dict(runtime=0, explicit=1, unclaimed=0)
    from okto_nexus.adapters.outbound.sqlite.handoff_runtime_views import SqliteHandoffRuntimeViewRepository
    def fail(*args, **kwargs):
        raise OSError('private storage failure')
    monkeypatch.setattr(SqliteHandoffRuntimeViewRepository, 'sample_attempts', fail)
    assert metrics(setup)['broadcast_handoffs'] == dict(status='unavailable')
