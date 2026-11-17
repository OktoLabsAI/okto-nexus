"""Private progress proof does not substitute for currentness or authority."""
from dataclasses import replace

import pytest

from tests.home_states.test_operational_status import NOW, facts, question, reduce


@pytest.mark.parametrize('proof,expected', [(True, 'working'), (False, 'unknown'), (None, 'unknown'),
                                           (1, 'unknown'), ('true', 'unknown')])
def test_submitted_requires_strict_current_productive_fact(proof, expected):
    rel, c, _, op = facts()
    op.update(stage='SUBMITTED', productive_progress_current=proof)
    status = reduce(rel, c)[0]['operational_status']
    assert status['activity'] == expected
    assert status['running_sessions']['value'] == (1 if expected == 'working' else 0)


@pytest.mark.parametrize('fence', ['owner', 'epoch', 'lease', 'authority', 'runtime', 'control',
                                  'outcome_unknown', 'reconciling', 'blocked', 'confirmation'])
def test_productive_event_cannot_bypass_existing_fences(fence):
    rel, c, session, op = facts()
    op.update(stage='SUBMITTED', productive_progress_current=True)
    if fence == 'owner':
        op['owner_generation'] += 1
    elif fence == 'epoch':
        op['stream_epoch'] = 'old'
    elif fence == 'lease':
        rel.operational_sessions = (replace(session, valid_until=NOW),)
    elif fence in ('authority', 'runtime', 'control'):
        field = {'authority': 'authority_current', 'runtime': 'runtime_ready', 'control': 'control_current'}[fence]
        rel.operational_sessions = (replace(session, **{field: False}),)
    elif fence == 'outcome_unknown':
        op['stage'] = 'OUTCOME_UNKNOWN'
    elif fence == 'reconciling':
        op['dispatch_state'] = 'RECONCILING'
    elif fence == 'blocked':
        question(rel, c)
    else:
        o, _ = question(rel, c, state='DECIDED', decision_id='d', native_operation_id='write')
        o.update(category='watch', resolution='resolved', active=False, allowed_actions=['inspect_approval'])
    result = reduce(rel, c)[0]
    assert result['operational_status']['activity'] != 'working'
    assert result['operational_status']['running_sessions']['value'] in (0, None)


def test_blocked_a_and_submitted_progress_b_then_terminal_b_keep_distinct_dimensions():
    rel, c, session, op = facts()
    op.update(stage='SUBMITTED', productive_progress_current=True)
    question(rel, c)
    sibling = dict(op, operation_id='sibling-op', session_id='sibling')
    rel.operational_sessions += (replace(session, session_id='sibling'),)
    rel.harness_blocking.append(sibling)
    current = reduce(rel, c)[0]
    assert current['operational_status']['activity'] == 'working'
    assert current['operational_status']['blocking'] == 'partial'
    assert current['operational_status']['running_sessions']['value'] == 1
    assert current['blocks_harness'] is False and current['placement_reason'] == 'normal_monitoring'
    sibling['stage'] = 'SUCCEEDED'
    after = reduce(rel, c)[0]
    assert after['blocks_harness'] is True and after['placement_reason'] == 'human_block_confirmed'
    assert after['operational_status']['activity'] == 'waiting_user'
