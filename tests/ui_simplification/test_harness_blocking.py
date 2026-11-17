"""Metadata contract fixtures, not native/provider execution claims."""
from dataclasses import asdict

import pytest

from okto_nexus.domain.attention import occurrence, with_preferences
from okto_nexus.domain.home_entries import ConnectionContext, EntryRecord, EntryRelations, SessionContext
from okto_nexus.domain.home_entry_pages import filters
from okto_nexus.domain.home_harness_board import page


NOW = '2026-11-16T12:00:00.000000Z'


def setup_facts():
    a = ConnectionContext('server', 'executor', 'ws', 'a', 'wa', 'subject', harness_id='codex_app_server')
    b = ConnectionContext('server', 'executor', 'ws', 'b', 'wb', 'subject', harness_id='codex_app_server')
    question = occurrence(kind='native_question_pending', source_type='execution_native_request', source_id='qa',
        episode=1, source_revision=1, first_detected_at=NOW, last_changed_at=NOW,
        workspace_id='ws', agent_id='subject', executor_id='executor', session_id='sa', operation_id='opa',
        category='action_required', allowed_actions=['respond_native'])
    session = SessionContext('server', 'executor', 'ws', 'sa', 'a', 'wa', 'subject', 'ACTIVE')
    entry = EntryRecord('logical-work', 'work', dict(type='direct_operation', id='opa', revision='r'),
        'ws', 'subject', 'Question work', 'awaiting_operator', 'confirmed', None,
        sessions=(session,), attention=[question], registered_connections=(a,))
    operation = dict(asdict(a), family='operation', session_id='sa', operation_id='opa',
        admission_state='ADMITTED', stage='RUNNING', dispatch_state='DISPATCHED', received_at=NOW)
    request = dict(asdict(a), family='request', session_id='sa', operation_id='opa', request_id='qa',
        request_revision=1, state='PENDING', expires_at='2026-11-16T13:00:00.000000Z', stream_epoch='epoch',
        session_stream_epoch='epoch', method='item/tool/requestUserInput', is_blocking=1, approval_status='pending', decided_at=None)
    sources = dict.fromkeys(('work', 'results', 'attention', 'connections', 'sessions', 'correlations', 'external'), 'ready')
    relation = EntryRelations([entry], [], sources, 2, (a, b), [operation, request])
    return relation, entry, operation, request, a, b


def read(relation):
    return page(relation, scope=filters({'quick': 'all'}), server_id='server', principal='human', now=NOW, limit=100)


def harnesses(value):
    return {item['connection']['binding_id']: (column, item) for column, lane in value['columns'].items()
            for item in lane['items'] if item['kind'] == 'harness'}


def test_confirmed_blocking_moves_only_own_harness_and_snooze_does_not_resume_it():
    relation, entry, _, _, _, _ = setup_facts()
    first = read(relation)
    known = harnesses(first)
    assert known['a'][0] == 'needs_you' and known['a'][1]['blocks_harness'] is True
    assert known['a'][1]['activity_state'] == 'waiting_for_user'
    assert known['b'][0] == 'active'
    assert not [item for item in first['columns']['needs_you']['items'] if item['kind'] == 'request']
    entry.attention[0] = with_preferences(entry.attention[0], snoozed_until='2026-11-16T12:30:00.000000Z', now=NOW)
    snoozed = harnesses(read(relation))['a']
    assert snoozed[0] == 'needs_you' and snoozed[1]['blocks_harness'] is True
    assert snoozed[1]['reminder_snoozed'] is True
    assert snoozed[1]['blocking_requests'][0]['notification_visible'] is False


def test_another_execution_keeps_harness_active_and_request_independent():
    relation, _, operation, _, _, _ = setup_facts()
    relation.harness_blocking.append(dict(operation, session_id='other-session', operation_id='other-operation'))
    value = read(relation)
    own = harnesses(value)['a']
    assert own[0] == 'active' and own[1]['blocks_harness'] is False and own[1]['activity_state'] == 'working'
    requests = [item for item in value['columns']['needs_you']['items'] if item['kind'] == 'request']
    assert len(requests) == 1 and requests[0]['blocks_harness'] is False
    assert [ref['connection']['binding_id'] for ref in requests[0]['harness_refs']] == ['a']


def test_explicit_nonblocking_question_is_independent_of_running_harness():
    relation, _, _, request, _, _ = setup_facts()
    request['is_blocking'] = 0
    value = read(relation)
    own = harnesses(value)['a']
    assert own[0] == 'active' and own[1]['blocks_harness'] is False
    assert any(item['kind'] == 'request' for item in value['columns']['needs_you']['items'])


