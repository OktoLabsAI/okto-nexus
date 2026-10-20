import json
import sqlite3
import pytest

from okto_nexus.application.execution_released_closes import settle_released_closes


@pytest.mark.parametrize('variant', ['eligible', 'live', 'lease', 'generation', 'turn', 'receipt', 'pending', 'other_error', 'other_executor'])
def test_only_lost_close_of_proven_released_session_is_retired(variant):
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.executescript('''
        CREATE TABLE execution_operations(server_id,executor_id,session_id,operation_id,action,admission_state,expected_revisions_json);
        CREATE TABLE execution_sessions(server_id,executor_id,session_id,lifecycle_state,lease_state,owner_generation);
        CREATE TABLE execution_dispatch_outbox(server_id,executor_id,operation_id,dispatch_state,last_error,reserved_bytes,reservation_class,reserved_at);
        CREATE TABLE execution_receipts(server_id,executor_id,operation_id);
        INSERT INTO execution_operations VALUES('s','e','session','close','runtime.close','RECONCILING','{"session_owner_generation":1}');
        INSERT INTO execution_sessions VALUES('s','e','session','CLOSED','CLOSED',1);
        INSERT INTO execution_dispatch_outbox VALUES('s','e','close','RECONCILING','{"code":"DISPATCH_CONNECTION_LOST"}',100,'control','now');
    ''')
    changes = {
        'live': "UPDATE execution_sessions SET lifecycle_state='READY'",
        'lease': "UPDATE execution_sessions SET lease_state='ACTIVE'",
        'generation': 'UPDATE execution_sessions SET owner_generation=2',
        'turn': "UPDATE execution_operations SET action='turn.submit'",
        'receipt': "INSERT INTO execution_receipts VALUES('s','e','close')",
        'pending': "UPDATE execution_dispatch_outbox SET dispatch_state='PENDING'",
        'other_error': "UPDATE execution_dispatch_outbox SET last_error='{}'",
    }
    if variant in changes:
        c.execute(changes[variant])
    proof = {'ownership': {'process_state': 'EXITED', 'owner_generation': 1}, 'stream': {'sequence': 0}}
    for _ in range(2):
        settle_released_closes(c, server_id='s', executor_id='other' if variant == 'other_executor' else 'e', session_id='session', proof=proof)
    row = c.execute('SELECT * FROM execution_dispatch_outbox').fetchone()
    if variant == 'eligible':
        assert row['dispatch_state'] == 'RESOLVED_TERMINAL'
        error = json.loads(row['last_error'])
        assert error['possible_effect'] is True and error['retry_safe'] is False
        assert error['proof'] == proof
        assert error['code'] == 'CLOSE_OUTCOME_UNKNOWN_SESSION_RELEASED'
        assert row['reserved_bytes'] == 0
        assert c.execute('SELECT admission_state FROM execution_operations').fetchone()[0] == 'RESOLVED_TERMINAL'
        assert c.execute('SELECT count(*) FROM execution_receipts').fetchone()[0] == 0
    else:
        assert row['dispatch_state'] != 'RESOLVED_TERMINAL'
        assert c.execute('SELECT admission_state FROM execution_operations').fetchone()[0] == 'RECONCILING'
