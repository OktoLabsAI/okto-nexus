import sqlite3

import pytest

from okto_nexus.application.execution_revocation import invalidate_sessions, repair_revoked_sessions


@pytest.mark.parametrize('scope', [{'grant_id': 'g'}, {'endpoint_id': 'ep'}])
def test_revocation_invalidates_only_scoped_sessions_and_credentials(scope):
    conn = sqlite3.connect(':memory:')
    conn.executescript('''
        CREATE TABLE execution_sessions(server_id,executor_id,session_id,binding_id,lease_state,lifecycle_state);
        CREATE TABLE execution_bindings(server_id,executor_id,binding_id,endpoint_id);
        CREATE TABLE execution_leases(server_id,executor_id,session_id,grant_id,status);
        CREATE TABLE execution_session_capabilities(server_id,executor_id,session_id,revoked_at);
        CREATE TABLE agent_endpoints(endpoint_id,activation_state);
        CREATE TABLE runtime_execution_grants(grant_id,revoked_at);
        INSERT INTO execution_sessions VALUES ('s','x','target','b','ACTIVE','READY'),('s','x','other','other','ACTIVE','READY');
        INSERT INTO execution_bindings VALUES ('s','x','b','ep'),('s','x','other','other');
        INSERT INTO execution_leases VALUES ('s','x','target','g','ACTIVE'),('s','x','other','other','ACTIVE');
        INSERT INTO execution_session_capabilities VALUES ('s','x','target',NULL),('s','x','other',NULL);
    ''')
    for _ in range(2):
        invalidate_sessions(conn, now='now', **scope)
    assert conn.execute('SELECT session_id,lease_state,lifecycle_state FROM execution_sessions ORDER BY session_id').fetchall() == [('other','ACTIVE','READY'),('target','REVOKED','READY')]
    assert conn.execute("SELECT status FROM execution_leases WHERE grant_id='g'").fetchone()[0] == 'REVOKED'
    assert conn.execute("SELECT revoked_at FROM execution_session_capabilities WHERE session_id='target'").fetchone()[0] == 'now'
    assert conn.execute("SELECT revoked_at FROM execution_session_capabilities WHERE session_id='other'").fetchone()[0] is None
    conn.execute("UPDATE execution_sessions SET lease_state='ACTIVE' WHERE session_id='target'")
    if 'grant_id' in scope:
        conn.execute("INSERT INTO runtime_execution_grants VALUES ('g','now')")
    else:
        conn.execute("INSERT INTO agent_endpoints VALUES ('ep','revoked')")
    repair_revoked_sessions(conn, now='restart')
    assert conn.execute("SELECT lease_state FROM execution_sessions WHERE session_id='target'").fetchone()[0] == 'REVOKED'
