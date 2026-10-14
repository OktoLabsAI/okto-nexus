"""Read models reflect canonical outcomes without acquiring or freeing work."""
import json

import pytest
from okto_nexus.application.handoff_runtime_views import progress
from okto_nexus.bootstrap.handoff_runtime_views import build_handoff_runtime_views
from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, call
from test_handoff_runtime_attempts import prepared
from test_canonical_result_publication import current_turn, emit, workspace
from test_reserved_handoff_tools import capability, invoke


def read(setup, hid):
    response = setup[2].get('/api/v1/handoffs', headers=setup[3]['operator'],
                            params={'workspace': workspace(setup)})
    assert response.status_code == 200, response.text
    return next(r for r in response.json()['data']['items'] if r['handoff_id'] == hid)


def overview(setup):
    response = setup[2].get('/api/v1/agents/subject/runtime-administration', headers=setup[3]['operator'])
    assert response.status_code == 200, response.text
    return response.json()['data']['broadcast_handoffs']


@pytest.mark.parametrize('verify', [False, True])
def test_runtime_projection_preserves_native_final_and_business_decision(runtime, verify):
    setup, binding, native = runtime
    setup[0].config.feature_verification = verify
    options = dict(acceptance_criteria=['Reviewed'], verify_by={'kind': 'creator'}) if verify else {}
    service, port, attempt, hid, _ = prepared(runtime, **options)
    aid = attempt.request.attempt_id
    before = read(setup, hid)['runtime_progress']
    assert before['state'] == 'AWAITING_EXPLICIT_CLAIM' and before['origin'] == 'missing'
    assert before['reason'] == 'AUTOMATION_DISABLED'
    assert before['winner_channel'] is None
    assert overview(setup)['items'][0]['state'] == 'WAITING'
    setup[2].portal.call(service.reserve, aid)
    held = overview(setup)['items'][0]
    assert held['state'] == 'RESERVED' and held['reservation_state'] == 'HELD'
    assert read(setup, hid)['status'] == 'OPEN' and native.opens == 0
    claimed = service.claim(aid)
    setup[2].portal.call(build_capacity_admission(setup[0], capacity=port).consume, claimed.operation_id)
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    view = read(setup, hid)['runtime_progress']
    assert view['state'] == 'DISPATCHED' and view['winner_channel'] == 'runtime'
    assert view['claimed_by'] == 'subject' and view['claim_latency_ms'] >= 0
    admitted = overview(setup)['items'][0]
    assert admitted['current_claim'] is True and admitted['reservation_state'] == 'CONSUMED'
    emit(setup, native, turn, 'Native final, not a handoff completion.')
    row = read(setup, hid)
    assert row['status'] == 'CLAIMED' and row['runtime_progress']['state'] == 'AWAITING_DECISION'
    cap = capability(setup, binding, turn['session_id'], 'native')
    done, code = invoke(setup, cap, 'complete', hid, claim_epoch=1, result='Reviewed')
    assert code == 200, done
    result = read(setup, hid)['runtime_progress']
    assert result['state'] == ('AWAITING_VERIFICATION' if verify else 'COMPLETED')
    assert native.opens == len(native.native.sent) == 1
    admin = overview(setup)
    encoded = json.dumps(admin)
    for private in ('principal_json', 'request_json', 'source_session_key', 'Perform the authorized broadcast work', 'capability', 'reservation_json'):
        assert private not in encoded
    assert admin['items'][0]['current_claim'] is verify
    assert setup[2].get('/api/v1/agents/subject/runtime-administration', headers=setup[3]['subject']).status_code == 403
    assert setup[2].get('/api/v1/handoffs', headers=setup[3]['operator'],
                        params={'workspace': 'unrelated'}).json()['data']['items'] == []
    # A later canonical epoch cannot inherit native facts from this old binding.
    # This is a projection fixture, not an invocation of the recovery workflow.
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE handoffs SET status='CLAIMED',claim_epoch=2,claimed_by='caller' WHERE handoff_id=?", (hid,))
    newer = read(setup, hid)['runtime_progress']
    assert newer['state'] == 'CLAIMED' and newer['native_stage'] is None
    assert newer['winner_channel'] == 'explicit' and newer['claimed_by'] == 'caller'
    assert overview(setup)['items'][0]['current_claim'] is False


