import sqlite3
from types import SimpleNamespace

import pytest

from okto_nexus.application.agent_connection_status import agent_connection_statuses


@pytest.fixture
def status_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
    CREATE TABLE agents(agent_id TEXT);
    CREATE TABLE agent_execution_policies(agent_id TEXT,execution_location TEXT);
    CREATE TABLE agent_runtime_overrides(agent_id TEXT,runtime_enabled INTEGER);
    CREATE TABLE runtime_policy_defaults(runtime_enabled INTEGER);
    CREATE TABLE execution_executors(server_id TEXT,executor_id TEXT,registered_by_agent_id TEXT,
      kind TEXT,revoked_at TEXT,label TEXT,control_state TEXT,last_seen_at TEXT,generation INTEGER,owner_instance_id TEXT);
    CREATE TABLE execution_bindings(server_id TEXT,executor_id TEXT,binding_id TEXT,endpoint_id TEXT);
    CREATE TABLE agent_endpoints(endpoint_id TEXT,agent_id TEXT,enabled INTEGER,activation_state TEXT);
    CREATE TABLE execution_control_lanes(server_id TEXT,executor_id TEXT,binding_id TEXT,agent_id TEXT,
      state TEXT,expires_at TEXT,connection_generation INTEGER,connection_id TEXT);
    INSERT INTO agents VALUES('subject'),('unrelated');
    INSERT INTO runtime_policy_defaults VALUES(1);
    INSERT INTO agent_execution_policies VALUES('subject','remote');
    INSERT INTO execution_executors VALUES('server','host','subject','remote',NULL,'Office PC',
      'CONTROL_READY','2026-10-05T12:00:00Z',1,'connection');
    INSERT INTO execution_bindings VALUES('server','host','binding','endpoint');
    INSERT INTO agent_endpoints VALUES('endpoint','subject',1,'approved');
    INSERT INTO execution_control_lanes VALUES('server','host','binding','subject','ADMITTED',
      '2026-10-05T13:00:00Z',1,'connection');
    ''')
    yield SimpleNamespace(connection=conn)
    conn.close()


@pytest.mark.parametrize('change,expected', [
    ('', 'Connected'),
    ("UPDATE execution_executors SET control_state='RECOVERING'", 'Reconnecting'),
    ("UPDATE execution_executors SET control_state='DISCONNECTED'", 'Offline'),
    ("UPDATE execution_executors SET last_seen_at='2026-10-05T11:59:00Z'", 'Offline'),
    ("UPDATE execution_control_lanes SET state='DISCONNECTED'", 'Reconnecting'),
    ("UPDATE execution_control_lanes SET connection_generation=2", 'Reconnecting'),
    ("UPDATE execution_control_lanes SET expires_at='2026-10-05T11:59:00Z'", 'Reconnecting'),
    ("UPDATE agent_endpoints SET enabled=0", 'Reconnecting'),
    ("UPDATE execution_executors SET revoked_at='2026-10-05T12:00:00Z'", 'Offline'),
    ("INSERT INTO agent_runtime_overrides VALUES('subject',0)", 'MCP only'),
])
def test_remote_state_uses_live_agent_lane_not_activity(status_db, change, expected):
    if change:
        status_db.connection.execute(change)
    result = agent_connection_statuses(status_db, '2026-10-05T12:00:10Z')
    assert result['subject']['status'] == expected
    assert result['unrelated'] == dict(location='local',status='Local',hosts=[])


def test_host_details_and_local_selection(status_db):
    result = agent_connection_statuses(status_db, '2026-10-05T12:00:10Z')['subject']
    assert result['hosts'][0]['label'] == 'Office PC'
    assert result['hosts'][0]['last_seen_at'] == '2026-10-05T12:00:00Z'
    status_db.connection.execute("UPDATE agent_execution_policies SET execution_location='local'")
    assert agent_connection_statuses(status_db, '2026-10-05T12:00:10Z')['subject'] == dict(location='local',status='Local',hosts=[])
