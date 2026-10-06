import sqlite3
from types import SimpleNamespace

import pytest

from okto_nexus.application import meta_harness_workspaces as service
from okto_nexus.errors import OktoNexusError


@pytest.fixture
def uow(monkeypatch):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE agent_execution_policies(agent_id,execution_location);
        CREATE TABLE agent_endpoints(endpoint_id,agent_id,workspace_id,adapter_id,profile_id,protocol,enabled,activation_state,consumption,response_policy);
        CREATE TABLE runtime_profiles(profile_id,enabled);
        CREATE TABLE execution_bindings(endpoint_id,server_id,executor_id);
        CREATE TABLE execution_executors(server_id,executor_id,kind,revoked_at);
        CREATE TABLE workspaces(workspace_id,display_name);
        CREATE TABLE sessions(agent_id,workspace_id,closed_at);
        INSERT INTO agent_execution_policies VALUES ('claude','remote');
        INSERT INTO runtime_profiles VALUES ('p',1);
        INSERT INTO workspaces VALUES ('old','Same name'),('new','Same name'),('local','Local');
        INSERT INTO execution_executors VALUES ('s','old','remote',NULL),('s','new','remote',NULL),('s','local','embedded',NULL);
        INSERT INTO agent_endpoints VALUES
          ('old','claude','old','claude_stream','p','nxl-r4',0,'revoked','exclusive','conversation'),
          ('new','claude','new','claude_stream','p','nxl-r4',1,'approved','exclusive','conversation'),
          ('local','claude','local','claude_stream','p','nxl-r4',1,'approved','exclusive','conversation');
        INSERT INTO execution_bindings VALUES ('old','s','old'),('new','s','new'),('local','s','local');
        INSERT INTO sessions VALUES ('mcp','new',NULL),('mcp','old','2026-01-01');
    ''')
    monkeypatch.setattr(service, 'effective', lambda *args: {'runtime_enabled': True})
    monkeypatch.setattr(service, 'method_enabled', lambda *args: True)
    yield SimpleNamespace(connection=conn)
    conn.close()


def test_replaced_machine_and_other_location_are_not_offered(uow):
    result = service.recipient_workspaces(uow, 'claude')
    assert result['items'] == [{'workspace_id': 'new', 'display_name': 'Same name'}]
    service.validate_recipient_workspace(uow, 'claude', 'new')
    with pytest.raises(OktoNexusError) as caught:
        service.validate_recipient_workspace(uow, 'claude', 'old')
    assert caught.value.details['reason'] == 'AGENT_WORKSPACE_MISMATCH'


def test_local_mode_and_disabled_method(uow, monkeypatch):
    uow.connection.execute("UPDATE agent_execution_policies SET execution_location='local'")
    assert service.recipient_workspaces(uow, 'claude')['items'][0]['workspace_id'] == 'local'
    monkeypatch.setattr(service, 'method_enabled', lambda *args: False)
    assert service.recipient_workspaces(uow, 'claude')['items'] == []


def test_mcp_namespaces_and_inbox_semantics_are_preserved(uow):
    assert service.recipient_workspaces(uow, 'mcp')['items'] == [{'workspace_id': 'new', 'display_name': 'Same name'}]
    service.validate_recipient_workspace(uow, 'mcp', 'old')


def test_revocation_after_selection_is_rejected(uow):
    assert service.recipient_workspaces(uow, 'claude')['items']
    uow.connection.execute("UPDATE execution_executors SET revoked_at='now' WHERE executor_id='new'")
    with pytest.raises(OktoNexusError):
        service.validate_recipient_workspace(uow, 'claude', 'new')
