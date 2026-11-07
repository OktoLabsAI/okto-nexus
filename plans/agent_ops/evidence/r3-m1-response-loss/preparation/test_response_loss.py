from copy import deepcopy
import json

import pytest

from response_loss import CampaignState, DriverRefusal, FiniteResponseLoss, ROUTES
from okto_nexus.application.terminal_connection import ConnectionError, document_revision


def admission(index=1):
    body = dict(client_intent_id=f'intent-{index}', operation_id=f'operation-{index}',
                resolution_revision=1, intent_hash='a' * 64)
    scope = dict(server_id='server', executor_id='executor', binding_id='binding',
                 agent_id='agent', workspace_id='workspace')
    checkpoint = dict(scope=scope, session_id='session', work=dict(state='submit_submitted',
        action='send', intent='runtime.start', submission=body))
    result = dict(operation_id=body['operation_id'], intent_hash=body['intent_hash'],
                  scope=scope | {'session_id': 'session'})
    return checkpoint, body, result


def test_exact_one_loss_survives_driver_restart_and_never_reposts(tmp_path):
    state = CampaignState(tmp_path/'state.json', campaign_id='finite')
    checkpoint, body, result = admission()
    state.arm('admission', 'connector', 'intent-1')
    calls = []
    def call(*args):
        calls.append(args[:2])
        return deepcopy(result)
    wrapped = FiniteResponseLoss(call, lambda: checkpoint, state, 'connector')
    with pytest.raises(ConnectionError) as caught:
        wrapped('POST', ROUTES['admission'], body)
    assert caught.value.possible_effect and caught.value.code == 'OUTCOME_UNKNOWN'
    assert state.snapshot()['faults']['admission']['phase'] == 'consumed'
    restored = CampaignState(state.path)
    with pytest.raises(DriverRefusal, match='FAULT_ALREADY_USED'):
        restored.arm('admission', 'connector', 'intent-2')
    with pytest.raises(DriverRefusal, match='REPEATED_POST'):
        FiniteResponseLoss(call, lambda: checkpoint, restored, 'connector')('POST', ROUTES['admission'], body)
    assert len(calls) == 1


def test_six_reservations_shared_by_two_lanes_not_seventh(tmp_path):
    state = CampaignState(tmp_path/'state.json', campaign_id='finite')
    calls = []
    for index in range(1, 8):
        checkpoint, body, result = admission(index)
        def call(*args):
            calls.append(args[:2])
            return result
        wrapper = FiniteResponseLoss(call, lambda: checkpoint, state,
                                     'local' if index < 4 else 'connector')
        if index == 7:
            with pytest.raises(DriverRefusal, match='ALLOCATION_EXHAUSTED'):
                wrapper('POST', ROUTES['admission'], body)
        else:
            assert wrapper('POST', ROUTES['admission'], body) == result
    assert len(calls) == 6


@pytest.mark.parametrize('problem', ['wrong_scope', 'wrong_id', 'transport'])
def test_unconfirmed_response_not_qualified_fault_and_controls_remain_available(tmp_path, problem):
    state = CampaignState(tmp_path/'state.json', campaign_id='finite')
    checkpoint, body, result = admission()
    state.arm('admission', 'local', 'intent-1')
    if problem == 'wrong_scope':
        result['scope']['session_id'] = 'foreign'
    elif problem == 'wrong_id':
        result['operation_id'] = 'foreign'
    def call(*args):
        if problem == 'transport':
            raise ConnectionError('OUTCOME_UNKNOWN', 'Synthetic preexisting transport failure', possible_effect=True)
        return result
    with pytest.raises((DriverRefusal, ConnectionError)):
        FiniteResponseLoss(call, lambda: checkpoint, state, 'local')('POST', ROUTES['admission'], body)
    assert state.snapshot()['blocked'] and state.snapshot()['faults']['admission']['phase'] == 'unconfirmed'
    checkpoint['control'] = dict(state='submit_submitted', action='close', submission={'operation_id': 'close'})
    assert FiniteResponseLoss(lambda *args: {'closed': True}, lambda: checkpoint, state, 'local')(
        'POST', ROUTES['admission'], checkpoint['control']['submission']) == {'closed': True}