def test_reported_finish_is_a_delivery_without_invented_harness_or_success():
    relation, entry, _, _, _, _ = setup_facts()
    report = occurrence(kind='external_completion_unseen', source_type='external_observation', source_id='observed',
        episode=1, source_revision=1, first_detected_at=NOW, last_changed_at=NOW,
        workspace_id='ws', resolution='resolved', active=True, allowed_actions=['inspect_external_observation'])
    report = with_preferences(report, now=NOW)
    entry.attention.append(report)
    value = read(relation)
    reported = next(item for item in value['columns']['results']['items'] if item['completion_evidence'] == 'reported')
    assert reported['result'] is None and reported['report']['attention_id'] == report['attention_id']
    assert reported['harness_refs'] == []
    assert value['summary']['results']['value'] == 1
    assert value['delivery_counts'] == dict(canonical=0, reported=1, total_is_exact=True)


def test_metadata_row_order_does_not_change_global_or_detail_revision():
    relation, _, _, _, _, _ = setup_facts()
    first = read(relation)
    relation.harness_blocking.reverse()
    second = read(relation)
    assert first['revision'] == second['revision']
    assert first['entry_revision'] == second['entry_revision']


@pytest.mark.parametrize('change', ['unknown-method', 'stale', 'expired', 'epoch', 'missing-metadata', 'partial-source', 'outcome-unknown'])
def test_missing_or_stale_proof_never_claims_global_pause_or_native_resume(change):
    relation, entry, operation, request, _, _ = setup_facts()
    if change == 'unknown-method':
        request.update(method='unproven/approval', is_blocking=None)
    elif change == 'stale':
        entry.attention[0].update(freshness='stale', category='watch')
    elif change == 'expired':
        request['expires_at'] = NOW
        entry.attention[0].update(resolution='expired', active=False, category='watch')
    elif change == 'epoch':
        request['session_stream_epoch'] = 'other-epoch'
    elif change == 'missing-metadata':
        relation.harness_blocking = None
    elif change == 'outcome-unknown':
        operation['stage'] = 'OUTCOME_UNKNOWN'
    else:
        relation.source_status['correlations'] = 'unavailable'
    own = harnesses(read(relation))['a']
    assert own[0] == 'active' and own[1]['blocks_harness'] is None
    assert own[1]['activity_state'] == 'unknown'


def test_decision_recorded_is_awaiting_confirmation_not_native_success():
    relation, entry, _, request, _, _ = setup_facts()
    request.update(state='DECIDED', approval_status='approved', decided_at='2026-11-16T12:00:01.000000Z')
    entry.attention[0].update(resolution='resolved', active=False, category='watch', allowed_actions=['inspect_approval'])
    entry.display_state = 'running'  # An old RUNNING receipt is insufficient.
    own = harnesses(read(relation))['a'][1]
    assert own['blocks_harness'] is None and own['activity_state'] == 'awaiting_confirmation'
    assert own['blocking_requests'] == []


def test_shared_work_does_not_share_request_scope_and_delivery_remains_independent():
    relation, entry, operation, _, a, b = setup_facts()
    entry.registered_connections = (a, b)
    relation.harness_blocking.append(dict(operation, **asdict(b), session_id='sb', operation_id='opb'))
    entry.results = [dict(id='delivery', created_at=NOW, view_state='unseen', detail_target=None, attention=None, outcome='FAILED')]
    value = read(relation)
    known = harnesses(value)
    assert known['a'][0] == 'needs_you' and known['b'][0] == 'active'
    assert known['a'][1]['blocking_requests'][0]['harness_refs'][0]['connection']['binding_id'] == 'a'
    assert known['b'][1]['blocking_requests'] == []
    assert not [e for e in known['b'][1]['events_preview'] if e['kind'] == 'attention']
    assert known['b'][1]['events_summary']['attention'] == 0
    assert known['b'][1]['summary']['occurrences']['value'] == 0
    assert known['a'][1]['summary']['occurrences']['value'] == 1
    deliveries = value['columns']['results']['items']
    assert len(deliveries) == 1 and deliveries[0]['kind'] == 'delivery'
    assert deliveries[0]['result']['outcome'] == 'FAILED' and deliveries[0]['completion_evidence'] == 'canonical'
    assert {ref['connection']['binding_id'] for ref in deliveries[0]['harness_refs']} == {'a', 'b'}
    assert value['summary']['activities']['value'] == 1 and value['summary']['results']['value'] == 1
