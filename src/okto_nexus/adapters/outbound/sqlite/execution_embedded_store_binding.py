"""Bind Core ledger identity and verified audit token to a reset generation."""
from nexus_connector_core import CoreError, JournalAuditAnchor


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


def registry_import_pending(conn, *, store_id):
    generation = conn.execute('SELECT generation FROM runtime_reset_generation WHERE singleton=1').fetchone()[0]
    row = conn.execute('SELECT store_id,registry_import_complete FROM execution_embedded_store_bindings '
        'WHERE reset_generation=?', (generation,)).fetchone()
    if row is None or row[0] != store_id:
        raise CoreError('PROFILE_DRIFT', 'embedded_store_binding')
    return not bool(row[1])


def complete_registry_import(conn, *, store_id):
    generation = conn.execute('SELECT generation FROM runtime_reset_generation WHERE singleton=1').fetchone()[0]
    if conn.execute('UPDATE execution_embedded_store_bindings SET registry_import_complete=1 '
            'WHERE reset_generation=? AND store_id=?', (generation, store_id)).rowcount != 1:
        raise CoreError('PROFILE_DRIFT', 'embedded_store_binding')


def stored_audit_anchor(conn, *, store_id):
    generation = conn.execute('SELECT generation FROM runtime_reset_generation WHERE singleton=1').fetchone()[0]
    row = conn.execute('SELECT store_id,registry_import_complete,audit_nonce,audit_revision,audit_digest,audit_completed_at '
        'FROM execution_embedded_store_bindings WHERE reset_generation=?', (generation,)).fetchone()
    if row is None or row[0] != store_id:
        raise CoreError('PROFILE_DRIFT', 'embedded_audit_anchor')
    if not row[1] and any(value is not None for value in row[2:]):
        raise CoreError('PROFILE_DRIFT', 'embedded_audit_anchor')
    if row[2] is None and any(value is not None for value in row[3:]):
        raise CoreError('PROFILE_DRIFT', 'embedded_audit_anchor')
    if not row[1] or row[2] is None:
        return None
    if (type(row[2]) is not str or not row[2].startswith('audit_') or len(row[2]) != 38
            or any(char not in '0123456789abcdef' for char in row[2][6:])
            or type(row[3]) is not int or row[3] < 0
            or type(row[4]) is not str or len(row[4]) != 64
            or any(char not in '0123456789abcdef' for char in row[4])
            or type(row[5]) is not str or not row[5]):
        raise CoreError('PROFILE_DRIFT', 'embedded_audit_anchor')
    return JournalAuditAnchor(row[0], row[2], row[3], row[4])


def record_audit_anchor(conn, *, anchor, recorded_at):
    if type(anchor) is not JournalAuditAnchor or type(recorded_at) is not str or not recorded_at:
        raise ValueError('Invalid embedded audit anchor.')
    stored_audit_anchor(conn, store_id=anchor.store_id)
    generation = conn.execute('SELECT generation FROM runtime_reset_generation WHERE singleton=1').fetchone()[0]
    if conn.execute('UPDATE execution_embedded_store_bindings SET '
            'audit_nonce=?,audit_revision=?,audit_digest=?,audit_completed_at=? '
            'WHERE reset_generation=? AND store_id=? AND registry_import_complete=1',
            (anchor.nonce, anchor.revision, anchor.digest, recorded_at,
             generation, anchor.store_id)).rowcount != 1:
        raise CoreError('PROFILE_DRIFT', 'embedded_audit_anchor')
