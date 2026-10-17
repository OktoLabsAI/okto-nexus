"""Bind a Core ledger identity to this Server's reset generation."""
from nexus_connector_core import CoreError


def bind_embedded_store(conn, *, store_id, recorded_at):
    if (type(store_id) is not str or len(store_id) != 38
            or not store_id.startswith('store_')
            or any(char not in '0123456789abcdef' for char in store_id[6:])):
        raise CoreError('JOURNAL_UNAVAILABLE', 'embedded_store_binding')
    generation = conn.execute('SELECT generation FROM runtime_reset_generation WHERE singleton=1').fetchone()[0]
    prior = conn.execute('SELECT store_id FROM execution_embedded_store_bindings '
        'WHERE reset_generation=?', (generation,)).fetchone()
    if prior is not None:
        if prior[0] != store_id:
            raise CoreError('PROFILE_DRIFT', 'embedded_store_binding')
        return False
    conn.execute('INSERT INTO execution_embedded_store_bindings '
        '(reset_generation,store_id,bound_at) VALUES(?,?,?)', (generation, store_id, recorded_at))
    return True


def require_no_missing_store(conn):
    """Only an entirely fresh generation may create its first ledger."""
    generation = conn.execute('SELECT generation FROM runtime_reset_generation WHERE singleton=1').fetchone()[0]
    if conn.execute('SELECT 1 FROM execution_embedded_store_bindings '
            'WHERE reset_generation=?', (generation,)).fetchone():
        raise CoreError('JOURNAL_UNAVAILABLE', 'embedded_store_binding')
    if (conn.execute('SELECT 1 FROM execution_sessions LIMIT 1').fetchone() or
            conn.execute('SELECT 1 FROM execution_operations LIMIT 1').fetchone()):
        raise CoreError('JOURNAL_UNAVAILABLE', 'embedded_store_binding')
