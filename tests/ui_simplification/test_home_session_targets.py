"""UI-019 exact passive targets; SQLite/HTTP only, not an integrated viewer."""
import json

from fastapi.testclient import TestClient
import pytest

from okto_nexus.domain.home import target as validate_target
from okto_nexus.errors import OktoNexusError
from .test_fixtures import fixtures


@pytest.fixture
def scenario(tmp_path):
    with fixtures.scenario(tmp_path / 'scenario') as value:
        yield value


def session_target(s, index=0, session_id=None):
    c = s.connections[index]
    return dict(kind='session', server_id=c.server_id, executor_id=c.executor_id,
                workspace_id=c.workspace_id, session_id=session_id or s.sessions[index])


def get(client, target, **scope):
    return client.get('/api/v1/home/target', params=dict(target=json.dumps(target), **scope))


def copy_idle(s, original, session_id):
    """Own synthetic historical read fact with a real opening relation, no productive turn."""
    with s.factory.unit_of_work() as uow:
        c = uow.connection
        row = c.execute('SELECT * FROM execution_sessions WHERE session_id=?', (original,)).fetchone()
        opening = c.execute('SELECT * FROM execution_operations WHERE operation_id=?', (row['open_operation_id'],)).fetchone()
        revisions = json.loads(opening['expected_revisions_json'])
        revisions['session_id'] = session_id
        operation_id = session_id + '-open'
        fixtures._copy(c, 'execution_operations', opening, operation_id=operation_id, session_id=session_id,
                       expected_revisions_json=json.dumps(revisions))
        fixtures._copy(c, 'execution_sessions', row, session_id=session_id, open_operation_id=operation_id,
                       lifecycle_state='CLOSED', lease_state='CLOSED')


def test_two_sessions_same_agent_resolve_exact_current_and_closed_scope(scenario):
    s = scenario
    client = TestClient(s.app, headers={'Authorization': 'Bearer ' + s.app.state.test_agent_keys['operator']})  # Shared fixture already owns lifespan/WSS.
    try:
        for index in (0, 1):
            selected = session_target(s, index)
            response = get(client, selected)
            assert response.status_code == 200, response.text
            value = response.json()['data']
            assert value['target'] == selected and value['available']
            context = value['session_context']
            expected = s.connections[index]
            assert context == dict(server_id=expected.server_id, executor_id=expected.executor_id,
                workspace_id=expected.workspace_id, binding_id=expected.binding_id,
                workspace_binding_id=expected.workspace_binding_id, agent_id=expected.agent_id,
                session_id=s.sessions[index], lifecycle_state='READY' if index == 0 else 'CLOSED')
            assert 'operation_id' not in value['target'] and 'operation_id' not in context
            assert value['agent_id'] == expected.agent_id
            assert value['source_revision']
    finally:
        client.close()


def test_session_without_productive_turn_and_retention_never_select_latest(scenario):
    s = scenario
    for sid in ('ui-idle-one', 'ui-idle-two'):
        copy_idle(s, s.sessions[0], sid)
    with s.factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE session_id LIKE 'ui-idle-%' AND action='turn.submit'").fetchone()[0] == 0
    client = TestClient(s.app, headers={'Authorization': 'Bearer ' + s.app.state.test_agent_keys['operator']})
    try:
        for sid in ('ui-idle-one', 'ui-idle-two'):
            response = get(client, session_target(s, session_id=sid))
            assert response.status_code == 200, response.text
            assert response.json()['data']['session_context']['session_id'] == sid
        with s.factory.unit_of_work() as uow:
            uow.connection.execute("DELETE FROM execution_sessions WHERE session_id='ui-idle-one'")
        assert get(client, session_target(s, session_id='ui-idle-one')).status_code == 404
        assert get(client, session_target(s, session_id='latest')).status_code == 404
        assert get(client, session_target(s, session_id='ui-idle-two')).status_code == 200
    finally:
        client.close()


def test_retained_session_keeps_admitted_scope_after_current_binding_rotates(scenario):
    s = scenario
    sid = 'ui-retained-before-binding-rotation'
    copy_idle(s, s.sessions[0], sid)
    original = s.connections[0]
    with s.factory.unit_of_work() as uow:
        c = uow.connection
        s.deps.repos.workspaces.upsert(uow, workspace_id='ui-rotated-project')
        workspace = c.execute('SELECT * FROM execution_workspace_bindings WHERE workspace_binding_id=?',
                              (original.workspace_binding_id,)).fetchone()
        fixtures._copy(c, 'execution_workspace_bindings', workspace,
                       workspace_binding_id='ui-rotated-wxb', workspace_id='ui-rotated-project')
        endpoint = c.execute('SELECT ep.* FROM agent_endpoints ep JOIN execution_bindings b USING(endpoint_id) WHERE b.binding_id=?',
                             (original.binding_id,)).fetchone()
        fixtures._copy(c, 'agent_endpoints', endpoint, endpoint_id='ui-rotated-endpoint',
                       workspace_id='ui-rotated-project', agent_id='other')
        c.execute('UPDATE execution_bindings SET workspace_binding_id=?,endpoint_id=?,binding_revision=binding_revision+1 WHERE binding_id=?',
                  ('ui-rotated-wxb', 'ui-rotated-endpoint', original.binding_id))
    client = TestClient(s.app, headers={'Authorization': 'Bearer ' + s.app.state.test_agent_keys['operator']})
    try:
        # Oracle: existing canonical session API keeps the admission snapshot.
        canonical = client.get(f'/v1/runtime/sessions/{sid}', params={'executor_id':original.executor_id})
        assert canonical.status_code == 200, canonical.text
        scope = canonical.json()['scope']
        assert scope['workspace_id'] == original.workspace_id and scope['agent_id'] == original.agent_id
        assert scope['workspace_binding_id'] == original.workspace_binding_id and scope['session_id'] == sid
        response = get(client, session_target(s, session_id=sid))
        assert response.status_code == 200, response.text
        actual = response.json()['data']['session_context']
        for key in ('server_id', 'executor_id', 'workspace_id', 'session_id', 'binding_id', 'workspace_binding_id', 'agent_id'):
            assert actual[key] == scope[key]
        assert actual['lifecycle_state'] == 'CLOSED'
        assert 'control_available' not in response.text
        assert get(client, dict(session_target(s, session_id=sid), workspace_id='ui-rotated-project')).status_code == 409
    finally:
        client.close()


