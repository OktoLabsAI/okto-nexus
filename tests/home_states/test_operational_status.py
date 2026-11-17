"""Pure metadata reduction, not a native adapter qualification."""
from dataclasses import asdict, replace

import pytest

from okto_nexus.domain.attention import occurrence
from okto_nexus.domain.home_entries import (
    ConnectionContext,
    EntryRecord,
    EntryRelations,
    SessionRuntimeFact,
)
from okto_nexus.domain.home_harness_blocking import project_v2

NOW = '2026-11-17T12:00:00.000000Z'
LATER = '2026-11-17T13:00:00.000000Z'


def facts():
    connection = ConnectionContext('server', 'executor', 'ws', 'binding', 'wxb', 'agent', harness_id='codex_app_server')
    session = SessionRuntimeFact('server', 'executor', 'binding', 'ws', 'wxb', 'agent', 'session', 'epoch', 1,
                                 'READY', True, LATER, NOW, runtime_ready=True, persistent_runtime=True, authority_current=True)
    operation = dict(asdict(connection), family='operation', session_id='session', operation_id='op',
                     owner_generation=1, stream_epoch='epoch', admission_state='ACCEPTED', stage='RUNNING',
                     dispatch_state='DISPATCHED', received_at=NOW)
    sources = dict.fromkeys(('attention', 'connections', 'sessions', 'correlations', 'work', 'results', 'external'), 'ready')
    relations = EntryRelations([], [], sources, 1, (connection,), [operation], (session,))
    return relations, connection, session, operation


def reduce(relations, connection):
    key = tuple(getattr(connection, k) for k in ('server_id', 'executor_id', 'binding_id', 'workspace_id', 'workspace_binding_id', 'agent_id'))
    states, owners, waiting = project_v2(relations, {key: connection}, now=NOW, check_budget=lambda: None)
    return states[key], owners, waiting


def question(relations, connection, **changes):
    o = occurrence(kind='native_question_pending', source_type='execution_native_request', source_id='request',
        episode=1, source_revision=1, first_detected_at=NOW, last_changed_at=NOW,
        workspace_id='ws', agent_id='agent', executor_id='executor', session_id='session', operation_id='op',
        category='action_required', allowed_actions=['respond_native'])
    entry = EntryRecord('entry', 'attention', {'type': 'execution_native_request', 'id': 'request', 'revision': '1'},
        'ws', 'agent', 'Question', 'awaiting_operator', 'confirmed', None, attention=[o])
    relations.entries.append(entry)
    r = dict(asdict(connection), family='request', session_id='session', operation_id='op', request_id='request',
        owner_generation=1, request_revision=1, state='PENDING', expires_at=LATER, stream_epoch='epoch',
        session_stream_epoch='epoch', adapter_id='codex_app_server', method='item/tool/requestUserInput',
        is_blocking=1, approval_status='pending', decided_at=None, decision_id=None, native_operation_id=None,
        decision_scope_matches=1)
    r.update(changes)
    relations.harness_blocking.append(r)
    return o, r


def test_live_idle_requires_complete_absence_and_does_not_follow_registration():
    rel, c, session, _ = facts()
    rel.harness_blocking = []
    assert reduce(rel, c)[0]['operational_status']['activity'] == 'idle'
    rel.operational_sessions = ()
    status = reduce(rel, c)[0]['operational_status']
    assert status['connection'] == 'registered' and status['activity'] == 'unknown'
    rel.operational_sessions = (replace(session, lifecycle_state='CLOSED', control_current=False),)
    assert reduce(rel, c)[0]['operational_status']['activity'] == 'no_active_session'


def test_expired_control_never_proves_idle_or_working():
    rel, c, session, _ = facts()
    rel.operational_sessions = (replace(session, valid_until=NOW),)
    assert reduce(rel, c)[0]['operational_status']['activity'] == 'unknown'


def test_active_lease_without_runtime_open_proof_never_proves_idle():
    rel, c, session, _ = facts()
    rel.harness_blocking = []
    rel.operational_sessions = (replace(session, runtime_ready=False),)
    assert reduce(rel, c)[0]['operational_status']['activity'] == 'unknown'


def test_offline_or_incomplete_prior_block_does_not_place_confirmation_in_needs_you():
    rel, c, session, _ = facts()
    o, r = question(rel, c, state='DECIDED', decision_id='d', native_operation_id='reply')
    o.update(category='watch', resolution='resolved', active=False, allowed_actions=['inspect_approval'])
    rel.operational_sessions = (replace(session, control_current=False),)
    result = reduce(rel, c)[0]
    assert result['placement_reason'] == 'monitoring_unconfirmed'
    assert result['operational_status']['awaiting_native_confirmation']
    r['decision_scope_matches'] = 0
    assert not reduce(rel, c)[0]['operational_status']['awaiting_native_confirmation']


def test_unrelated_external_failure_preserves_positive_working_but_not_unknown_absence():
    rel, c, _, _ = facts()
    rel.source_status['external'] = 'unavailable'
    assert reduce(rel, c)[0]['operational_status']['activity'] == 'working'
    rel.harness_blocking = []
    rel.source_status['correlations'] = 'unavailable'
    assert reduce(rel, c)[0]['operational_status']['activity'] == 'unknown'


def test_blocked_session_and_independent_working_session_have_distinct_dimensions():
    rel, c, session, op = facts()
    question(rel, c)
    first = reduce(rel, c)[0]
    assert first['blocks_harness'] is True and first['placement_reason'] == 'human_block_confirmed'
    rel.operational_sessions += (replace(session, session_id='sibling'),)
    rel.harness_blocking.append(dict(op, operation_id='sibling-op', session_id='sibling'))
    second = reduce(rel, c)[0]['operational_status']
    assert second['activity'] == 'working' and second['blocking'] == 'partial'
    assert second['blocked_sessions']['value'] == 1 and second['running_sessions']['value'] == 1


