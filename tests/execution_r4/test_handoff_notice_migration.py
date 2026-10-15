"""Upgrade real schema without treating user text or admitted effects as control."""
import json
import shutil

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner, _default_migrations_dir
from okto_nexus.config import NexusConfig


def test_upgrade_preserves_inbox_and_admitted_history_and_routes_only_proved_waiting_notices(tmp_path):
    old = tmp_path / 'old-migrations'
    old.mkdir()
    for path in _default_migrations_dir().glob('*.sql'):
        if int(path.name.split('_')[0]) <= 133:
            shutil.copy(path, old)
    factory = ConnectionFactory(NexusConfig(home_dir=tmp_path / 'home'))
    MigrationRunner(factory, migrations_dir=old).apply()
    now = '2026-01-01T00:00:00Z'
    with factory.unit_of_work() as uow:
        conn = uow.connection
        conn.execute('INSERT INTO workspaces(workspace_id,created_at) VALUES(?,?)', ('workspace', now))
        conn.execute('INSERT INTO agents(agent_id,created_at) VALUES(?,?)', ('agent', now))
        conn.execute('INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,adapter_id,protocol,created_at,updated_at) '
                     'VALUES(?,?,?,?,?,?,?)', ('endpoint', 'agent', 'workspace', 'fixture', 'nxl-r4', now, now))
        for name in ('waiting', 'admitted', 'uncertain', 'direct', 'spoof'):
            target = dict(strategy='direct', agent_id='agent') if name == 'direct' else dict(strategy='broadcast')
            conn.execute('INSERT INTO handoffs(handoff_id,workspace_id,target,status,created_at) VALUES(?,?,?,?,?)',
                         (name, 'workspace', json.dumps(target), 'OPEN', now))
            conn.execute('INSERT INTO messages(message_id,workspace_id,from_agent_id,body,created_at) VALUES(?,?,?,?,?)',
                         (name, 'workspace', 'agent', json.dumps(dict(kind='handoff.created', handoff_id=name)), now))
            conn.execute('INSERT INTO message_deliveries(delivery_id,message_id,recipient_agent_id,status,created_at) VALUES(?,?,?,?,?)',
                         (name, name, 'agent', 'unread', now))
            conn.execute('INSERT INTO runtime_pending_deliveries(delivery_id,context_json,authorization_revision,created_at) VALUES(?,?,?,?)',
                         (name, '{}', 'handoff-notification', now))
            if name != 'spoof':
                conn.execute('INSERT INTO runtime_handoff_notifications VALUES(?,?,?,?,?)',
                             (name, name, 'agent', 'handoff.created', 'persisted-server-guard'))
            if name in ('admitted', 'uncertain'):
                conn.execute('INSERT INTO delivery_outbox(operation_id,delivery_id,message_id,workspace_id,actor_agent_id,'
                    'credential_binding,recipient_agent_id,endpoint_id,endpoint_revision,envelope,request_hash,'
                    'authorization_revision,root_operation_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (name, name, name, 'workspace', 'agent', 'bound', 'agent', 'endpoint', 1, '{}', 'hash', 'auth', name,
                     'PENDING' if name == 'admitted' else 'OUTCOME_UNKNOWN', now, now))
        deliveries = [tuple(r) for r in conn.execute('SELECT * FROM message_deliveries ORDER BY delivery_id')]
        admitted = [tuple(r) for r in conn.execute('SELECT * FROM delivery_outbox ORDER BY operation_id')]
    assert MigrationRunner(factory).apply() == [134, 135, 136, 137, 138, 139, 140, 141]
    assert MigrationRunner(factory).apply() == []
    with factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        routes = dict(conn.execute('SELECT message_id,runtime_route FROM runtime_handoff_notifications'))
        assert routes == dict(waiting='competitive', admitted='legacy_admitted', uncertain='legacy_admitted', direct='conversation')
        assert dict(conn.execute('SELECT delivery_id,status FROM runtime_pending_deliveries')) == dict(
            waiting='resolved', admitted='waiting', uncertain='waiting', direct='waiting', spoof='waiting')
        assert [tuple(r) for r in conn.execute('SELECT * FROM message_deliveries ORDER BY delivery_id')] == deliveries
        assert [tuple(r) for r in conn.execute('SELECT * FROM delivery_outbox ORDER BY operation_id')] == admitted
        assert [r[0] for r in conn.execute('SELECT handoff_id FROM handoff_runtime_schedule')] == ['waiting']
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
