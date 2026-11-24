from contextlib import closing
import json
import sqlite3

import pytest

from tools.si038_codex_usage import TurnUsage, UnconfirmedUsage, read_turn_usage


SCOPE = ('server', 'executor', 'session', 'epoch')
USAGE_NOTIFICATION = 'thread/tokenUsage/updated'


def event(turn, *, operation=None, phase=None, outcome=None, tokens=None, thread='thread'):
    payload = dict(thread_id=thread, turn_id=turn, delivery_phase=phase, delivery_outcome=outcome)
    if tokens is not None:
        payload['tokenUsage'] = {'total': dict(totalTokens=tokens, inputTokens=tokens, outputTokens=0,
                                             cachedInputTokens=0, reasoningOutputTokens=0)}
    return json.dumps(dict(operation_id=operation, payload=payload,
                           native_type=USAGE_NOTIFICATION if tokens is not None else None))


def journal(tmp_path, events, *, gap=False):
    path = tmp_path / 'journal.db'
    with closing(sqlite3.connect(path)) as db:
        db.executescript('''CREATE TABLE event_streams (server_id,executor_id,session_id,stream_epoch,
                             next_sequence,compacted_sequence);
            CREATE TABLE events (server_id,executor_id,session_id,stream_epoch,sequence,body);''')
        db.execute('INSERT INTO event_streams VALUES (?,?,?,?,?,?)', (*SCOPE, len(events) + 1, int(gap)))
        db.executemany('INSERT INTO events VALUES (?,?,?,?,?,?)',
                       ((*SCOPE, i, body) for i, body in enumerate(events, 1)))
        db.commit()
    return path


def test_read_only_groups_cumulative_reports_by_exact_turn(tmp_path):
    path = journal(tmp_path, [event('one', operation='a', phase='started'), event('one', tokens=105),
        event('one', operation='a', phase='terminal', outcome='success'),
        event('two', operation='b', phase='started'), event('two', tokens=315), event('two', tokens=630),
        event('two', operation='b', phase='terminal', outcome='success'),
        event('three', operation='c', phase='started'), event('three', tokens=1050)])
    original = path.read_bytes()
    assert read_turn_usage(path, SCOPE, thread_id='thread', operation_id='a') == TurnUsage('one', 105, 'success')
    assert read_turn_usage(path, SCOPE, thread_id='thread', operation_id='b') == TurnUsage('two', 525, 'success')
    assert read_turn_usage(path, SCOPE, thread_id='thread', operation_id='c') == TurnUsage('three', 420, None)
    assert path.read_bytes() == original


def test_old_usage_cannot_confirm_a_new_terminal_turn(tmp_path):
    path = journal(tmp_path, [event('one', operation='a', phase='started'), event('one', tokens=105),
        event('one', operation='a', phase='terminal', outcome='success'),
        event('two', operation='b', phase='started'), event('one', tokens=150),
        event('two', operation='b', phase='terminal', outcome='success')])
    assert read_turn_usage(path, SCOPE, thread_id='thread', operation_id='b') is None
    assert read_turn_usage(path, (*SCOPE[:3], 'other'), thread_id='thread', operation_id='a') is None


@pytest.mark.parametrize('payload', [
    {},
    {'tokenUsage': None},
    {'tokenUsage': {}},
    {'tokenUsage': {'total': None}},
    {'tokenUsage': {'total': json.dumps(dict(totalTokens=152, inputTokens=150, outputTokens=2,
                                            cachedInputTokens=0, reasoningOutputTokens=0))}},
], ids=['missing-report', 'null-report', 'missing-total', 'null-total', 'string-total'])
def test_malformed_late_notification_cannot_reuse_an_old_total(tmp_path, payload):
    late = json.dumps(dict(native_type=USAGE_NOTIFICATION, payload=dict(thread_id='thread', turn_id='one', **payload)))
    path = journal(tmp_path, [
        event('one', operation='a', phase='started'),
        event('one', tokens=105),
        event('one', operation='a', phase='terminal', outcome='success'),
        late,
    ])
    original = path.read_bytes()
    with pytest.raises(UnconfirmedUsage, match='INVALID_USAGE_COUNTER'):
        read_turn_usage(path, SCOPE, thread_id='thread', operation_id='a')
    assert path.read_bytes() == original


def test_counter_in_another_notification_cannot_be_attributed_to_the_turn(tmp_path):
    bogus = json.loads(event('one', tokens=105))
    bogus['native_type'] = 'turn/plan/updated'
    path = journal(tmp_path, [event('one', operation='a', phase='started'), json.dumps(bogus)])
    with pytest.raises(UnconfirmedUsage, match='UNEXPECTED_USAGE_NOTIFICATION'):
        read_turn_usage(path, SCOPE, thread_id='thread', operation_id='a')


@pytest.mark.parametrize('case', [dict(operation='other'), dict(thread='other')])
def test_mismatched_report_fails_closed(tmp_path, case):
    path = journal(tmp_path, [event('one', operation='a', phase='started'), event('one', tokens=105, **case)])
    with pytest.raises(UnconfirmedUsage, match='USAGE_TURN_UNCORRELATED'):
        read_turn_usage(path, SCOPE, thread_id='thread', operation_id='a')


def test_regression_and_missing_history_fail_closed(tmp_path):
    path = journal(tmp_path, [event('one', operation='a', phase='started'), event('one', tokens=105),
                             event('one', tokens=104)])
    with pytest.raises(UnconfirmedUsage, match='USAGE_COUNTER_REGRESSED'):
        read_turn_usage(path, SCOPE, thread_id='thread', operation_id='a')
    with closing(sqlite3.connect(path)) as db:
        db.execute('UPDATE event_streams SET compacted_sequence=1')
        db.commit()
    with pytest.raises(UnconfirmedUsage, match='JOURNAL_COVERAGE_GAP'):
        read_turn_usage(path, SCOPE, thread_id='thread', operation_id='a')
