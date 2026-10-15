"""Connection catalog exposes logical workspace identity, never machine paths."""
import json
from test_local_realization import local_setup, publish


def test_catalog_paginates_other_workspaces_and_enforces_discovery_permission(local_setup):
    deps, app, client, headers, *_ = local_setup
    client._transport.raise_server_exceptions = True
    with deps.connection_factory.unit_of_work() as uow:
        for identity, path in [('ws_a','/server/private'),('ws_b',None)]:
            uow.connection.execute('INSERT INTO workspaces(workspace_id,display_name,root_realpath,created_at) VALUES(?,?,?,?)',
                (identity,'Same project',path,deps.clock.now_iso()))
        uow.connection.execute('UPDATE agents SET permissions=? WHERE agent_id=?',
            (json.dumps({'workspaces': {'list': True}}),'subject'))
    response = client.get('/v1/connections/workspaces?limit=1',headers=headers['subject'])
    assert response.status_code == 200, response.text
    first = response.json()
    assert first == dict(items=[dict(workspace_id='ws_a',display_name='Same project')],
                         has_more=True,next_workspace_id='ws_a')
    response=client.get('/v1/connections/workspaces?limit=1&after_workspace_id=ws_a',headers=headers['subject'])
    assert response.json() == dict(items=[dict(workspace_id='ws_b',display_name='Same project')],
                                   has_more=False,next_workspace_id=None)
    assert client.get('/v1/connections/workspaces?limit=101',headers=headers['operator']).status_code==422
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE agents SET permissions=? WHERE agent_id=?',
            (json.dumps({'workspaces': {'list': False}}),'subject'))
    assert client.get('/v1/connections/workspaces',headers=headers['subject']).status_code==403
    operator=client.get('/v1/connections/workspaces',headers=headers['operator'])
    assert operator.status_code==200
    assert all(set(row)=={'workspace_id','display_name'} for row in operator.json()['items'])
    assert client.get('/v1/connections/workspaces',headers={'Authorization':'Bearer invalid'}).status_code in (401,403)


def test_existing_workspace_keeps_identity_with_independent_connection_folder(local_setup):
    deps, _, _, _, _, _, root = local_setup
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute(
            'INSERT INTO workspaces(workspace_id,display_name,root_realpath,created_at) VALUES(?,?,?,?)',
            ('ws_other_harness', 'Shared project', '/other-host/project', deps.clock.now_iso()))
    response = publish(local_setup, changes={'workspace_id': 'ws_other_harness'})
    assert response.status_code == 201, response.text
    assert response.json()['workspace_id'] == 'ws_other_harness'
    with deps.connection_factory.unit_of_work(write=False) as uow:
        workspace = uow.connection.execute('SELECT * FROM workspaces WHERE workspace_id=?',
                                          ('ws_other_harness',)).fetchone()
        assert workspace['display_name'] == 'Shared project'
        assert workspace['root_realpath'] == '/other-host/project'
        record = json.loads(uow.connection.execute(
            'SELECT local_record_json FROM execution_local_realizations').fetchone()[0])
        assert record['root']['path'] == str(root.resolve())
        binding = uow.connection.execute('SELECT workspace_id FROM execution_workspace_bindings').fetchone()
        assert binding['workspace_id'] == 'ws_other_harness'
