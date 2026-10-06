"""Invalidate routing authority without claiming that a remote process exited."""


def invalidate_sessions(conn, *, now, grant_id=None, endpoint_id=None):
    if (grant_id is None) == (endpoint_id is None):
        raise ValueError('Select exactly one revocation scope.')
    if grant_id is not None:
        sessions = conn.execute('SELECT DISTINCT server_id,executor_id,session_id FROM execution_leases WHERE grant_id=?', (grant_id,)).fetchall()
    else:
        sessions = conn.execute('SELECT s.server_id,s.executor_id,s.session_id FROM execution_sessions s '
            'JOIN execution_bindings b USING(server_id,executor_id,binding_id) WHERE b.endpoint_id=?', (endpoint_id,)).fetchall()
    for row in sessions:
        key = tuple(row)
        conn.execute("UPDATE execution_sessions SET lease_state='REVOKED' WHERE server_id=? AND executor_id=? AND session_id=?", key)
        conn.execute("UPDATE execution_leases SET status='REVOKED' WHERE server_id=? AND executor_id=? AND session_id=?", key)
        conn.execute('UPDATE execution_session_capabilities SET revoked_at=? WHERE server_id=? AND executor_id=? AND session_id=? AND revoked_at IS NULL', (now, *key))


def repair_revoked_sessions(conn, *, now):
    """Repair preexisting revocations at startup, without replaying any work."""
    for row in conn.execute("SELECT endpoint_id FROM agent_endpoints WHERE activation_state='revoked'").fetchall():
        invalidate_sessions(conn, endpoint_id=row[0], now=now)
    for row in conn.execute('SELECT DISTINCT g.grant_id FROM runtime_execution_grants g '
            'JOIN execution_leases l ON l.grant_id=g.grant_id WHERE g.revoked_at IS NOT NULL').fetchall():
        invalidate_sessions(conn, grant_id=row[0], now=now)
