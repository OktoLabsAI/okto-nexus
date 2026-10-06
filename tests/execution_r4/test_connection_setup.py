"""Finish is the sole configuration commit boundary."""
import json
from copy import deepcopy
import pytest
from test_local_realization import local_setup
from okto_nexus.application.connection_setup import finish_setup, load_setup
from okto_nexus.application.execution_local_realizations import directory_identity
from okto_nexus.domain.runtime_context import RuntimeRequestContext


def request_for(setup):
    deps,app,client,headers,body,candidate,root = setup
    context = RuntimeRequestContext('operator','http_loopback',trusted_local_operator=True)
    request = dict(client_intent_id='finish-one',agent_id='subject',executor_id=app.state.embedded_inventory_owner.key.executor_id,
        candidate_ref=body['candidate_ref'],inventory_revision=body['inventory_revision'],workspace_id=None,binding_id=None,
        baseline=load_setup(deps,context,'subject')['baseline'],configuration=dict(
            format='okto-nexus-connection',version=1,adapter_id=body['adapter_id'],execution_location='local',
            runtime_enabled=True,session_policy='per_sender',workspace_root=str(root),workspace_label='Draft workspace',
            provider_home=None,secret_bindings={},alias='draft-test',harness_settings={},automatic_reply=True,
            tool_access='always_allow',authorization=dict(minutes=60,actions=20)))
    return context,request


def finish(setup, context, request, **kwargs):
    deps,app,*_ = setup
    return finish_setup(deps,context,app.state.embedded_inventory_owner,
        app.state.inventory_fresh_publications,request,**kwargs)


def count(setup, table):
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        return uow.connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]


def test_finish_atomic_idempotent(local_setup):
    context,request=request_for(local_setup)
    request['configuration']['automatic_reply'] = False  # Legacy JSON cannot disable routing.
    assert count(local_setup,'execution_bindings') == 0
    result=finish(local_setup,context,request,verified={'root':directory_identity(request['configuration']['workspace_root']),'home':None})
    assert result['saved']
    assert count(local_setup,'execution_bindings') == 1
    assert count(local_setup,'connection_setup_commits') == 1
    workspace_id = result['binding']['workspace_id']
    client, headers = local_setup[2:4]
    listed = client.get('/api/v1/workspaces', headers=headers['operator'])
    assert listed.status_code == 200
    assert workspace_id in {item['workspace_id'] for item in listed.json()['data']['workspaces']}
    recipient = client.get('/api/v1/meta-harness/agents/subject/workspaces', headers=headers['operator'])
    assert recipient.status_code == 200
    assert workspace_id in {item['workspace_id'] for item in recipient.json()['data']['items']}
    paths = client.get(f'/v1/workspaces/{workspace_id}/paths',
        params={'executor_id': request['executor_id']}, headers=headers['operator'])
    assert paths.status_code == 200
    assert paths.json()['items'] == [{'path': str(local_setup[6].resolve())}]
    dashboard_paths = client.get(f'/api/v1/runtime-management/workspaces/{workspace_id}/paths',
        params={'executor_id': request['executor_id']}, headers=headers['operator'])
    assert dashboard_paths.status_code == 200
    assert dashboard_paths.json()['items'] == paths.json()['items']
    assert client.get(f'/v1/workspaces/{workspace_id}/paths',
        params={'executor_id': request['executor_id']}, headers=headers['subject']).status_code == 403
    assert finish(local_setup,context,request,verified=None) == result
    assert count(local_setup,'execution_bindings') == 1
    view=load_setup(local_setup[0],context,'subject',result['binding']['binding_id'])
    assert view['folders']['workspace_root'] == request['configuration']['workspace_root']
    assert view['public_config']['nexus_tool_permission'] == 'always_allow'
    assert view['automatic_reply'] is True
    endpoint = result['binding']['endpoint_id']
    client,headers = local_setup[2:4]
    policy = client.get(f'/api/v1/harness/endpoints/{endpoint}/conversation-policy',headers=headers['operator']).json()['data']
    response = client.put(f'/api/v1/harness/endpoints/{endpoint}/conversation-policy',headers=headers['operator'],
        json={'expected_revision':policy['revision'],'enabled':False})
    assert response.status_code == 422
    # Upgrade legacy connections without losing existing execution grants.
    from pathlib import Path
    import okto_nexus
    with local_setup[0].connection_factory.unit_of_work() as uow:
        conn=uow.connection
        before=[tuple(r) for r in conn.execute('SELECT * FROM runtime_execution_grants')]
        revision=conn.execute('SELECT revision FROM agent_endpoints WHERE endpoint_id=?',(endpoint,)).fetchone()[0]
        conn.execute("UPDATE agent_endpoints SET response_policy='explicit' WHERE endpoint_id=?",(endpoint,))
        sql=(Path(okto_nexus.__file__).parent/'migrations/106_runtime_automatic_delivery.sql').read_text()
        conn.execute(sql)
        assert conn.execute('SELECT response_policy,revision FROM agent_endpoints WHERE endpoint_id=?',(endpoint,)).fetchone()[:] == ('conversation',revision)
        assert [tuple(r) for r in conn.execute('SELECT * FROM runtime_execution_grants')] == before


