import pytest
import sqlite3
from types import SimpleNamespace
from okto_nexus.application.runtime_results import RuntimeResultService
from okto_nexus.adapters.outbound.sqlite.observability_repo import SqliteObservabilityQueries


@pytest.mark.parametrize('outcome', ['success', 'interrupted', 'failed'])
@pytest.mark.parametrize('size', [0, 43347, 96917])
def test_result_labels_follow_terminal_outcome_and_preserve_artifact_threshold(outcome, size):
    row = dict(result_id='result-test', output_text='x' * size, output_truncated=False,
               delivery_outcome=outcome, root_realpath='workspace', recipient_agent_id='Pi',
               recipient_id='operator', channel_id=None, parent_id='message', notification_config='{}')
    result = RuntimeResultService.arguments(row)
    assert bool(result['artifacts']) == (size > 60000)
    if outcome == 'success':
        assert result['subject'] == ('x' * 80 if size else 'Runtime result')
        assert not result['body'].startswith('> **Execution')
    else:
        assert outcome in result['subject']
        assert result['body'].startswith('> **Execution' if size else 'Execution')
        if size:
            assert 'must not be treated as a complete response' in result['body']
    assert len(result['body'].encode()) < 65536


def _result_row(output_text, outcome='success'):
    return dict(result_id='result-test', output_text=output_text, output_truncated=False,
                delivery_outcome=outcome, root_realpath='workspace', recipient_agent_id='Pi',
                recipient_id='operator', channel_id=None, parent_id='message', notification_config='{}')


def test_success_subject_is_first_non_blank_line_of_output():
    result = RuntimeResultService.arguments(_result_row('\n  Milestone: draft PR open \nDetails follow'))
    assert result['subject'] == 'Milestone: draft PR open'


@pytest.mark.parametrize('output', [None, '', '  \n '])
def test_success_subject_stays_generic_without_output(output):
    assert RuntimeResultService.arguments(_result_row(output))['subject'] == 'Runtime result'


def test_partial_outcome_subjects_ignore_output_text():
    result = RuntimeResultService.arguments(_result_row('First line\nrest', outcome='failed'))
    assert result['subject'] == 'Runtime failed \u2014 partial output'


def _memory_db():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.executescript('''
        CREATE TABLE messages(message_id TEXT,workspace_id TEXT,channel_id TEXT,from_agent_id TEXT,
            created_at TEXT,subject TEXT,body TEXT,target TEXT,artifacts TEXT,trace_id TEXT);
        CREATE TABLE message_deliveries(delivery_id TEXT,message_id TEXT,recipient_agent_id TEXT,
            status TEXT,created_at TEXT,delivered_at TEXT,read_at TEXT);
        CREATE TABLE runtime_pending_deliveries(delivery_id TEXT,status TEXT);
        CREATE TABLE runtime_results(publication_message_id TEXT,delivery_outcome TEXT,output_truncated INTEGER);
    ''')
    return db


def _page(db, **kwargs):
    return SqliteObservabilityQueries().messages_page(SimpleNamespace(connection=db),
        workspace_id='one', agent_id=None, channel_id=None, lane=None, since_iso=None,
        until_iso=None, page=1, page_size=50, **kwargs)


def test_messages_page_hides_receipts_by_default_and_keeps_odd_bodies():
    db = _memory_db()
    receipt = '{"kind": "message.read_receipt", "read_by": "Pi"}'
    rows = [('ordinary', 'plain text'), ('json', '{"kind": "other"}'), ('null', None),
            ('mention', 'about message.read_receipt in prose'), ('receipt', receipt),
            ('array', '[1, 2, "message.read_receipt"]')]
    for message, body in rows:
        db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?,?)',
            (message, 'one', None, 'Pi', '2026-10-16', 'S', body, '{}', '[]', None))
    try:
        items, total = _page(db)
        assert total == 5 and 'receipt' not in {item['message_id'] for item in items}
        assert {item['kind'] for item in items} == {'message'}
        items, total = _page(db, include_receipts=True)
        assert total == 6
        assert {item['message_id']: item['kind'] for item in items}['receipt'] == 'receipt'
        items, total = _page(db, message_id='receipt')
        assert total == 1 and items[0]['kind'] == 'receipt'
    finally:
        db.close()


def test_messages_page_preview_is_first_120_characters():
    db = _memory_db()
    db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?,?)',
        ('long', 'one', None, 'Pi', '2026-10-16', 'S', 'a' * 300, '{}', '[]', None))
    try:
        items, _ = _page(db)
        assert items[0]['preview'] == 'a' * 120
    finally:
        db.close()


def test_history_uses_recorded_outcome_without_rewriting_or_trusting_message_text():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.executescript('''
        CREATE TABLE messages(message_id TEXT,workspace_id TEXT,channel_id TEXT,from_agent_id TEXT,
            created_at TEXT,subject TEXT,body TEXT,target TEXT,artifacts TEXT,trace_id TEXT);
        CREATE TABLE message_deliveries(delivery_id TEXT,message_id TEXT,recipient_agent_id TEXT,
            status TEXT,created_at TEXT,delivered_at TEXT,read_at TEXT);
        CREATE TABLE runtime_pending_deliveries(delivery_id TEXT,status TEXT);
        CREATE TABLE runtime_results(publication_message_id TEXT,delivery_outcome TEXT,output_truncated INTEGER);
    ''')
    try:
        for message, workspace in [('partial', 'one'), ('success', 'one'), ('ordinary', 'one'), ('private', 'two')]:
            db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?,?)',
                (message, workspace, None, 'Pi', '2026-10-16', 'Runtime result', 'Complete file', '{}', '[]', None))
        db.executemany('INSERT INTO runtime_results VALUES(?,?,?)',
            [('partial', 'interrupted', 0), ('success', 'success', 0), ('private', 'failed', 0)])
        db.commit()
        db.execute('PRAGMA query_only=ON')
        items, total = SqliteObservabilityQueries().messages_page(SimpleNamespace(connection=db),
            workspace_id='one', agent_id=None, channel_id=None, lane=None, since_iso=None,
            until_iso=None, page=1, page_size=50, include_body=True)
        rows = {item['message_id']: item for item in items}
        assert total == 3 and 'private' not in rows
        assert rows['partial']['runtime_result'] == dict(outcome='interrupted', partial=True)
        assert rows['success']['runtime_result'] == dict(outcome='success', partial=False)
        assert 'runtime_result' not in rows['ordinary']
        assert all(item['body'] == 'Complete file' for item in items)
    finally:
        db.close()
