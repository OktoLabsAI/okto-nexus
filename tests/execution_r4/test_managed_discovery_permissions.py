"""Managed MCP reads retain domain permissions and session authority over HTTP."""
import json

import pytest

from test_mcp_session_capabilities import opening, activate, rpc, envelope, seed_work, args


READS = [
    ('agent_list', {}),
    ('agent_get', {'agent_id': 'other'}),
    ('capability_list', {}),
    ('coordination_health', {'project_root': 'ws'}),
]


@pytest.mark.parametrize('name,arguments', READS)
def test_managed_discovery_uses_authorized_identity(opening, name, arguments):
    opening[0].config.feature_health = True
    cap = activate(opening, actions=['tools/call', name])
    result = envelope(rpc(opening, cap['capability'], name, arguments))
    assert result['ok'], result
    if name == 'agent_list':
        agents = {a['agent_id']: a for a in result['data']['agents']}
        assert 'other' in agents and 'subject' in agents
        assert {'presence', 'connection'} <= agents['subject'].keys()
    if name == 'agent_get':
        assert result['data']['agent_id'] == 'other'
        assert {'presence', 'connection'} <= result['data'].keys()
    if name == 'coordination_health':
        assert result['data']['workspace_id'] == 'ws'
    for private in ('api_key_hash', 'secret_hash', 'credential_binding'):
        assert private not in json.dumps(result['data'])


@pytest.mark.parametrize('name,arguments', READS)
def test_managed_discovery_requires_explicit_tool_ceiling(opening, name, arguments):
    opening[0].config.feature_health = True
    cap = activate(opening, actions=['tools/call'])
    result = envelope(rpc(opening, cap['capability'], name, arguments))
    assert not result['ok'] and result['error']['code'] == 'PERMISSION_DENIED', result


@pytest.mark.parametrize('opening', [{'subject_comm_scope': {'outbound': {'team': ['allowed']}}}], indirect=True)
def test_managed_discovery_respects_outbound_and_inbound_visibility(opening):
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET tags=?,capabilities=? WHERE agent_id='other'",
            ('{"team":["allowed"]}', '{"review":true}'))
    cap = activate(opening, actions=['tools/call', 'agent_list', 'agent_get', 'capability_list'])
    def visible():
        result = envelope(rpc(opening, cap['capability'], 'agent_list'))
        assert result['ok'], result
        return {a['agent_id'] for a in result['data']['agents']}
    assert visible() == {'subject', 'other'}
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET comm_scope=? WHERE agent_id='other'",
            ('{"inbound":{"team":["blocked"]}}',))
    assert visible() == {'subject'}
    for peer in ('other', 'nonexistent'):
        result = envelope(rpc(opening, cap['capability'], 'agent_get', {'agent_id': peer}))
        assert not result['ok'] and result['error']['code'] == 'NOT_FOUND', result
    caps = envelope(rpc(opening, cap['capability'], 'capability_list'))
    assert caps['ok'], caps
    assert all('other' not in c['agents'] for c in caps['data']['capabilities'])


@pytest.mark.parametrize('opening', [{'subject_permissions': {
    'health': {'read': False}, 'events': {'read': False}, 'handoffs': {'work': False},
    'messages': {'send_broadcast': False, 'send_channel': False}}}], indirect=True)
@pytest.mark.parametrize('name,arguments', [
    ('coordination_health', {'project_root': 'ws'}),
    ('event_get', {'project_root': 'ws', 'agent_id': 'subject', 'stream': 'workspace'}),
    ('event_cursor', {'project_root': 'ws', 'agent_id': 'subject', 'stream': 'workspace'}),
    ('handoff_claim', args()),
    ('message_create', {'project_root': 'ws', 'from_agent_id': 'subject',
                        'target': {'strategy': 'broadcast'}, 'subject': 'Denied', 'body': 'Denied'}),
])
def test_runtime_capability_does_not_override_agent_permissions(opening, name, arguments):
    opening[0].config.feature_health = True
    cap = activate(opening, actions=['tools/call', name, 'agent_whoami'])
    assert envelope(rpc(opening, cap['capability']))['ok']
    seed_work(opening)
    result = envelope(rpc(opening, cap['capability'], name, arguments))
    assert not result['ok'] and result['error']['code'] == 'PERMISSION_DENIED', result
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 0
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id='work'").fetchone()[0] == 'OPEN'


@pytest.mark.parametrize('name,arguments', [
    ('coordination_health', {'project_root': 'other-workspace'}),
    ('coordination_health', {'project_root': 'ws', 'agent_id': 'other'}),
    ('harness_list', {'view': 'connections', 'maintenance': {'agent_id': 'subject'}}),
    ('harness_list', {'view': 'connections', 'maintenance': {'action': 'revoke', 'agent_id': 'other', 'key_id': 'key'}}),
])
def test_full_communication_access_does_not_grant_scope_escape_or_connection_admin(opening, name, arguments):
    cap = activate(opening, actions=['tools/call', name])
    result = envelope(rpc(opening, cap['capability'], name, arguments))
    assert not result['ok'] and result['error']['code'] == 'PERMISSION_DENIED', result


def test_revoked_direct_send_permission_invalidates_existing_runtime_authority(opening):
    cap = activate(opening, actions=['tools/call', 'message_create', 'agent_whoami'])
    assert envelope(rpc(opening, cap['capability']))['ok']
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET permissions=? WHERE agent_id='subject'",
            ('{"messages":{"send_direct":false}}',))
    response = rpc(opening, cap['capability'], 'message_create', {
        'workspace_id': 'ws', 'from_agent_id': 'subject', 'subject': 'Denied', 'body': 'Denied',
        'target': {'strategy': 'direct', 'agent_id': 'other'}})
    assert response.status_code == 401
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 0


@pytest.mark.parametrize('name,arguments', READS)
def test_managed_discovery_rechecks_revocation_after_authentication(opening, monkeypatch, name, arguments):
    from okto_nexus.adapters.inbound.mcp.connection_gate import ConnectionGateServer
    cap = activate(opening, actions=['tools/call', name])
    opening[0].config.feature_health = True
    original = ConnectionGateServer.check
    def revoke_after_check(self):
        original(self)
        with opening[0].connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE execution_session_capabilities SET revoked_at='2026-01-01T00:00:00Z'")
    monkeypatch.setattr(ConnectionGateServer, 'check', revoke_after_check)
    result = envelope(rpc(opening, cap['capability'], name, arguments))
    assert not result['ok'] and result['error']['code'] == 'PERMISSION_DENIED', result


def test_local_and_remote_issuance_include_only_reviewed_domain_tools():
    from okto_nexus.bootstrap.embedded_tools import MCP_ACTIONS
    from okto_nexus_connector.services.mcp_launch import MCP_SESSION_ACTIONS
    from okto_nexus.application.execution_tools import MANAGED_TOOLS
    assert set(MCP_ACTIONS) == set(MCP_SESSION_ACTIONS)
    assert set(MCP_ACTIONS) - {'tools/call', 'resources/read', 'prompts/get'} == MANAGED_TOOLS
