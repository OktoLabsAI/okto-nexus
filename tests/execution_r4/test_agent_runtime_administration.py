"""Runtime administration reads canonical state and controls only a selected session."""
import json
from nexus_connector_core import RuntimeEvent
from test_embedded_dispatch import qualified_contract, connected_local, admit, wait_receipt
from test_local_realization import local_setup


def test_recent_calls_active_instances_permissions_and_scoped_close(connected_local):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE runtime_execution_grants SET max_executions=100')
    first = admit(setup, binding, 'admin-first', 'runtime.start', new_session=True)
    wait_receipt(setup, first)
    first_native = native.native
    second = admit(setup, binding, 'admin-second', 'runtime.start', new_session=True)
    wait_receipt(setup, second)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams WHERE session_id=?', (first['session_id'],)).fetchone())
    calls = []
    for index in range(12):
        turn = admit(setup, binding, f'admin-turn-{index}', 'turn.submit', session_id=first['session_id'], text=f'Call {index}')
        wait_receipt(setup, turn)
        client.portal.call(first_native.queue.put, RuntimeEvent(stream['server_id'], stream['executor_id'],
            stream['session_id'], stream['stream_epoch'], 0, 'turn_state', 'fixture.output',
            dict(delivery_phase='terminal', delivery_outcome='success', output_text=f'Answer {index}'),
            operation_id=turn['operation_id']))
        wait_receipt(setup, turn, stages=('SUCCEEDED',))
        calls.append(turn['operation_id'])
    path = '/api/v1/agents/subject/runtime-administration'
    response = client.get(path, headers=headers['operator'])
    assert response.status_code == 200, response.text
    view = response.json()['data']
    assert view['active_count'] == 2 and len(view['active']) == 2
    assert [row['operation_id'] for row in view['completed']] == list(reversed(calls[-10:]))
    assert {row['session_id'] for row in view['completed']} == {first['session_id']}
    assert client.get(path, headers=headers['subject']).status_code == 403
    # The native dashboard deliberately trusts its local operator connection.
    assert client.get(path).status_code == 200
    assert client.get(path, headers={'Authorization':'Bearer invalid-key'}).status_code == 401
    assert client.get(path, params={'after': -1}, headers=headers['operator']).status_code == 422
    details = f'/api/v1/agents/subject/runtime-executions/{calls[-1]}'
    result = client.get(details, params={'executor_id':binding['executor_id']}, headers=headers['operator'])
    assert result.status_code == 200, result.text
    assert result.json()['data']['scope']['agent_id'] == 'subject'
    assert client.get(details, params={'executor_id':binding['executor_id']}, headers=headers['subject']).status_code == 403
    assert client.get(details.replace('/subject/', '/operator/'), params={'executor_id':binding['executor_id']}, headers=headers['operator']).status_code == 404
    assert client.get(details, params={'executor_id':'wrong-host'}, headers=headers['operator']).status_code == 404
    # Use the same operator close path as the modal, not a direct database mutation.
    close = client.post('/v1/runtime/intents:resolve', headers=headers['operator'], json=dict(
        client_intent_id='admin-close', agent_id='subject', binding_id=binding['binding_id'],
        workspace_binding_id=binding['workspace_binding_id'], intent='runtime.close', session_id=first['session_id'])).json()
    assert close['can_submit'], close
    request = {k:close[k] for k in ('client_intent_id','operation_id','resolution_revision','intent_hash')}
    assert client.post('/v1/runtime/operations', headers=headers['operator'], json=request).status_code == 202
    wait_receipt(setup, close, stages=('SUCCEEDED',))
    remaining_response = client.get(path, headers=headers['operator'])
    assert remaining_response.status_code == 200, remaining_response.text
    remaining = remaining_response.json()['data']
    assert [s['scope']['session_id'] for s in remaining['active']] == [second['session_id']]
    assert remaining['completed'] == view['completed']
    agents = client.get('/api/v1/agents', headers=headers['operator']).json()['data']['items']
    assert next(a for a in agents if a['agent_id']=='subject')['connection']['runtime_integrated']
    assert not next(a for a in agents if a['agent_id']=='operator')['connection']['runtime_integrated']


def test_remote_and_local_sessions_with_colliding_ids_stay_distinct(connected_local):
    from test_session_views import test_session_id_collision_requires_executor_selection
    test_session_id_collision_requires_executor_selection(connected_local)
    setup, _, _ = connected_local
    response = setup[2].get('/api/v1/agents/subject/runtime-administration', headers=setup[3]['operator'])
    assert response.status_code == 200, response.text
    rows = response.json()['data']['active']
    assert len(rows)==2 and {r['location'] for r in rows} == {'embedded','remote'}
    assert rows[0]['scope']['session_id'] == rows[1]['scope']['session_id']
    assert rows[0]['scope']['executor_id'] != rows[1]['scope']['executor_id']
    assert not next(r for r in rows if r['location']=='remote')['control_available']


def test_active_pagination_keeps_failed_unreleased_sessions(connected_local):
    setup, binding, _ = connected_local
    opened = admit(setup, binding, 'page-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    with setup[0].connection_factory.unit_of_work() as uow:
        conn = uow.connection
        operation = dict(conn.execute('SELECT * FROM execution_operations WHERE operation_id=?', (opened['operation_id'],)).fetchone())
        session = dict(conn.execute('SELECT * FROM execution_sessions WHERE session_id=?', (opened['session_id'],)).fetchone())
        for index in range(51):
            sid, oid = f'history-session-{index}', f'history-open-{index}'
            op = operation | dict(operation_id=oid, session_id=sid,
                expected_revisions_json=json.dumps(opened['scope'] | dict(session_id=sid)))
            record = session | dict(session_id=sid, open_operation_id=oid, lifecycle_state='FAILED', lease_state='ACTIVE')
            for table, row in [('execution_operations',op),('execution_sessions',record)]:
                conn.execute('INSERT INTO '+table+'('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))
    path = '/api/v1/agents/subject/runtime-administration'
    first = setup[2].get(path, headers=setup[3]['operator']).json()['data']
    second = setup[2].get(path, params={'after':first['next_after']}, headers=setup[3]['operator']).json()['data']
    assert first['active_count']==52 and len(first['active'])==50 and first['has_more']
    assert len(second['active'])==2 and not second['has_more']
    ids = [row['scope']['session_id'] for row in first['active']+second['active']]
    assert len(set(ids))==52


def test_mcp_only_agent_has_no_runtime_administration(local_setup):
    response = local_setup[2].get('/api/v1/agents/subject/runtime-administration', headers=local_setup[3]['operator'])
    assert response.status_code == 409
