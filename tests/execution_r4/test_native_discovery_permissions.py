"""Native Pi HTTP actions apply the same domain policy as managed MCP."""
import pytest

from test_native_actions import opening, native_cap, invoke
from test_mcp_session_capabilities import seed_work


def body(cap, action, payload=None):
    return dict(action_id='native-check', scope=cap['scope'], action=action, payload=payload or {})


@pytest.mark.parametrize('action,payload', [
    ('agent_list', {}), ('agent_get', {'agent_id': 'other'}), ('capability_list', {}), ('coordination_health', {}),
])
def test_native_read_requires_its_own_action_ceiling(opening, action, payload):
    cap = native_cap(opening, actions=['handoff.get'])
    response = invoke(opening, cap, body(cap, action, payload))
    assert response.status_code == 403, response.text


@pytest.mark.parametrize('opening', [{'subject_permissions': {
    'health': {'read': False}, 'handoffs': {'work': False}, 'messages': {'send_broadcast': False}}}], indirect=True)
@pytest.mark.parametrize('action,domain,payload', [
    ('coordination_health', 'coordination.health', {}),
    ('claim', 'handoff.claim', {'handoff_id': 'work', 'idempotency_key': 'claim-key'}),
    ('message_create', 'message.create', {'message': {'subject': 'Denied', 'body': 'Denied', 'target': {'strategy': 'broadcast'}}}),
])
def test_native_tool_injection_does_not_override_agent_permissions(opening, action, domain, payload):
    opening[0].config.feature_health = True
    cap = native_cap(opening, actions=[domain, 'agent.list'])
    assert invoke(opening, cap, body(cap, 'agent_list')).status_code == 200
    seed_work(opening)
    response = invoke(opening, cap, body(cap, action, payload))
    assert response.status_code == 403, response.text
    assert response.json()['error']['code'] == 'PERMISSION_DENIED'
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 0
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id='work'").fetchone()[0] == 'OPEN'


@pytest.mark.parametrize('opening', [{'subject_comm_scope': {'outbound': {'team': ['allowed']}}}], indirect=True)
def test_native_discovery_rechecks_peer_visibility_without_cached_replay(opening):
    cap = native_cap(opening, actions=['agent.list', 'agent.get', 'capability.list'])
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET tags=? WHERE agent_id='other'", ('{"team":["allowed"]}',))
    request = body(cap, 'agent_list')
    assert {a['agent_id'] for a in invoke(opening, cap, request).json()['result']['agents']} == {'subject', 'other'}
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET comm_scope=? WHERE agent_id='other'", ('{"inbound":{"team":["blocked"]}}',))
    assert {a['agent_id'] for a in invoke(opening, cap, request).json()['result']['agents']} == {'subject'}
    for peer in ('other', 'missing'):
        response = invoke(opening, cap, body(cap, 'agent_get', {'agent_id': peer}))
        assert response.status_code == 404, response.text


@pytest.mark.parametrize('field,value', [('workspace_id', 'foreign'), ('agent_id', 'other')])
def test_native_health_cannot_override_session_scope(opening, field, value):
    cap = native_cap(opening, actions=['coordination.health'])
    response = invoke(opening, cap, body(cap, 'coordination_health', {field: value}))
    assert response.status_code == 422, response.text


def test_native_discovery_cannot_use_revoked_capability(opening):
    cap = native_cap(opening, actions=['agent.list'])
    assert invoke(opening, cap, body(cap, 'agent_list')).status_code == 200
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_session_capabilities SET revoked_at='2026-01-01T00:00:00Z'")
    assert invoke(opening, cap, body(cap, 'agent_list')).status_code == 401
