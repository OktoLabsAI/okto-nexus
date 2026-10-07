"""Reviewed handoff recovery preserves Core history and claim epochs."""
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable
from test_canonical_handoff_regressions import runtime, call, grant, claim
from test_canonical_result_publication import current_turn, emit, wait_result
from test_runtime_handoff_recovery import recovery


def uncertain_work(runtime, *, terminal=False, **options):
    setup, binding, native = runtime
    if terminal:
        enable(setup, binding)
    response = call(runtime, 'handoff_create', from_agent_id='caller', visibility='eligible',
        target=dict(strategy='direct', agent_id='subject'), payload='Reviewed uncertain work', **options)
    assert response['ok'], response
    hid = response['data']['handoff_id']
    admitted = claim(runtime, hid, grant(runtime, ('execute_work', 'read') if terminal else ('execute_work',)))
    assert admitted['ok'], admitted
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    if terminal:
        emit(setup, native, turn, 'Captured work evidence, not a completion')
        wait_result(setup, 'PUBLISHED')
    close = admit(setup, binding, 'uncertain-work-close', 'runtime.close', session_id=turn['session_id'])
    wait_receipt(setup, close, stages=('SUCCEEDED',))
    until = time.monotonic() + 10
    while True:
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            row = dict(uow.connection.execute('SELECT * FROM delivery_outbox').fetchone())
        if row['status'] == 'OUTCOME_UNKNOWN' or terminal:
            return hid, admitted['data']['claim_epoch'], row
        assert time.monotonic() < until, row
        time.sleep(.02)


def post(runtime, args, actor='operator'):
    setup = runtime[0]
    return setup[2].post('/api/v1/harness/outbox', headers=setup[3][actor], json=args)