def test_workspace_paths_aggregate_across_agents_on_the_same_host(local_setup):
    context, first = request_for(local_setup)
    initial = finish(local_setup, context, first, verified={
        'root': directory_identity(first['configuration']['workspace_root']), 'home': None})
    workspace_id = initial['binding']['workspace_id']
    second_root = local_setup[6].parent / 'another-location'
    second_root.mkdir()
    with local_setup[0].connection_factory.unit_of_work() as uow:
        local_setup[0].repos.agents.upsert(uow, agent_id='second-agent')
        local_setup[1].state.auth.issue_key(uow, agent_id='second-agent')
    second = deepcopy(first)
    second.update(client_intent_id='finish-second', agent_id='second-agent', workspace_id=workspace_id,
                  baseline=load_setup(local_setup[0], context, 'second-agent')['baseline'])
    second['configuration'].update(workspace_root=str(second_root), alias='second-agent-connection')
    finish(local_setup, context, second, verified={
        'root': directory_identity(str(second_root)), 'home': None})

    client, headers = local_setup[2:4]
    response = client.get(f'/v1/workspaces/{workspace_id}/paths',
        params={'executor_id': first['executor_id']}, headers=headers['operator'])
    assert response.status_code == 200
    assert {item['path'] for item in response.json()['items']} == {
        str(local_setup[6].resolve()), str(second_root.resolve())}


@pytest.mark.parametrize('failure',['no_test','invalid_settings','stale_baseline'])
def test_finish_rolls_back_every_configuration_change(local_setup,failure):
    context,request=request_for(local_setup)
    verified={'root':directory_identity(request['configuration']['workspace_root']),'home':None}
    if failure == 'no_test': verified=None
    if failure == 'invalid_settings': request['configuration']['harness_settings']={'effort':'impossible'}
    if failure == 'stale_baseline': request['baseline']['execution_revision'] += 1
    with pytest.raises(Exception): finish(local_setup,context,request,verified=verified)
    for table in ('execution_bindings','execution_local_realizations','connection_setup_commits','agent_execution_policies','agent_runtime_overrides'):
        assert count(local_setup,table) == 0


def test_setup_transport_requires_operator(local_setup):
    _,_,client,headers,*_=local_setup
    assert client.get('/v1/connections/setup/subject',headers=headers['subject']).status_code == 403
    assert client.get('/v1/connections/setup/subject',headers=headers['operator']).status_code == 200


