"""Result-source rebuild preserves live legacy references and rolls back safely."""
import sqlite3
from pathlib import Path

import pytest
import okto_nexus
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner, _split_statements
from okto_nexus.config import NexusConfig
from okto_nexus.errors import OktoNexusError
from test_pr34_remediation import runtime as runtime_fixture, send_message
from test_runtime_commands import codex_session
from test_runtime_result_publication import result

runtime = runtime_fixture


def test_result_rebuild_preserves_published_history_and_causal_foreign_keys(runtime, tmp_path):
    codex_session(runtime)
    sent = send_message(runtime, body='Historical result and references')
    published = result(runtime, sent['runtime_operations'][0], 'PUBLISHED')
    config = NexusConfig(home_dir=tmp_path / 'migration-copy')
    factory = ConnectionFactory(config)
    migrations = Path(okto_nexus.__file__).parent / 'migrations'
    old = sqlite3.connect(':memory:')
    for path in sorted(migrations.glob('[0-9]*.sql')):
        if int(path.name.split('_')[0]) >= 96:
            continue
        for statement in _split_statements(path.read_text()):
            old.execute(statement)
    schema = old.execute("SELECT sql FROM sqlite_master WHERE name='runtime_results'").fetchone()[0]
    indexes = [r[0] for r in old.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='runtime_results' AND sql IS NOT NULL")]
    columns = ','.join(r[1] for r in old.execute('PRAGMA table_info(runtime_results)'))
    old.close()
    with sqlite3.connect(config.db_path) as target:
        with runtime[0].connection_factory.unit_of_work(write=False) as uow:
            uow.connection.backup(target)
        target.execute('PRAGMA foreign_keys=OFF')
        target.execute(schema.replace('CREATE TABLE runtime_results', 'CREATE TABLE prior_results', 1))
        target.execute(f'INSERT INTO prior_results({columns}) SELECT {columns} FROM runtime_results')
        target.execute('DROP TABLE runtime_results')
        target.execute('ALTER TABLE prior_results RENAME TO runtime_results')
        for sql in indexes:
            target.execute(sql)
        target.execute('DELETE FROM schema_migrations WHERE version=96')
        expected = target.execute(f'SELECT {columns} FROM runtime_results ORDER BY result_id').fetchall()
        causal = target.execute('SELECT * FROM runtime_message_causality ORDER BY message_id').fetchall()
        assert any(r[-1] == published['result_id'] for r in causal)
        assert target.execute('PRAGMA foreign_key_check').fetchall() == []
    assert MigrationRunner(factory).apply() == [96]
    assert MigrationRunner(factory).apply() == []
    with factory.unit_of_work(write=False) as uow:
        assert [tuple(r) for r in uow.connection.execute(f'SELECT {columns} FROM runtime_results ORDER BY result_id')] == expected
        assert [tuple(r) for r in uow.connection.execute('SELECT * FROM runtime_message_causality ORDER BY message_id')] == causal
        assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []
        assert uow.connection.execute('PRAGMA foreign_keys').fetchone()[0] == 1


def test_invalid_rebuild_rolls_back_and_restores_foreign_key_enforcement(tmp_path):
    config = NexusConfig(home_dir=tmp_path / 'bad-migration')
    factory = ConnectionFactory(config)
    script = tmp_path / '002_invalid.sql'
    script.write_text('-- foreign-key-rebuild\n'
        'CREATE TABLE replacement(id INTEGER PRIMARY KEY);\n'
        'INSERT INTO replacement VALUES(2);\n'
        'DROP TABLE parent;\n'
        'ALTER TABLE replacement RENAME TO parent;\n')
    conn = factory.get_connection()
    try:
        conn.executescript('CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,applied_at TEXT);'
            'INSERT INTO schema_migrations VALUES(1,\'before\');'
            'CREATE TABLE parent(id INTEGER PRIMARY KEY); INSERT INTO parent VALUES(1);'
            'CREATE TABLE child(parent_id INTEGER REFERENCES parent(id)); INSERT INTO child VALUES(1);')
        with pytest.raises(OktoNexusError, match='Failed to apply migration'):
            MigrationRunner(factory)._apply_one(conn, 2, script)
        assert conn.execute('SELECT id FROM parent').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0] == 1
        assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
    finally:
        conn.close()