def test_idle_sibling_does_not_supply_independent_progress():
    rel, c, session, _ = facts()
    question(rel, c)
    rel.operational_sessions += (replace(session, session_id='idle-sibling'),)
    assert reduce(rel, c)[0]['blocks_harness'] is True


@pytest.mark.parametrize('adapter,method', [('pi_rpc', 'extension_ui_request'),
    ('claude_code_stream_json', 'claude/AskUserQuestion'), ('pi_rpc', 'item/tool/requestUserInput')])
def test_no_cross_adapter_blocking_extrapolation(adapter, method):
    rel, c, _, _ = facts()
    question(rel, c, adapter_id=adapter, method=method)
    result = reduce(rel, c)[0]
    assert result['blocks_harness'] is None and result['operational_status']['pending_actions']['value'] == 1


def test_decision_and_late_old_running_never_claim_resume():
    rel, c, _, op = facts()
    o, _ = question(rel, c, state='DECIDED', approval_status='approved', decision_id='decision', native_operation_id='reply')
    o.update(resolution='resolved', category='watch', active=False, allowed_actions=['inspect_approval'])
    op['received_at'] = LATER  # Arrival after decision is not causality.
    result = reduce(rel, c)[0]
    assert result['blocks_harness'] is None and result['placement_reason'] == 'awaiting_native_confirmation'
    assert result['operational_status']['pending_actions']['value'] == 0
    assert result['resume_confirmation_refs'][0]['decision_id'] == 'decision'
    op['stage'] = 'SUCCEEDED'
    assert reduce(rel, c)[0]['operational_status']['activity'] == 'idle'


@pytest.mark.parametrize('field,value', [('owner_generation', 2), ('stream_epoch', 'old')])
def test_old_epoch_or_owner_cannot_establish_current_block_or_confirmation(field, value):
    rel, c, _, _ = facts()
    question(rel, c, **{field: value}, state='DECIDED', decision_id='decision', native_operation_id='reply')
    result = reduce(rel, c)[0]
    assert result['blocks_harness'] is None and result['resume_confirmation_refs'] == []


def test_queue_is_not_working_idle_or_evidence_of_an_independent_turn():
    rel, c, _, op = facts()
    op.update(stage=None, dispatch_state='PENDING')
    assert reduce(rel, c)[0]['operational_status']['activity'] == 'queued'


def test_agent_recipient_does_not_become_operator_blocking_card():
    rel, c, _, _ = facts()
    o, _ = question(rel, c)
    o.update(kind='question_waiting_for_agent', category='watch', allowed_actions=['inspect_approval'])
    result = reduce(rel, c)[0]
    assert result['placement_reason'] == 'monitoring_unconfirmed'
    assert result['blocks_harness'] is None
    assert result['operational_status']['activity'] == 'waiting_agent'
    assert result['operational_status']['pending_actions']['value'] == 0


def test_outcome_unknown_cannot_prove_global_pause_despite_old_question():
    rel, c, _, op = facts()
    question(rel, c)
    op.update(stage='OUTCOME_UNKNOWN', dispatch_state='RECONCILING')
    assert reduce(rel, c)[0]['blocks_harness'] is None


@pytest.mark.parametrize('stage,effect,reason,awaiting', [
    ('FAILED', 0, 'NATIVE_RESPONSE_NOT_APPLIED', False),
    ('OUTCOME_UNKNOWN', 1, 'NATIVE_RESPONSE_OUTCOME_UNKNOWN', True),
    ('SUCCEEDED', 1, 'NATIVE_APPLICATION_UNCONFIRMED', True),
])
def test_native_write_refusal_unknown_and_success_are_not_application(stage, effect, reason, awaiting):
    rel, c, _, _ = facts()
    o, _ = question(rel, c, state='DECIDED', decision_id='d', native_operation_id='reply',
                    native_write_stage=stage, native_write_possible_effect=effect)
    o.update(category='watch', resolution='resolved', active=False, allowed_actions=['inspect_approval'])
    result = reduce(rel, c)[0]
    assert result['operational_status']['reason_code'] == reason
    assert result['operational_status']['awaiting_native_confirmation'] is awaiting
    assert result['operational_status']['pending_actions']['value'] == 0
    assert result['blocks_harness'] is None and result['resume_confirmation_refs']


@pytest.mark.parametrize('prior_state', ['idle', 'working', 'blocked', 'confirmation'])
def test_changed_authority_never_keeps_current_activity_or_confirmation(prior_state):
    rel, c, session, _ = facts()
    if prior_state == 'idle':
        rel.harness_blocking = []
    elif prior_state in ('blocked', 'confirmation'):
        o, _ = question(rel, c, **({'state': 'DECIDED', 'decision_id': 'decision', 'native_operation_id': 'reply'}
            if prior_state == 'confirmation' else {}))
        if prior_state == 'confirmation':
            o.update(category='watch', resolution='resolved', active=False, allowed_actions=['inspect_approval'])
    rel.operational_sessions = (replace(session, authority_current=False),)
    result = reduce(rel, c)[0]
    assert result['operational_status']['activity'] == 'unknown'
    assert result['blocks_harness'] is None
    assert result['resume_confirmation_refs'] == []
    assert not result['operational_status']['awaiting_native_confirmation']