def test_recovery_preserves_history_and_new_claim_epoch(runtime):
    hid, epoch, row = uncertain_work(runtime)
    setup, _, native = runtime
    args = recovery(hid, epoch, row)
    response = post(runtime, args)
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert data['handoff']['status'] == 'OPEN' and data['inbox_released'] is False
    replay = call(runtime, 'harness_list', actor='operator', view='outbox', maintenance=args)
    assert replay['ok'] and replay['data'] == data, replay
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        handoff = uow.connection.execute('SELECT status,claimed_by,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()
        assert tuple(handoff) == ('OPEN', None, epoch)
        original = uow.connection.execute('SELECT status,ack_level FROM delivery_outbox').fetchone()
        assert tuple(original) == (row['status'], row['ack_level'])
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1
    next_claim = call(runtime, 'handoff_claim', actor='subject', handoff_id=hid, agent_id='subject')
    assert next_claim['ok'] and next_claim['data']['claim_epoch'] == epoch + 1, next_claim
    stale = call(runtime, 'handoff_complete', actor='subject', handoff_id=hid, agent_id='subject', claim_epoch=epoch, result='Old output')
    assert not stale['ok'], stale
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE handoffs SET lease_expires_at='2000-01-01T00:00:00Z' WHERE handoff_id=?", (hid,))
    current = call(runtime, 'handoff_get', actor='subject', handoff_id=hid, agent_id='subject')
    assert current['ok'] and current['data']['status'] == 'OPEN', current
    assert native.opens == 1 and len(native.native.sent) == 1


@pytest.mark.parametrize('change', [dict(expected_claim_epoch=999), dict(expected_handoff_id='other-work'),
    dict(acknowledge_duplicate_risk=False), dict(expected_attempt_id='old-attempt')])
def test_stale_or_unreviewed_handoff_recovery_is_refused(runtime, change):
    hid, epoch, row = uncertain_work(runtime)
    response = post(runtime, recovery(hid, epoch, row, **change))
    assert response.status_code == 409, response.text
    with runtime[0][0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status FROM handoffs').fetchone()[0] == 'CLAIMED'
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_operation_reconciliations').fetchone()[0] == 0


def test_operator_recovers_work_with_admission_disabled(runtime):
    hid, epoch, row = uncertain_work(runtime)
    args = recovery(hid, epoch, row)
    for actor in ('caller', 'subject'):
        assert post(runtime, args, actor).status_code == 403
        refusal = call(runtime, 'harness_list', actor=actor, view='outbox', maintenance=args)
        assert not refusal['ok'] and refusal['error']['code'] == 'PERMISSION_DENIED', refusal
    runtime[0][0].config.feature_harness_integrations = False
    result = call(runtime, 'harness_list', actor='operator', view='outbox', maintenance=args)
    assert result['ok'] and result['data']['handoff']['status'] == 'OPEN', result


@pytest.mark.parametrize('status', ['COMPLETED', 'VERIFYING', 'REJECTED'])
def test_recovery_never_reopens_completed_work(runtime, status):
    runtime[0][0].config.feature_verification = True
    hid, epoch, row = uncertain_work(runtime, **(dict(acceptance_criteria=['Review evidence']) if status == 'VERIFYING' else {}))
    action = 'handoff_reject' if status == 'REJECTED' else 'handoff_complete'
    value = dict(reason='Explicit rejection') if status == 'REJECTED' else dict(result='Explicit completion')
    completed = call(runtime, action, actor='subject', agent_id='subject', handoff_id=hid, claim_epoch=epoch, **value)
    assert completed['ok'], completed
    response = post(runtime, recovery(hid, epoch, row))
    assert response.status_code == 409, response.text
    with runtime[0][0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status FROM handoffs').fetchone()[0] == status


def test_handoff_recovery_rolls_back_transition_event_and_audit(runtime, monkeypatch):
    hid, epoch, row = uncertain_work(runtime)
    deps = runtime[0][0]
    original = deps.repos.handoffs.reopen_managed_claim
    def cut(*args, **kwargs):
        original(*args, **kwargs)
        from okto_nexus.errors import OktoNexusError, ErrorCode
        raise OktoNexusError(ErrorCode.CONFLICT, 'Fixture cut after canonical transition', {})
    monkeypatch.setattr(deps.repos.handoffs, 'reopen_managed_claim', cut)
    assert post(runtime, recovery(hid, epoch, row)).status_code == 409
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status FROM handoffs').fetchone()[0] == 'CLAIMED'
        assert uow.connection.execute('SELECT reconciliation_id FROM delivery_outbox').fetchone()[0] is None
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_operation_reconciliations').fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM events WHERE type='handoff.recovered'").fetchone()[0] == 0


def test_concurrent_handoff_recovery_is_one_transition(runtime):
    hid, epoch, row = uncertain_work(runtime)
    args = recovery(hid, epoch, row)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: post(runtime, args), range(2)))
    assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
    assert results[0].json() == results[1].json()
    with runtime[0][0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM events WHERE type='handoff.recovered'").fetchone()[0] == 1
        audit = uow.connection.execute('SELECT * FROM runtime_operation_reconciliations').fetchall()
        assert len(audit) == 1 and audit[0]['canonical_action'] == 'reopen_handoff'
        assert (audit[0]['handoff_id'], audit[0]['claim_epoch']) == (hid, epoch)
    assert post(runtime, recovery(hid, epoch, row, reason='Changed recovery')).status_code == 409


def test_completed_native_turn_can_be_recovered_without_completing_work(runtime):
    hid, epoch, row = uncertain_work(runtime, terminal=True)
    response = post(runtime, recovery(hid, epoch, row))
    assert response.status_code == 200 and response.json()['data']['handoff']['status'] == 'OPEN', response.text


def test_handoff_claim_cannot_be_released_as_conversation(runtime):
    hid, epoch, row = uncertain_work(runtime)
    args = recovery(hid, epoch, row, action='release_to_inbox')
    args.pop('expected_handoff_id')
    args.pop('expected_claim_epoch')
    response = post(runtime, args)
    assert response.status_code == 409 and 'handoff recovery' in response.text, response.text
    with runtime[0][0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status FROM handoffs').fetchone()[0] == 'CLAIMED'


def test_retired_stdio_cannot_create_another_work_recovery_owner(runtime):
    import os
    import subprocess
    import sys
    hid, epoch, row = uncertain_work(runtime)
    deps = runtime[0][0]
    before = (deps.runtime_dispatcher.owner_id, deps.runtime_dispatcher.epoch)
    env = dict(os.environ, OKTO_NEXUS_API_KEY=runtime[0][3]['operator']['Authorization'].removeprefix('Bearer '))
    retired = subprocess.run([sys.executable, '-m', 'okto_nexus.adapters.inbound.mcp.server',
        '--home', str(deps.config.home_dir)], env=env, capture_output=True, text=True, timeout=30)
    assert retired.returncode != 0
    assert 'MCP stdio is no longer available' in retired.stderr
    args = recovery(hid, epoch, row)
    response = call(runtime, 'harness_list', actor='operator', view='outbox', maintenance=args)
    assert response['ok'], response
    repeated = post(runtime, args)
    assert repeated.status_code == 200 and repeated.json()['data'] == response['data'], repeated.text
    assert (deps.runtime_dispatcher.owner_id, deps.runtime_dispatcher.epoch) == before
    assert runtime[2].opens == 1 and len(runtime[2].native.sent) == 1


def test_late_structured_output_cannot_complete_reclaimed_work(connected_local, monkeypatch):
    from okto_nexus.application.handoff import HandoffService
    from test_canonical_structured_work import native_work, state
    setup, binding, hid, _, claim_work, call_work, peers = native_work(connected_local, monkeypatch)
    with monkeypatch.context() as patch:
        patch.setattr(HandoffService, 'process_runtime_results', lambda service: 0)
        admitted = claim_work(completion_mode='structured_result_v1')
        assert admitted['ok'], admitted
        result = wait_result(setup, 'PENDING_AUTHORIZATION')
        turn = current_turn(setup)
        wait_receipt(setup, turn, stages=('SUCCEEDED',))
        closed = admit(setup, binding, 'close-before-reclaim', 'runtime.close', session_id=turn['session_id'])
        wait_receipt(setup, closed, stages=('SUCCEEDED',))
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            row = dict(uow.connection.execute('SELECT * FROM delivery_outbox').fetchone())
        epoch = admitted['data']['claim_epoch']
        response = setup[2].post('/api/v1/harness/outbox', headers=setup[3]['operator'], json=recovery(hid, epoch, row))
        assert response.status_code == 200, response.text
        fresh = call_work('handoff_claim', handoff_id=hid, agent_id='subject')
        assert fresh['ok'] and fresh['data']['claim_epoch'] == epoch + 1, fresh
        assert state(setup, hid)['status'] == 'CLAIMED'
    setup[0].runtime_dispatcher.wake()
    until = time.monotonic() + 10
    while True:
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            outcome = uow.connection.execute('SELECT state FROM runtime_work_outcomes WHERE operation_id=?', (row['operation_id'],)).fetchone()
        if outcome:
            break
        assert time.monotonic() < until
        time.sleep(.02)
    assert outcome[0] == 'BLOCKED'
    current = state(setup, hid)
    assert current['status'] == 'CLAIMED' and current['claim_epoch'] == epoch + 1
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT output_text FROM runtime_results WHERE result_id=?', (result['result_id'],)).fetchone()[0] == result['output_text']
    assert len(peers) == 1 and peers[0]._transport._proc.poll() is not None
