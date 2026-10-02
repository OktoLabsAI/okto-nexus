"""Legacy scoped opening keys cannot replace the original agent credential."""
import hashlib
import sqlite3

import pytest

from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt


@pytest.mark.parametrize('actor', ['subject', 'operator'])
def test_scoped_key_issuance_and_opening_routes_are_removed(connected_local, actor):
    setup, binding, native = connected_local
    _, _, client, headers, *_ = setup
    assert client.post('/api/v1/agents/subject/connection-keys', headers=headers[actor],
        json={'endpoint_id': binding['endpoint_id']}).status_code in (404, 405)
    assert client.post('/api/v1/connections/open', headers=headers[actor], json={}).status_code in (404, 405)
    assert native.opens == 0
    opened = admit(setup, binding, 'original-agent-key', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    wait_receipt(setup, admit(setup, binding, 'original-agent-close', 'runtime.close',
        session_id=opened['session_id']), stages=('SUCCEEDED',))
    assert native.opens == 1


def test_retained_scoped_key_cannot_authenticate_or_resolve(connected_local):
    from okto_nexus.application.connection_policy import valid_connection_key
    setup, binding, native = connected_local
    deps, _, client, *_ = setup
    raw = 'nxsconn_retained_historical_test_credential'
    digest = hashlib.sha256(raw.encode()).hexdigest()
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('INSERT INTO agent_connection_keys '
            '(key_id,key_hash,agent_id,endpoint_id,endpoint_revision,created_at) VALUES (?,?,?,?,?,?)',
            ('retained-key', digest, 'subject', binding['endpoint_id'], 1, deps.clock.now_iso()))
        assert valid_connection_key(uow, digest, deps.clock.now_iso(), agents=deps.repos.agents) is None
    for path in ('/api/v1/connections/open', '/v1/runtime/intents:resolve'):
        response = client.post(path, headers={'Authorization': 'Bearer ' + raw}, json={})
        assert response.status_code in (401, 403, 404, 405), response.text
    assert native.opens == 0


def test_policy_migration_preserves_existing_execution_history(connected_local, tmp_path):
    from okto_nexus.config import NexusConfig
    from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
    from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
    setup, binding, _ = connected_local
    opened = admit(setup, binding, 'before-policy', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    wait_receipt(setup, admit(setup, binding, 'before-policy-close', 'runtime.close',
        session_id=opened['session_id']), stages=('SUCCEEDED',))
    config = NexusConfig(home_dir=tmp_path / 'upgrade-copy')
    factory = ConnectionFactory(config)
    with sqlite3.connect(config.db_path) as target:
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            uow.connection.backup(target)
        triggers = target.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'agent_execution_policy_%'").fetchall()
        for (name,) in triggers:
            target.execute('DROP TRIGGER ' + name)
        target.execute('DROP TABLE agent_execution_policies')
        target.execute('DELETE FROM schema_migrations WHERE version=100')
        expected = target.execute('SELECT * FROM execution_operations ORDER BY operation_id').fetchall()
    assert MigrationRunner(factory).apply() == [100]
    assert MigrationRunner(factory).apply() == []
    with factory.unit_of_work(write=False) as uow:
        assert [tuple(row) for row in uow.connection.execute('SELECT * FROM execution_operations ORDER BY operation_id')] == expected
        assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []
