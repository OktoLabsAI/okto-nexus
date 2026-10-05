"""Durable, namespaced sender-session provenance for runtime affinity."""
import json


def runtime_key(scope):
    # Executor and server IDs prevent native/session ID collisions across hosts.
    return json.dumps(['runtime', scope['server_id'], scope['executor_id'], scope['session_id']],
                      separators=(',', ':'))


def capture(conn, *, managed_binding=None, result_id=None, verified_session_id=None):
    """Call only after sender capability/result/session authorization succeeded."""
    if managed_binding:
        from .runtime_actor_authority import MANAGED_MESSAGE_PREFIX
        proof = json.loads(managed_binding[len(MANAGED_MESSAGE_PREFIX):])
        return runtime_key(proof['principal']['scope'])
    if result_id:
        row = conn.execute('SELECT r.runtime_session_id,e.server_id,e.executor_id,e.session_id '
            'FROM runtime_results r LEFT JOIN execution_results e '
            'ON e.server_id=r.canonical_server_id AND e.executor_id=r.canonical_executor_id '
            'AND e.operation_id=r.canonical_operation_id WHERE r.result_id=?', (result_id,)).fetchone()
        if row and row['session_id']:
            return runtime_key(row)
        if row and row['runtime_session_id']:
            return json.dumps(['legacy-runtime', row['runtime_session_id']], separators=(',', ':'))
    if verified_session_id:
        return json.dumps(['mcp', verified_session_id], separators=(',', ':'))
    return ''


def for_message(conn, message_id):
    row = conn.execute('SELECT source_session_key FROM execution_message_origins WHERE message_id=?',
                       (message_id,)).fetchone()
    return row[0] if row else ''
