"""Runtime readiness, not the last user message, drives dashboard presence."""
import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract
from test_canonical_delivery import connected_local


@pytest.mark.parametrize('state,presence', [('CONTROL_READY','present'), ('RECOVERING','stale'), ('DISCONNECTED','offline')])
def test_graph_and_agent_presence_follow_local_connection(connected_local, state, presence):
    setup, binding, _ = connected_local
    deps, app, client, headers, *_ = setup
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET last_seen_at='2000-01-01T00:00:00Z' WHERE agent_id='subject'")
        uow.connection.execute("UPDATE execution_executors SET control_state=? WHERE kind='embedded'", (state,))
    try:
        graph = client.get('/api/v1/graph', headers=headers['operator']).json()['data']
        node = next(n for n in graph['nodes'] if n['agent_id'] == 'subject')
        assert node['presence'] == presence
        agents = client.get('/api/v1/agents', headers=headers['operator']).json()['data']['items']
        assert next(a for a in agents if a['agent_id'] == 'subject')['presence'] == presence
        assert client.get('/api/v1/agents/subject', headers=headers['operator']).json()['data']['presence'] == presence
        # A disconnected runtime stays offline even if its agent just called an API.
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('UPDATE agents SET last_seen_at=? WHERE agent_id=?', (deps.clock.now_iso(), 'subject'))
        graph = client.get('/api/v1/graph', headers=headers['operator']).json()['data']
        assert next(n for n in graph['nodes'] if n['agent_id'] == 'subject')['presence'] == presence
    finally:
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE execution_executors SET control_state='CONTROL_READY' WHERE kind='embedded'")