@pytest.mark.parametrize('existing_local', [False, True])
def test_remote_policy_can_finish_before_connector_registration(local_setup, existing_local):
    context, request = request_for(local_setup)
    if existing_local:
        finish(local_setup, context, request, verified={
            'root': directory_identity(request['configuration']['workspace_root']), 'home': None})
    before = count(local_setup, 'execution_bindings')
    request.update(client_intent_id='switch-to-remote', executor_id='', candidate_ref='', inventory_revision='',
                   workspace_id=None, binding_id=None,
                   baseline=load_setup(local_setup[0], context, 'subject')['baseline'])
    request['configuration']['execution_location'] = 'remote'
    request['configuration']['authorization'] = dict(minutes=0, actions=0,
        no_expiry=True, unlimited_actions=True)
    response = local_setup[2].post('/v1/connections/setup:finish', headers=local_setup[3]['operator'], json=request)
    assert response.status_code == 200, response.text
    assert response.json() == {'saved': True, 'agent_id': 'subject'}
    assert count(local_setup, 'execution_bindings') == before
    policy = local_setup[2].get('/api/v1/agents/subject/execution-policy', headers=local_setup[3]['operator'])
    assert policy.json()['data']['execution_location'] == 'remote'
    retry = local_setup[2].post('/v1/connections/setup:finish', headers=local_setup[3]['operator'], json=request)
    assert retry.status_code == 200 and retry.json() == response.json()


@pytest.mark.parametrize('enabled',[True,False])
def test_finish_preserves_inherited_runtime_policy(local_setup,enabled):
    context,request=request_for(local_setup)
    with local_setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE runtime_policy_defaults SET runtime_enabled=?',(enabled,))
    request['configuration']['runtime_enabled']=None
    verified={'root':directory_identity(request['configuration']['workspace_root']),'home':None} if enabled else None
    assert finish(local_setup,context,request,verified=verified)['saved']
    assert count(local_setup,'execution_bindings') == int(enabled)
    with local_setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT runtime_enabled FROM agent_runtime_overrides WHERE agent_id=?',('subject',)).fetchone()[0] is None


def test_remote_finish_updates_approved_binding_atomically(local_setup):
    context,request=request_for(local_setup)
    created=finish(local_setup,context,request,verified={'root':directory_identity(request['configuration']['workspace_root']),'home':None})
    with local_setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_executors SET kind='remote',connector_id='connector-test',registered_by_agent_id='subject'")
    request.update(client_intent_id='remote-finish',binding_id=created['binding']['binding_id'])
    with local_setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute('DELETE FROM execution_local_realizations')
        uow.connection.execute('DELETE FROM runtime_execution_grants')
    remote_view=load_setup(local_setup[0],context,'subject',request['binding_id'])
    assert remote_view['connections'][0]['execution_location']=='remote'
    assert 'folders' not in remote_view
    request['baseline']=remote_view['baseline']
    request['configuration'].update(execution_location='remote',tool_access='ask')
    result=finish(local_setup,context,request,verified=None)
    assert result['saved']
    assert count(local_setup,'execution_bindings')==1
    view=load_setup(local_setup[0],context,'subject',request['binding_id'])
    assert view['public_config']['nexus_tool_permission']=='ask'
    assert count(local_setup,'runtime_execution_grants')==1
    assert view['authorization']=={'minutes':60,'actions':20}


def test_remote_finish_rejects_embedded_binding_without_partial_writes(local_setup):
    context,request=request_for(local_setup)
    created=finish(local_setup,context,request,verified={'root':directory_identity(request['configuration']['workspace_root']),'home':None})
    request.update(client_intent_id='remote-wrong',binding_id=created['binding']['binding_id'])
    request['baseline']=load_setup(local_setup[0],context,'subject',request['binding_id'])['baseline']
    request['configuration'].update(execution_location='remote')
    with pytest.raises(Exception,match='approved remote'):finish(local_setup,context,request,verified=None)
    assert load_setup(local_setup[0],context,'subject',request['binding_id'])['baseline']==request['baseline']
