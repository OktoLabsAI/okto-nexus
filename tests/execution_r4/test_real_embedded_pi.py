"""Opt-in real Pi journey; Server release gate is test-only, native gate is real."""
import json
import os
from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.http import runtime_v1
from okto_nexus.bootstrap import embedded_dispatch
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.bootstrap.local_discovery import split_discovery_args
from okto_nexus.domain.base import iso_plus
from test_binding_operator import prepare_operator
from test_embedded_dispatch import admit
from test_mcp_session_capabilities import seed_work


@pytest.mark.skipif(os.environ.get('OKTO_NEXUS_REAL_PI') != '1', reason='Real Pi campaign is opt-in.')
def test_real_pi_uses_automatic_local_dispatch_and_native_work(tmp_path, monkeypatch):
    home = Path(os.environ.get('OKTO_NEXUS_REAL_PI_HOME', str(Path.home()/'.pi/agent')))
    node = Path(os.environ.get('OKTO_NEXUS_REAL_PI_NODE', 'C:/Program Files/nodejs/node.exe'))
    discovery, rest = split_discovery_args(['--harness-root',str(node.parent),
        '--harness-root',str(home/'install'),'--pi-install-root',str(home/'install'),'--pi-node',str(node)])
    assert not rest
    info = runtime_v1.protocol_info()
    monkeypatch.setattr(runtime_v1,'protocol_info',lambda:{**info,'remote_execution_ready':True})
    monkeypatch.setattr(embedded_dispatch,'protocol_info',lambda:{**info,'remote_execution_ready':True})
    deps=bootstrap({},['--home',str(tmp_path/'nexus'),'--feature-harness-integrations','true'])
    deps.local_discovery=discovery
    app=build_app(deps,runtime_owner_api_url='http://127.0.0.1:8202')
    headers={}
    with deps.connection_factory.unit_of_work() as uow:
        for actor in ('operator','subject'):
            uow.connection.execute('INSERT OR IGNORE INTO agents(agent_id,created_at) VALUES (?,?)',(actor,deps.clock.now_iso()))
            headers[actor]={'Authorization':'Bearer '+app.state.auth.issue_key(uow,agent_id=actor)}
    workspace=tmp_path/'workspace'
    workspace.mkdir()
    report={'adapter':'pi_rpc','server_release_gate_override':True,'native_qualification_override':False,
            'protected_os_vault':True,'synthetic_native_factory':False}
    with TestClient(app,raise_server_exceptions=False) as client:
        owner=app.state.embedded_dispatch_owner
        inventory_owner=app.state.embedded_inventory_owner
        until=time.monotonic()+300
        while True:
            inventory_view=client.get(f'/v1/runtime/executors/{inventory_owner.key.executor_id}/inventory',
                                     headers=headers['operator']).json()
            if inventory_view.get('freshness')=='FRESH':
                inventory=inventory_view['snapshot']
                break
            assert inventory_owner.failure is None,repr(inventory_owner.failure)
            assert time.monotonic()<until,inventory_view.get('freshness')
            time.sleep(.25)
        selected=next(row for row in inventory['evidence'] if row['adapter_id']=='pi_rpc')
        candidate=next(c for c in inventory_owner.candidates if c.adapter_id=='pi_rpc')
        report['version']=candidate.version
        response=client.post(f'/v1/runtime/executors/{inventory_owner.key.executor_id}/realizations',
            headers=headers['operator'],json=dict(client_intent_id='real-pi-setup',agent_id='subject',
                workspace_root=str(workspace),workspace_id=None,workspace_label='Real Pi campaign',
                adapter_id='pi_rpc',candidate_ref=selected['candidate_ref'],inventory_revision=inventory['inventory_revision'],
                local_consent_id='authorized-local-provider-campaign',approved=True,provider_home=str(Path.home()),secret_bindings={}))
        assert response.status_code==201,response.text
        view=response.json()
        _,apply=prepare_operator(client,headers,dict(client_intent_id='real-pi-binding',agent_id_hint='subject',
            executor_id=view['executor_id'],adapter_id='pi_rpc',candidate_ref=selected['candidate_ref'],
            inventory_revision=inventory['inventory_revision'],realization_ref=view['realization_ref'],
            workspace_id=view['workspace_id'],alias='real-local-pi'))
        response=client.post('/v1/connections/bindings:apply',json=apply,headers=headers['operator'])
        assert response.status_code==200,response.text
        binding=response.json()
        response=client.post('/api/v1/harness/grants',headers=headers['operator'],json={
            'actor_agent_id':'subject','endpoint_id':binding['endpoint_id'],
            'actions':['open','send','steer','interrupt','close'],'max_executions':3,
            'expires_at':iso_plus(deps.clock.now_iso(),600)})
        assert response.status_code==200,response.text
        setup=(deps,app,client,headers,{},candidate,workspace)
        def receipt(operation, stages):
            until=time.monotonic()+180
            while True:
                result=client.get('/v1/runtime/operations/'+operation['operation_id'],headers=headers['subject']).json()
                if result.get('executor_stage') in stages:
                    return result
                assert result.get('executor_stage') not in ('FAILED','REJECTED','OUTCOME_UNKNOWN'),result
                assert owner.failure is None,repr(owner.failure)
                assert time.monotonic()<until,{'operation':operation['operation_id'],'stage':result.get('executor_stage')}
                time.sleep(.1)
        opened=admit(setup,binding,'real-pi-open','runtime.start',new_session=True)
        report['open_stage']=receipt(opened,('SUBMITTED','SUCCEEDED'))['executor_stage']
        session=opened['scope']['session_id']
        seed_work(setup,workspace=opened['scope']['workspace_id'])
        until=time.monotonic()+120
        while True:
            with deps.connection_factory.unit_of_work(write=False) as uow:
                serial=uow.connection.execute("SELECT MAX(lease_serial) FROM execution_leases WHERE status='ACTIVE'").fetchone()[0]
            if serial>=2: break
            assert owner.failure is None,repr(owner.failure)
            assert time.monotonic()<until
            time.sleep(.1)
        report['lease_serial_before_turn']=serial
        sent=admit(setup,binding,'real-pi-work','turn.submit',session_id=session,text=(
            'Use only the Nexus native tools for this task. Call nexus_handoff_get for handoff_id work, '
            'then nexus_handoff_claim for work with idempotency_key real-pi-work, then nexus_handoff_complete '
            'for work with the returned claim_epoch and result {"summary":"Reviewed by real Pi."}. '
            'Do not use filesystem or shell tools. Finish with OK.'))
        report['turn_stage']=receipt(sent,('SUCCEEDED',))['executor_stage']
        with deps.connection_factory.unit_of_work(write=False) as uow:
            report['handoff_status']=uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id='work'").fetchone()[0]
            report['native_action_count']=uow.connection.execute('SELECT count(*) FROM execution_native_actions').fetchone()[0]
            report['wss_ticket_count']=uow.connection.execute('SELECT count(*) FROM execution_link_tickets').fetchone()[0]
        assert report['handoff_status']=='COMPLETED',report
        assert report['native_action_count']>=3 and report['wss_ticket_count']==0,report
        closed=admit(setup,binding,'real-pi-close','runtime.close',session_id=session)
        report['close_stage']=receipt(closed,('SUCCEEDED',))['executor_stage']
        client.portal.call(owner.close)
        assert not owner.tools.stored
        report['secret_removed']=True
    destination=os.environ.get('OKTO_NEXUS_REAL_PI_REPORT')
    if destination:
        Path(destination).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
