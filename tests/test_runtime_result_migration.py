"""Result-source rebuild preserves live legacy references and rolls back safely."""
import sqlite3
from pathlib import Path

import pytest
import okto_nexus
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner, _split_statements
from okto_nexus.config import NexusConfig
from okto_nexus.errors import OktoNexusError
from test_pr34_remediation import runtime as runtime_fixture
from test_runtime_event_journal import historical_session, event

runtime = runtime_fixture


def test_result_rebuild_preserves_published_history_and_causal_foreign_keys(runtime, tmp_path):
    # Migrate real retained journal/result rows. Current Core results cannot be
    # inserted into the pre-96 schema, whose legacy event/session IDs are NOT NULL.
    deps = runtime[0]
    session = historical_session(runtime)
    deps.harness_supervisor.event_ingress.capture(event(session, text='Historical result and references'))
    from okto_nexus.domain.ids import resolve_workspace_id
    from okto_nexus.domain.base import iso_plus
    workspace = resolve_workspace_id(runtime[2])
    with deps.connection_factory.unit_of_work() as uow:
        now = deps.clock.now_iso()
        deps.repos.workspaces.upsert(uow, workspace_id=workspace, root_realpath=runtime[2])
        for message, actor in (('historical-source', 'caller'), ('historical-publication', 'worker')):
            deps.repos.messages.create(uow, message_id=message, workspace_id=workspace,
                from_agent_id=actor, subject='Historical result', body='Historical result and references')
        published = dict(uow.connection.execute('SELECT * FROM runtime_results').fetchone())
        uow.connection.execute("UPDATE runtime_results SET publication_state='PUBLISHED',publication_message_id='historical-publication',output_text=?",
            ('Historical result and references',))
        uow.connection.execute('INSERT INTO runtime_causal_roots(root_operation_id,workspace_id,actor_agent_id,'
            'created_at,deadline,max_depth,max_messages,max_executions,generated_messages,admitted_executions) '
            "VALUES('historical-root',?,'caller',?,?,3,5,5,1,1)", (workspace, now, iso_plus(now, 600)))
        uow.connection.execute("INSERT INTO runtime_message_causality VALUES('historical-source','historical-root',NULL,0,'entry',NULL)")
        uow.connection.execute("INSERT INTO runtime_message_causality VALUES('historical-publication','historical-root','historical-source',1,'continuation',?)",
            (published['result_id'],))
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
