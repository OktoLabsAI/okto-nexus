"""A previously observed physical ledger cannot be silently replaced."""
import sqlite3

import pytest
from importlib.resources import files
from nexus_connector_core import CoreError

from okto_nexus.adapters.outbound.sqlite.execution_embedded_store_binding import (
    bind_embedded_store, require_no_missing_store,
)


def database():
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE runtime_reset_generation '
        '(singleton INTEGER PRIMARY KEY, generation INTEGER NOT NULL)')
    conn.execute('INSERT INTO runtime_reset_generation VALUES(1,0)')
    conn.execute('CREATE TABLE execution_sessions (session_id TEXT)')
    conn.execute('CREATE TABLE execution_operations (operation_id TEXT)')
    migration = files('okto_nexus').joinpath(
        'migrations/148_execution_embedded_store_binding.sql').read_text()
    conn.executescript(migration)
    return conn


def test_binding_is_immutable_within_reset_generation_and_reset_selects_new_store():
    with database() as conn:
        original = 'store_' + 'a' * 32
        replacement = 'store_' + 'b' * 32
        assert bind_embedded_store(conn, store_id=original, recorded_at='first')
        assert not bind_embedded_store(conn, store_id=original, recorded_at='second')
        assert conn.execute('SELECT bound_at FROM execution_embedded_store_bindings '
            'WHERE reset_generation=0').fetchone()[0] == 'first'
        with pytest.raises(CoreError, match='PROFILE_DRIFT'):
            bind_embedded_store(conn, store_id=replacement, recorded_at='forged')
        conn.execute('UPDATE runtime_reset_generation SET generation=1 WHERE singleton=1')
        assert bind_embedded_store(conn, store_id=replacement, recorded_at='reset')
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
