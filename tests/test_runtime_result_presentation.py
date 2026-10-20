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
        assert result['subject'] == 'Runtime result'
        assert not result['body'].startswith('> **Execution')
    else:
        assert outcome in result['subject']
        assert result['body'].startswith('> **Execution' if size else 'Execution')
        if size:
            assert 'must not be treated as a complete response' in result['body']
    assert len(result['body'].encode()) < 65536


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
