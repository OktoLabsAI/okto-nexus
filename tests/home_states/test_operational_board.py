"""Negotiated pages over complete synthetic metadata, not native proof."""
from dataclasses import replace

import pytest

from okto_nexus.domain import home_entry_pages
from okto_nexus.domain.attention import occurrence
from okto_nexus.domain.home_entries import EntryRecord
from okto_nexus.domain.home_entry_pages import filters
from okto_nexus.domain.home_harness_board import page
from okto_nexus.errors import OktoNexusError
from tests.home_states.test_operational_status import NOW, facts, question


def read(rel, **kwargs):
    return page(rel, scope=filters({'quick': 'all'}), server_id='server', principal='human', now=NOW,
                presentation_version=2, **kwargs)


def card(value):
    return next(item for lane in value['columns'].values() for item in lane['items'] if item['kind'] == 'harness')


def test_sessions_are_complete_paged_and_bound_to_card_version_principal():
    rel, _, session, _ = facts()
    rel.operational_sessions = tuple(replace(session, session_id=f's{i}') for i in range(7))
    first = read(rel, preview=2)
    item = card(first)
    assert item['sessions_total'] == 7 and len(item['sessions']) == 2 and item['has_more_sessions']
    seen = {s['session_id'] for s in item['sessions']}
    cursor = item['sessions_cursor']
    while cursor:
        more = read(rel, partition='sessions', card_id=item['id'], cursor=cursor, limit=2)
        assert more['partition'] == 'harness_sessions' and more['total'] == 7
        assert not seen.intersection(s['session_id'] for s in more['items'])
        seen.update(s['session_id'] for s in more['items'])
        cursor = more['next_cursor']
    assert len(seen) == 7
    with pytest.raises(OktoNexusError):
        page(rel, scope=filters({'quick': 'all'}), server_id='server', principal='other', now=NOW,
             presentation_version=2, partition='sessions', card_id=item['id'], cursor=item['sessions_cursor'])
    with pytest.raises(OktoNexusError):
        page(rel, scope=filters({'quick': 'all'}), server_id='server', principal='human', now=NOW,
             partition='sessions', card_id=item['id'])


def test_all_requests_are_reachable_beyond_bounded_blocker_preview():
    rel, c, _, _ = facts()
    o, r = question(rel, c)
    template = dict(o)
    for i in range(1, 7):
        q = occurrence(kind='native_question_pending', source_type='execution_native_request', source_id=f'r{i}',
            episode=1, source_revision=1, first_detected_at=NOW, last_changed_at=NOW,
            workspace_id='ws', agent_id='agent', executor_id='executor', session_id='session', operation_id='op',
            category='action_required', allowed_actions=['respond_native'])
        rel.entries.append(EntryRecord(f'e{i}', 'attention', {'type': 'execution_native_request', 'id': f'r{i}', 'revision': '1'},
            'ws', 'agent', 'Question', 'awaiting_operator', 'confirmed', None, attention=[q]))
        rel.harness_blocking.append(dict(r, request_id=f'r{i}'))
    first = read(rel, preview=2)
    item = card(first)
    assert item['operational_status']['pending_actions']['value'] == 7
    assert item['operational_status']['pending_by_kind']['question']['value'] == 7
    assert len(item['blocking_requests']) == len(item['blocking_request_ids']) == 2
    assert first['columns']['needs_you']['total'] == 1
    assert first['operational_summary']['pending_actions']['value'] == 7
    ids, cursor = set(), None
    while True:
        more = read(rel, partition='requests', card_id=item['id'], cursor=cursor, limit=2)
        assert more['total'] == 7
        for value in more['items']:
            assert value['blocks_session'] is True
            assert value['request']['attention_id'] not in ids
            ids.add(value['request']['attention_id'])
        cursor = more['next_cursor']
        if cursor is None:
            break
    assert len(ids) == 7 and o == template


def test_semantic_revision_ignores_arrival_time_but_expires_control_without_event():
    rel, _, session, op = facts()
    first = read(rel)
    op['received_at'] = '2026-11-17T12:00:30.000000Z'
    rel.operational_sessions = (replace(session, observed_at=op['received_at']),)
    second = read(rel)
    assert first['revision'] == second['revision']
    rel.operational_sessions = (replace(session, valid_until=NOW),)
    expired = read(rel)
    assert expired['revision'] != first['revision']
    assert card(expired)['operational_status']['activity'] == 'unknown'


def test_awaiting_confirmation_placement_never_fabricates_full_block():
    rel, c, _, _ = facts()
    o, _ = question(rel, c, state='DECIDED', decision_id='decision', native_operation_id='reply')
    o.update(category='watch', resolution='resolved', active=False, allowed_actions=['inspect_approval'])
    value = read(rel)
    item = card(value)
    assert value['columns']['needs_you']['items'] == [item]
    assert item['blocks_harness'] is None and item['placement_reason'] == 'awaiting_native_confirmation'
    assert item['operational_status']['pending_actions']['value'] == 0
    assert value['operational_summary']['resume_confirmations']['value'] == 1
    assert value['operational_summary']['pending_actions']['value'] == 0


def test_old_and_new_cursor_spaces_cannot_mix():
    rel, c, _, _op = facts()
    question(rel, c)
    # A second registered connection gives the active column a continuation.
    b = replace(c, binding_id='other')
    rel.connections += (b, replace(c, binding_id='third'))
    legacy = page(rel, scope=filters({'quick': 'all'}), server_id='server', principal='human', now=NOW, limit=1)
    assert 'operational_summary' not in legacy
    legacy_cursor = legacy['columns']['active']['next_cursor']
    assert legacy_cursor is not None
    with pytest.raises(OktoNexusError):
        read(rel, partition='column', column='active', cursor=legacy_cursor)


def test_board_child_related_cursor_uses_real_v2_entry_revision():
    rel, c, _, _ = facts()
    question(rel, c)
    entry = rel.entries[0]
    for i in range(4):
        extra = occurrence(kind='native_question_pending', source_type='execution_native_request', source_id=f'other{i}',
            episode=1, source_revision=1, first_detected_at=NOW, last_changed_at=NOW, workspace_id='ws',
            agent_id='agent', executor_id='executor', session_id='session', operation_id='op',
            category='action_required', allowed_actions=['respond_native'])
        entry.attention.append(extra)
    entry.registered_connections = (c,)
    root = read(rel)
    child = card(root)['children'][0]
    assert child['has_more_attention'] and child['attention_cursor']
    continuation = home_entry_pages.page(rel, scope=filters({'quick': 'all'}), server_id='server', principal='human',
        now=NOW, presentation_version=2, partition='attention', group_id=child['group_id'], entry_id=child['id'],
        cursor=child['attention_cursor'])
    assert continuation['revision'] == root['entry_revision']
    assert len(continuation['items']) == 2
    with pytest.raises(OktoNexusError):
        home_entry_pages.page(rel, scope=filters({'quick': 'all'}), server_id='server', principal='human', now=NOW,
            partition='attention', group_id=child['group_id'], entry_id=child['id'], cursor=child['attention_cursor'])


def test_unknown_runtime_does_not_synthesize_exact_zero_connection_counts():
    rel, _, session, _ = facts()
    rel.operational_sessions = (replace(session, control_current=False),)
    summary = read(rel)['operational_summary']
    assert summary['connected'] == {'value': None, 'total_is_exact': False}
    assert summary['idle'] == {'value': None, 'total_is_exact': False}
    assert summary['unconfirmed']['value'] == 1
