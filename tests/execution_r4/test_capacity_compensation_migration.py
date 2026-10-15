"""Rebuild constraints without losing existing committed or uncertain attempts."""
import sqlite3

import pytest

from okto_nexus.adapters.outbound.sqlite.migrations import _default_migrations_dir


def test_capacity_compensation_migration_preserves_rows_and_operation_history():
    conn = sqlite3.connect(':memory:')
    conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript('CREATE TABLE handoffs(handoff_id TEXT PRIMARY KEY);'
        'CREATE TABLE delivery_outbox(operation_id TEXT PRIMARY KEY);'
        'CREATE TABLE execution_sessions(server_id TEXT,executor_id TEXT,session_id TEXT,'
        'PRIMARY KEY(server_id,executor_id,session_id));')
    root = _default_migrations_dir()
    for name in ('131_execution_capacity_admissions.sql', '132_handoff_runtime_attempts.sql'):
        conn.executescript((root / name).read_text(encoding='utf-8'))
    conn.execute("INSERT INTO handoffs VALUES('handoff')")
    for i, state in enumerate(('WAITING_CONSUMPTION', 'CONSUMED', 'NEEDS_RECONCILIATION')):
        op, attempt, session = f'op{i}', f'attempt{i}', f'session{i}'
        conn.execute('INSERT INTO delivery_outbox VALUES(?)', (op,))
        conn.execute("INSERT INTO execution_sessions VALUES('server','executor',?)", (session,))
        conn.execute('INSERT INTO execution_capacity_admissions VALUES(?,?,?,?,?,?,?,?,?,?)',
            (op, attempt, 'server', 'executor', session, '{}', '{}', state, None, 'now'))
        conn.execute('INSERT INTO handoff_runtime_attempts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (attempt, 'workspace', 'handoff', f'agent{i}', 0, '{}', '{}', '{}', op,
             'CLAIM_COMMITTED', 'ACQUIRE', 1, 1, None, 'now', 'now'))
    tables = ('execution_capacity_admissions', 'handoff_runtime_attempts')
    before = {table: conn.execute(f'SELECT * FROM {table} ORDER BY attempt_id').fetchall() for table in tables}
    conn.executescript((root / '137_capacity_admission_compensation.sql').read_text(encoding='utf-8'))
    assert {table: conn.execute(f'SELECT * FROM {table} ORDER BY attempt_id').fetchall() for table in tables} == before
    # Keep the original operation FK when retiring the candidate; never erase
    # history just to evade the unique active-agent constraint.
    conn.execute("UPDATE handoff_runtime_attempts SET state='CANCELLED_NO_EFFECT',active=0,disposition='RELEASE' "
                 "WHERE attempt_id='attempt0'")
    assert conn.execute("SELECT operation_id FROM handoff_runtime_attempts WHERE attempt_id='attempt0'").fetchone()[0] == 'op0'
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE handoff_runtime_attempts SET state='NOT_AVAILABLE' WHERE attempt_id='attempt0'")
    conn.execute("UPDATE execution_capacity_admissions SET state='CANCELLED_NO_EFFECT' WHERE attempt_id='attempt0'")
    conn.execute("INSERT INTO execution_capacity_compensations VALUES('op0','{}','system','EXPIRED_UNCONSUMED','now')")
    assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    conn.close()
