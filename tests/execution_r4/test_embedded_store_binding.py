"""A previously observed physical ledger cannot be silently replaced."""
import sqlite3

import pytest
from importlib.resources import files
from nexus_connector_core import CoreError, JournalAuditAnchor

from okto_nexus.adapters.outbound.sqlite.execution_embedded_store_binding import (
    bind_embedded_store, require_no_missing_store,
    registry_import_pending, complete_registry_import,
    stored_audit_anchor, record_audit_anchor,
)


def database():
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE runtime_reset_generation '
        '(singleton INTEGER PRIMARY KEY, generation INTEGER NOT NULL)')
    conn.execute('INSERT INTO runtime_reset_generation VALUES(1,0)')
    conn.execute('CREATE TABLE execution_sessions (session_id TEXT)')
    conn.execute('CREATE TABLE execution_operations (operation_id TEXT)')
    for name in ('148_execution_embedded_store_binding.sql',
                 '149_execution_journal_registry_conversion.sql',
                 '150_execution_embedded_audit_anchor.sql'):
        migration = files('okto_nexus').joinpath('migrations', name)
        conn.executescript(migration.read_text())
    return conn


def test_binding_is_immutable_within_reset_generation_and_reset_selects_new_store():
    with database() as conn:
        original = 'store_' + 'a' * 32
        replacement = 'store_' + 'b' * 32
        assert bind_embedded_store(conn, store_id=original, recorded_at='first')
        assert registry_import_pending(conn, store_id=original)
        complete_registry_import(conn, store_id=original)
        assert not registry_import_pending(conn, store_id=original)
        assert not bind_embedded_store(conn, store_id=original, recorded_at='second')
        assert conn.execute('SELECT bound_at FROM execution_embedded_store_bindings '
            'WHERE reset_generation=0').fetchone()[0] == 'first'
        with pytest.raises(CoreError, match='PROFILE_DRIFT'):
            bind_embedded_store(conn, store_id=replacement, recorded_at='forged')
        conn.execute('UPDATE runtime_reset_generation SET generation=1 WHERE singleton=1')
        assert bind_embedded_store(conn, store_id=replacement, recorded_at='reset')
        assert registry_import_pending(conn, store_id=replacement)
        assert conn.execute('SELECT reset_generation,store_id FROM execution_embedded_store_bindings '
            'ORDER BY reset_generation').fetchall() == [(0, original), (1, replacement)]


def test_missing_bound_store_blocks_but_fresh_generation_can_start_empty():
    with database() as conn:
        require_no_missing_store(conn)
        bind_embedded_store(conn, store_id='store_' + 'a' * 32, recorded_at='first')
        with pytest.raises(CoreError, match='JOURNAL_UNAVAILABLE'):
            require_no_missing_store(conn)
        conn.execute('UPDATE runtime_reset_generation SET generation=1 WHERE singleton=1')
        require_no_missing_store(conn)


def test_invalid_core_store_identity_never_creates_a_binding():
    with database() as conn:
        with pytest.raises(CoreError, match='JOURNAL_UNAVAILABLE'):
            bind_embedded_store(conn, store_id='store_' + 'g' * 32, recorded_at='bad')
        assert conn.execute('SELECT COUNT(*) FROM execution_embedded_store_bindings').fetchone()[0] == 0


def test_unbound_store_with_history_cannot_be_recreated_as_empty():
    with database() as conn:
        conn.execute("INSERT INTO execution_sessions VALUES('previous')")
        with pytest.raises(CoreError, match='JOURNAL_UNAVAILABLE'):
            require_no_missing_store(conn)


def test_audit_anchor_requires_import_and_is_scoped_to_reset_generation():
    with database() as conn:
        store_id = 'store_' + 'a' * 32
        anchor = JournalAuditAnchor(store_id, 'audit_' + 'b' * 32, 3, 'c' * 64)
        bind_embedded_store(conn, store_id=store_id, recorded_at='first')
        assert stored_audit_anchor(conn, store_id=store_id) is None
        with pytest.raises(CoreError, match='PROFILE_DRIFT'):
            record_audit_anchor(conn, anchor=anchor, recorded_at='before-import')
        complete_registry_import(conn, store_id=store_id)
        record_audit_anchor(conn, anchor=anchor, recorded_at='after-import')
        assert stored_audit_anchor(conn, store_id=store_id) == anchor
        with pytest.raises(CoreError, match='PROFILE_DRIFT'):
            stored_audit_anchor(conn, store_id='store_' + 'd' * 32)
        conn.execute('UPDATE runtime_reset_generation SET generation=1 WHERE singleton=1')
        replacement = 'store_' + 'd' * 32
        bind_embedded_store(conn, store_id=replacement, recorded_at='reset')
        assert stored_audit_anchor(conn, store_id=replacement) is None
