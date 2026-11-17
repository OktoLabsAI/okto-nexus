"""Owned canonical namespaces/HTTP Finish; only test verification is inert."""
from copy import deepcopy
import json
import os
from pathlib import Path
import uuid

from test_public_connection_ids import public_request
from test_connection_setup import local_setup,request_for
from test_connection_setup_recovery import snapshot
from okto_nexus.application.execution_local_realizations import directory_identity
from okto_nexus.application.connection_project_context import read_project_context

BASE='/api/v1/runtime-management/connections'


def reserve(setup,request):
    response=setup[2].post(BASE+'/public-ids/reserve',headers=setup[3]['operator'],
        json=dict(approved=True,request=request))
    assert response.status_code==200,response.text
    return response.json()


def finish_http(setup,request,monkeypatch):
    # Existing setup test boundary: exact owned directory identity, no model.
    monkeypatch.setattr(setup[1].state.connection_tests,'verified',lambda context,value,owner:
        dict(root=directory_identity(value['configuration']['workspace_root']),home=None))
    response=setup[2].post(BASE+'/setup:finish',headers=setup[3]['operator'],json=request)
    assert response.status_code==200,response.text
    return response.json()


def write_proof(name,value):
    if os.environ.get('QC_DERIVATIVE_OUTPUT'):
        (Path(os.environ['QC_DERIVATIVE_OUTPUT'])/name).write_text(json.dumps(value,indent=2)+'\n')


def test_e09_http_mixed_case_reserve_collision_and_query_share_namespace(local_setup,monkeypatch):
    setup=local_setup
    context,legacy=request_for(setup)
    existing=finish_http(setup,legacy,monkeypatch)
    workspace=existing['binding']['workspace_id']
    context,request=public_request(setup,name='CoDeX',workspace_id=workspace)
    before=snapshot(setup[0])
    first=reserve(setup,request)
    assert first['connect_id']=='codex' and first['workspace_id']==workspace and first['state']=='reserved'
    assert snapshot(setup[0])==before
    second=deepcopy(request)
    second['client_intent_id']='case-collision-'+uuid.uuid4().hex
    second['public_connection'].update(connect_id='codex',reservation_ref='pcr_'+uuid.uuid4().hex)
    conflict=setup[2].post(BASE+'/public-ids/reserve',headers=setup[3]['operator'],
        json=dict(approved=True,request=second))
    assert conflict.status_code==409,conflict.text
    assert conflict.json()['error']['code']=='CONNECT_ID_PENDING'
    pages=[]
    for identifier in ('codex','CoDeX','CODEX'):
        response=setup[2].get(BASE+'/public-ids',headers=setup[3]['operator'],
            params=dict(workspace_id=workspace,connect_id=identifier))
        assert response.status_code==200,response.text
        pages.append(response.json())
    assert all(page['total']==1 and page['items']==pages[0]['items'] for page in pages)
    assert pages[0]['items'][0]['connect_id']=='codex'
    assert pages[0]['items'][0]['reservation_ref']==first['reservation_ref']
    assert snapshot(setup[0])==before
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM connection_public_ids').fetchone()[0]==1
    write_proof('e09-proof.json',dict(workspace_id=workspace,normalized='codex',queries=3,
        same_item=True,collision_status=409,collision_code='CONNECT_ID_PENDING',authority_tables_unchanged=True))


def test_e07_same_id_two_finish_created_workspaces_bound_with_distinct_refs_and_grants(local_setup,monkeypatch):
    setup=local_setup
    context,first=public_request(setup,name='reviewer')
    reserve(setup,first)
    a=finish_http(setup,first,monkeypatch)
    second_root=setup[6].parent/'namespace-second-project'
    second_root.mkdir()
    context,second=request_for(setup)
    second['client_intent_id']='namespace-b-'+uuid.uuid4().hex
    second['configuration'].update(workspace_root=str(second_root),workspace_label='Namespace B',alias='namespace-b')
    proof=read_project_context(setup[0],context,executor_id=second['executor_id'],project_root=str(second_root))
    second['public_connection']=dict(version=1,connect_id='reviewer',reservation_ref='pcr_'+uuid.uuid4().hex,
        project_revision=proof['project_revision'])
    reserve(setup,second)
    b=finish_http(setup,second,monkeypatch)
    pa,pb=a['public_connection'],b['public_connection']
    assert pa['state']==pb['state']=='bound' and pa['connect_id']==pb['connect_id']=='reviewer'
    ra,rb=pa['canonical_ref'],pb['canonical_ref']
    assert ra['server_id']==rb['server_id'] and ra['executor_id']==rb['executor_id']
    assert ra['agent_id']==rb['agent_id']=='subject'
    for field in ('workspace_id','binding_id','endpoint_id','workspace_binding_id'):
        assert ra[field]!=rb[field],field
    for reference in (ra,rb):
        page=setup[2].get(BASE+'/public-ids',headers=setup[3]['operator'],
            params=dict(workspace_id=reference['workspace_id'],connect_id='reviewer'))
        assert page.status_code==200,page.text
        assert page.json()['total']==1 and page.json()['items'][0]['canonical_ref']==reference
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        workspaces=[r[0] for r in uow.connection.execute('SELECT workspace_id FROM workspaces')]
        grants=[dict(r) for r in uow.connection.execute('SELECT * FROM runtime_execution_grants')]
        assert set(workspaces)=={ra['workspace_id'],rb['workspace_id']}
        assert len(grants)==2
        assert len({r['grant_id'] for r in grants})==2
        assert {(r['workspace_id'],r['endpoint_id']) for r in grants}=={
            (ra['workspace_id'],ra['endpoint_id']),(rb['workspace_id'],rb['endpoint_id'])}
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_sessions').fetchone()[0]==0
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0]==0
        assert uow.connection.execute('SELECT COUNT(*) FROM connection_setup_commits').fetchone()[0]==2
    write_proof('e07-proof.json',dict(connect_id='reviewer',canonical_refs=[ra,rb],workspace_count=2,
        distinct_grants=2,shared_grants=False,finish_commits=2,operations=0,sessions=0,
        workspace_origin='Each workspace created by canonical HTTP Finish, not seeded SQL'))