def test_attempt_history_is_bounded_scoped_read_only_and_query_count_constant(runtime):
    setup = runtime[0]
    _, _, attempt, hid, _ = prepared(runtime)
    with setup[0].connection_factory.unit_of_work() as uow:
        conn = uow.connection
        original = dict(conn.execute('SELECT * FROM handoff_runtime_attempts WHERE attempt_id=?',
                                    (attempt.request.attempt_id,)).fetchone())
        fields = ','.join(original)
        placeholders = ','.join('?' for _ in original)
        for i in range(25):
            row = original | dict(attempt_id=f'history-{i:02}', active=0, state='NOT_AVAILABLE',
                reason='POOL_FULL', updated_at=f'2030-01-01T00:00:{i:02}Z')
            conn.execute(f'INSERT INTO handoff_runtime_attempts({fields}) VALUES({placeholders})', tuple(row.values()))
        foreign = original | dict(attempt_id='foreign-private', agent_id='caller', active=0,
                                 state='NOT_AVAILABLE', reason='private secret must not be exposed')
        conn.execute(f'INSERT INTO handoff_runtime_attempts({fields}) VALUES({placeholders})', tuple(foreign.values()))
    service = build_handoff_runtime_views(setup[0])
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        statements = []
        uow.connection.set_trace_callback(statements.append)
        before = uow.connection.total_changes
        view = service.agent(uow, 'subject')
        assert uow.connection.total_changes == before
        assert len(statements) == 2
        assert view['has_more'] is True and len(view['items']) == 20
        assert view['items'][0]['attempt_id'] == 'history-24'
        assert all(r['attempt_id'] != 'foreign-private' for r in view['items'])
        assert service.agent(uow, 'caller')['items'][0]['reason'] == 'UNKNOWN'
        assert service.handoffs(uow, []) == {}
    assert read(setup, hid)['status'] == 'OPEN'


@pytest.mark.parametrize('status,state', [('COMPLETED','COMPLETED'), ('VERIFYING','AWAITING_VERIFICATION'),
                                        ('CANCELLED','CANCELLED'), ('REJECTED','REJECTED')])
@pytest.mark.parametrize('stage', ['RUNNING', 'SUCCEEDED', 'FAILED', 'OUTCOME_UNKNOWN'])
def test_canonical_decision_outweighs_native_stage(status, state, stage):
    assert progress(dict(status=status, native_stage=stage))['state'] == state


@pytest.mark.parametrize('stage,state', [('FAILED','EXECUTION_FAILED'), ('CANCELLED','EXECUTION_FAILED'),
    ('OUTCOME_UNKNOWN','NEEDS_RECONCILIATION'), ('RUNNING','RUNNING'), ('WAITING_INPUT','WAITING_INPUT'),
    ('SUBMITTED','DISPATCHED'), ('SUCCEEDED','AWAITING_DECISION')])
def test_native_progress_cannot_complete_handoff(stage, state):
    assert progress(dict(status='CLAIMED', native_stage=stage, native_action='turn.submit'))['state'] == state


def test_unknown_capacity_and_opening_success_do_not_imply_completion():
    facts = dict(status='CLAIMED', native_stage='SUCCEEDED', native_action='runtime.start')
    assert progress(facts)['state'] == 'CLAIMED'
    assert progress(facts | dict(capacity_state='NEEDS_RECONCILIATION'))['state'] == 'NEEDS_RECONCILIATION'
    assert progress(dict(status='OPEN', schedule_reason='private secret'))['reason'] == 'UNKNOWN'


def test_direct_handoff_keeps_previous_response_shape(runtime):
    made = call(runtime, 'handoff_create', from_agent_id='caller', visibility='eligible',
                target={'strategy':'direct','agent_id':'subject'}, payload='Direct')
    assert made['ok'], made
    assert 'runtime_progress' not in read(runtime[0], made['data']['handoff_id'])
