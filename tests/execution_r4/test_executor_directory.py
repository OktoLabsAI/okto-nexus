"""The dashboard directory shares inventory scope without exposing host internals."""
import pytest
from test_binding_operator import onboarding, prepare_operator


def read(host, subject='subject', actor='subject', query=None):
    _, client, headers, _ = host
    return client.get(f'/v1/agents/{subject}/executors', params=query, headers=headers[actor])


def test_directory_is_scoped_path_free_and_has_no_effects(onboarding):
    deps, client, headers, scope = onboarding
    response = read(onboarding)
    assert response.status_code == 200, response.text
    assert response.headers['Cache-Control'] == 'no-store'
    items = response.json()['items']
    assert scope['executor_id'] in {row['executor_id'] for row in items}
    assert all(set(row) == {'executor_id', 'kind', 'label', 'control_state'} for row in items)
    assert read(onboarding, actor='other').status_code == 403
    assert scope['executor_id'] not in {row['executor_id'] for row in read(onboarding, subject='other', actor='other').json()['items']}
    assert scope['executor_id'] in {row['executor_id'] for row in read(onboarding, subject='other', actor='operator').json()['items']}
    assert client.get('/v1/agents/subject/executors').status_code == 401
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0


def test_directory_paginates_visible_rows_and_removes_revoked_executor(onboarding):
    deps, _, _, scope = onboarding
    first = read(onboarding, query={'limit': 1}).json()
    assert first['has_more'] and len(first['items']) == 1
    second = read(onboarding, query={'limit': 1, 'after_executor_id': first['next_executor_id']}).json()
    assert not second['has_more'] and second['next_executor_id'] is None
    assert first['items'][0]['executor_id'] != second['items'][0]['executor_id']
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE execution_executors SET revoked_at=? WHERE executor_id=?',
                               (deps.clock.now_iso(), scope['executor_id']))
    assert scope['executor_id'] not in {row['executor_id'] for row in read(onboarding).json()['items']}


def test_approved_subject_can_discover_executor_registered_by_another_agent(onboarding):
    deps, client, headers, scope = onboarding
    _, body = prepare_operator(client, headers, scope)
    assert client.post('/v1/connections/bindings:apply', json=body, headers=headers['operator']).status_code == 200
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_executors SET registered_by_agent_id='other' WHERE executor_id=?", (scope['executor_id'],))
    assert scope['executor_id'] in {row['executor_id'] for row in read(onboarding).json()['items']}
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE agent_endpoints SET enabled=0')
    assert scope['executor_id'] not in {row['executor_id'] for row in read(onboarding).json()['items']}


@pytest.mark.parametrize('query', ['limit=0', 'limit=101', 'limit=1&limit=2', 'after_executor_id=', 'unexpected=1'])
def test_directory_rejects_invalid_or_ambiguous_query(onboarding, query):
    _, client, headers, _ = onboarding
    assert client.get('/v1/agents/subject/executors?' + query, headers=headers['subject']).status_code == 422