def test_closed_session_replays_same_committed_history_without_control_or_new_session(scenario):
    s = scenario
    selected = session_target(s)
    with s.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET lifecycle_state='CLOSED',lease_state='CLOSED' WHERE session_id=?",
                               (selected['session_id'],))
        before = uow.connection.execute('SELECT COUNT(*) FROM execution_sessions').fetchone()[0]
    client = TestClient(s.app, headers={'Authorization': 'Bearer ' + s.app.state.test_agent_keys['operator']})
    try:
        resolved = get(client, selected)
        assert resolved.status_code == 200, resolved.text
        canonical = client.get('/v1/runtime/sessions/'+selected['session_id'], params={'executor_id':selected['executor_id']})
        assert canonical.status_code == 200
        assert canonical.json()['lifecycle_state'] == 'CLOSED' and not canonical.json()['control_available']
        history = client.get('/v1/runtime/sessions/'+selected['session_id']+'/events', params={'executor_id':selected['executor_id']})
        assert history.status_code == 200, history.text
        value = history.json()
        assert value['scope']['session_id'] == selected['session_id']
        assert value['events'] and value['committed_contiguous'] > 0
        assert all(event['session_id'] == selected['session_id'] for event in value['events'])
        assert 'private-marker' not in history.text
        with s.factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT COUNT(*) FROM execution_sessions').fetchone()[0] == before
    finally:
        client.close()


def test_session_foreign_scope_and_operator_authority_are_checked_by_real_http(scenario):
    s = scenario
    with s.factory.unit_of_work() as uow:
        s.deps.repos.workspaces.upsert(uow, workspace_id='ui-other-workspace')
    client = TestClient(s.app, headers={'Authorization': 'Bearer ' + s.app.state.test_agent_keys['operator']})
    try:
        selected = session_target(s)
        assert get(client, dict(selected, server_id='foreign-server')).status_code == 409
        assert get(client, dict(selected, executor_id='foreign-executor')).status_code == 404
        assert get(client, dict(selected, workspace_id='ui-other-workspace')).status_code == 409
        assert get(client, selected, workspace_id='ui-other-workspace').status_code == 409
        assert get(client, dict(selected, workspace_id=None)).status_code == 422
        response = client.get('/api/v1/home/target', params={'target':json.dumps(selected)},
            headers={'Authorization':'Bearer '+s.app.state.test_agent_keys['subject']})
        assert response.status_code == 403, response.text
        assert 'session_context' not in response.text
    finally:
        client.close()


def test_exact_connection_context_is_additive_and_legacy_execution_target_still_resolves(scenario):
    s = scenario
    client = TestClient(s.app, headers={'Authorization': 'Bearer ' + s.app.state.test_agent_keys['operator']})
    try:
        for c in s.connections:
            selected = dict(kind='connection', server_id=c.server_id, executor_id=c.executor_id,
                            workspace_id=c.workspace_id, binding_id=c.binding_id, agent_id=c.agent_id)
            response = get(client, selected)
            assert response.status_code == 200, response.text
            context = response.json()['data']['connection_context']
            assert context['binding_id'] == c.binding_id and context['workspace_binding_id'] == c.workspace_binding_id
            assert get(client, dict(selected, agent_id='other')).status_code == 404
        with s.factory.unit_of_work(write=False) as uow:
            operation = dict(uow.connection.execute("SELECT * FROM execution_operations WHERE action='turn.submit' LIMIT 1").fetchone())
        old = dict(kind='execution', server_id=operation['server_id'], executor_id=operation['executor_id'],
                   workspace_id=operation['workspace_id'], session_id=operation['session_id'], operation_id=operation['operation_id'])
        response = get(client, old)
        assert response.status_code == 200 and response.json()['data']['target'] == old
        assert 'session_context' not in response.json()['data']
    finally:
        client.close()


@pytest.mark.parametrize('patch', [dict(operation_id='fake'), dict(session_id=''), dict(executor_id=None),
    dict(workspace_id=None), dict(kind='session/latest'), dict(session_id=12), dict(url='https://untrusted')])
def test_new_session_target_schema_is_closed(patch):
    value = dict(kind='session', server_id='server', executor_id='executor', workspace_id='workspace', session_id='session')
    with pytest.raises(OktoNexusError) as error:
        validate_target(dict(value, **patch))
    assert error.value.code == 'VALIDATION_ERROR'
