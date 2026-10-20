"""Runtime readiness, not the last user message, drives dashboard presence."""
import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract
from test_canonical_delivery import connected_local


@pytest.mark.parametrize('state,presence', [('CONTROL_READY','present'), ('RECOVERING','stale'), ('DISCONNECTED','offline')])
def test_graph_and_agent_presence_follow_local_connection(connected_local, state, presence, monkeypatch):
    setup, binding, _ = connected_local
    deps, app, client, headers, *_ = setup
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET last_seen_at='2000-01-01T00:00:00Z' WHERE agent_id='subject'")
        uow.connection.execute("UPDATE execution_executors SET control_state=? WHERE kind='embedded'", (state,))

    def stable_read(read):
        # The live embedded owner can reconcile between two HTTP calls. Check
        # each projection only when the controlled state survived that call.
        for _ in range(8):
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute("UPDATE execution_executors SET control_state=? WHERE kind='embedded'", (state,))
            value = read()
            with deps.connection_factory.unit_of_work(write=False) as uow:
                current = uow.connection.execute("SELECT control_state FROM execution_executors WHERE kind='embedded'").fetchone()[0]
            if current == state:
                return value
        pytest.fail(f'Embedded control state did not remain {state} during a presence read')

    try:
        graph = stable_read(lambda: client.get('/api/v1/graph', headers=headers['operator']).json()['data'])
        node = next(n for n in graph['nodes'] if n['agent_id'] == 'subject')
        assert node['presence'] == presence
        agents = stable_read(lambda: client.get('/api/v1/agents', headers=headers['operator']).json()['data']['items'])
        assert next(a for a in agents if a['agent_id'] == 'subject')['presence'] == presence
        assert stable_read(lambda: client.get('/api/v1/agents/subject', headers=headers['operator']).json()['data'])['presence'] == presence
        from pathlib import Path
        monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
        from test_pr34_remediation import tool
        client.headers['host'] = '127.0.0.1:8000'
        key = headers['operator']['Authorization'].removeprefix('Bearer ')
        listed = stable_read(lambda: tool(client, key, 'agent_list', {}))
        assert listed['ok'], listed
        peer = next(a for a in listed['data']['agents'] if a['agent_id'] == 'subject')
        inspected = stable_read(lambda: tool(client, key, 'agent_get', {'agent_id': 'subject'}))
        assert inspected['ok'], inspected
        assert peer['presence'] == inspected['data']['presence'] == presence
        assert peer['connection'] == inspected['data']['connection']
        assert set(peer['connection']) == {'location', 'status'}
        assert peer['connection']['location'] == 'local'
        # A disconnected runtime stays offline even if its agent just called an API.
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('UPDATE agents SET last_seen_at=? WHERE agent_id=?', (deps.clock.now_iso(), 'subject'))
        graph = stable_read(lambda: client.get('/api/v1/graph', headers=headers['operator']).json()['data'])
        assert next(n for n in graph['nodes'] if n['agent_id'] == 'subject')['presence'] == presence
    finally:
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE execution_executors SET control_state='CONTROL_READY' WHERE kind='embedded'")