def test_wrong_checkpoint_and_external_mutation_refuse_before_forward(tmp_path):
    state = CampaignState(tmp_path/'state.json', campaign_id='finite')
    checkpoint, body, _ = admission()
    calls = []
    call = lambda *args: calls.append(args)
    bad = deepcopy(body) | {'operation_id': 'foreign'}
    with pytest.raises(DriverRefusal, match='CHECKPOINT_MISMATCH'):
        FiniteResponseLoss(call, lambda: checkpoint, state, 'local')('POST', ROUTES['admission'], bad)
    state.path.write_text('{}')
    with pytest.raises(DriverRefusal, match='EXTERNAL_STATE_CHANGE'):
        FiniteResponseLoss(call, lambda: checkpoint, state, 'local')('POST', ROUTES['admission'], body)
    assert calls == []


def test_response_and_prompt_material_never_enter_driver_journal(tmp_path):
    state = CampaignState(tmp_path/'state.json', campaign_id='finite')
    checkpoint, _, _ = admission()
    key = checkpoint['scope'] | {'session_id': 'session', 'canonical_request_id': 'approval-1'}
    response = {'answers': {'one': {'answers': ['PRIVATE_ANSWER_CANARY']}}}
    body = dict(approval_key=key, expected_revision=1, request_hash='b'*64, cas_token='PRIVATE_CAS_CANARY',
                decision='approve', client_intent_id='decision-intent', response=response)
    checkpoint['decision'] = {k: v for k, v in body.items() if k != 'response'}
    checkpoint['decision']['response_hash'] = document_revision(response)
    result = dict(canonical_state='CONFIRMED', decision_id='decision-1', approval_key=key,
                  request_hash=body['request_hash'], client_intent_id=body['client_intent_id'], extra='PRIVATE_RESULT_CANARY')
    state.arm('decision', 'connector', 'approval-1')
    with pytest.raises(ConnectionError):
        FiniteResponseLoss(lambda *args: result, lambda: checkpoint, state, 'connector')('POST', ROUTES['decision'], body)
    assert 'PRIVATE_' not in state.path.read_text()
    assert json.loads(state.path.read_text())['faults']['decision']['phase'] == 'consumed'


def test_unrelated_reads_forward_without_fault_or_reservation(tmp_path):
    state = CampaignState(tmp_path/'state.json', campaign_id='finite')
    state.arm('admission', 'local', 'intent-1')
    result = {'same': 'object'}
    assert FiniteResponseLoss(lambda *args: result, lambda: {}, state, 'local')(
        'GET', ROUTES['admission'] + '/known') is result
    assert state.snapshot()['admissions'] == []


@pytest.mark.parametrize('uncertain_collection', ['admissions', 'decisions'])
def test_crash_after_reservation_blocks_new_work_but_not_inspection_or_close(tmp_path, uncertain_collection):
    state = CampaignState(tmp_path/'state.json', campaign_id='finite')
    # Exact durable boundary after save(), before sending or receiving anything.
    state.data[uncertain_collection].append(dict(lane='connector', target='old-target',
        operation_id='old-operation', phase='forwarding'))
    state.save()
    restored = CampaignState(state.path)
    assert restored.snapshot()['blocked'] is False  # The phase itself must fence it.
    checkpoint, body, _ = admission(2)
    calls = []
    def call(method, path, body=None):
        calls.append((method, path))
        return {'inspect_or_close': True}
    wrapped = FiniteResponseLoss(call, lambda: checkpoint, restored, 'local')
    with pytest.raises(DriverRefusal, match='REQUIRES_RECONCILIATION'):
        wrapped('POST', ROUTES['admission'], body)
    assert calls == []
    assert wrapped('GET', ROUTES['admission']+'/old-operation')['inspect_or_close']
    checkpoint['control'] = dict(state='submit_submitted', action='close', submission={'operation_id': 'close'})
    assert wrapped('POST', ROUTES['admission'], checkpoint['control']['submission'])['inspect_or_close']
    assert len(calls) == 2
