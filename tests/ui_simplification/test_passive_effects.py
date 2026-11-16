"""Repeated actual Home HTTP reads preserve canonical execution and decision data."""
import json

from fastapi.testclient import TestClient

from .test_entry_pages import scenario as scenario


TABLES = (
    'connection_setup_commits', 'execution_bindings', 'agent_endpoints',
    'runtime_execution_grants', 'messages', 'handoffs', 'sessions',
    'execution_sessions', 'execution_operations', 'execution_decisions',
    'execution_dispatch_outbox', 'delivery_outbox', 'runtime_handoff_bindings',
    'approvals', 'connection_authorization_receipts', 'execution_receipts',
    'runtime_native_approvals', 'runtime_relay_decisions',
)


def test_repeated_entries_expansion_and_exact_detail_create_no_productive_effect(request):
    s = request.getfixturevalue('scenario')

    def snapshot():
        with s.factory.unit_of_work(write=False) as uow:
            return {table: sorted(json.dumps(dict(row), sort_keys=True) for row in
                                 uow.connection.execute('SELECT * FROM ' + table)) for table in TABLES}

    before = snapshot()
    client = TestClient(s.app, headers={'Authorization': 'Bearer ' + s.app.state.test_agent_keys['operator']})
    try:
        for _ in range(2):
            response = client.get('/api/v1/home/entries', params={'quick': 'all', 'limit': 100})
            assert response.status_code == 200, response.text
            groups = response.json()['data']['items']
            for group in groups:
                children = client.get('/api/v1/home/entries/' + group['id'] + '/children', params={'quick': 'all'})
                assert children.status_code == 200, children.text
                for entry in children.json()['data']['items']:
                    if entry['target'] is None:
                        continue
                    target = client.get('/api/v1/home/target', params={'target': json.dumps(entry['target'])})
                    assert target.status_code == 200, target.text
        assert snapshot() == before
        assert not s.app.state.connection_tests.tests
    finally:
        client.close()
