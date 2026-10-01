"""Opt-in installed Codex/Claude journey over real loopback HTTP MCP."""
import json
import os
from pathlib import Path
import time
import asyncio
from contextlib import contextmanager
import socket
import threading

import httpx
import uvicorn

import pytest

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.http import runtime_v1
from okto_nexus.bootstrap import embedded_dispatch
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.bootstrap.local_discovery import split_discovery_args
from okto_nexus.domain.base import iso_plus
from test_binding_operator import prepare_operator
from test_embedded_dispatch import admit
from test_mcp_session_capabilities import seed_work



@contextmanager
def live_server(app,listener,origin):
    server=uvicorn.Server(uvicorn.Config(app,log_level="error",access_log=False,
                                       timeout_graceful_shutdown=5))
    errors=[]
    def serve():
        try:
            asyncio.run(server.serve(sockets=[listener]))
        except BaseException as exc:
            errors.append(exc)
    thread=threading.Thread(target=serve,name="real-mcp-campaign-server",daemon=True)
    thread.start()
    try:
        until=time.monotonic()+180
        while not server.started:
            assert not errors,repr(errors)
            assert thread.is_alive()
            assert time.monotonic()<until,"Local server startup timed out."
            time.sleep(.1)
        with httpx.Client(base_url=origin,timeout=30,follow_redirects=True,trust_env=False) as client:
            yield client
    finally:
        server.should_exit=True
        thread.join(45)
        listener.close()
        assert not thread.is_alive(),"Local server shutdown timed out."
        assert not errors,repr(errors)


@pytest.mark.skipif(os.environ.get("OKTO_NEXUS_REAL_MCP") != "1", reason="Real provider campaign is opt-in.")
@pytest.mark.parametrize("adapter",["codex_app_server","claude_stream"])
def test_real_provider_uses_automatic_local_dispatch_and_http_work(tmp_path,monkeypatch,adapter):
    codex=Path.home()/"AppData/Roaming/npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe"
    claude=Path.home()/".local/bin/claude.exe"
    binary=codex if adapter=="codex_app_server" else claude
    assert binary.is_file(),"The selected real provider executable must be installed."
    monkeypatch.setenv("PATH",str(binary.parent)+os.pathsep+os.environ.get("PATH",""))
    discovery,rest=split_discovery_args(["--harness-root",str(binary.parent)])
    assert not rest
    info = runtime_v1.protocol_info()
    monkeypatch.setattr(runtime_v1,'protocol_info',lambda:{**info,'remote_execution_ready':True})
    monkeypatch.setattr(embedded_dispatch,'protocol_info',lambda:{**info,'remote_execution_ready':True})
    deps=bootstrap({},['--home',str(tmp_path/'nexus'),'--feature-harness-integrations','true',
                       '--feature-hitl','true'])
    deps.local_discovery=discovery
    listener=socket.socket()
    listener.bind(('127.0.0.1',0))
    origin='http://127.0.0.1:'+str(listener.getsockname()[1])
    app=build_app(deps,runtime_owner_api_url=origin)
    headers={}
    with deps.connection_factory.unit_of_work() as uow:
        for actor in ('operator','subject'):
            uow.connection.execute('INSERT OR IGNORE INTO agents(agent_id,created_at) VALUES (?,?)',(actor,deps.clock.now_iso()))
            headers[actor]={'Authorization':'Bearer '+app.state.auth.issue_key(uow,agent_id=actor)}
    workspace=tmp_path/'workspace'
    workspace.mkdir()
    report={'adapter':adapter,'server_release_gate_override':True,'native_qualification_override':False,
            'protected_os_vault':True,'synthetic_native_factory':False}
    with live_server(app,listener,origin) as client:
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
        selected=next(row for row in inventory['evidence'] if row['adapter_id']==adapter)
        candidate=next(c for c in inventory_owner.candidates if c.adapter_id==adapter)
        report['passive_inventory_version']=candidate.version
        report['candidate_fingerprint']=candidate.fingerprint
        report['candidate_build_identity']=candidate.build_identity
        response=client.post(f'/v1/runtime/executors/{inventory_owner.key.executor_id}/realizations',
            headers=headers['operator'],json=dict(client_intent_id='real-mcp-setup',agent_id='subject',
                workspace_root=str(workspace),workspace_id=None,workspace_label='Real MCP campaign',
                adapter_id=adapter,candidate_ref=selected['candidate_ref'],inventory_revision=inventory['inventory_revision'],
                local_consent_id='authorized-local-provider-campaign',approved=True,provider_home=str(Path.home()),secret_bindings={}))
        assert response.status_code==201,response.text
        view=response.json()
        _,apply=prepare_operator(client,headers,dict(client_intent_id='real-mcp-binding',agent_id_hint='subject',
            executor_id=view['executor_id'],adapter_id=adapter,candidate_ref=selected['candidate_ref'],
            inventory_revision=inventory['inventory_revision'],realization_ref=view['realization_ref'],
            workspace_id=view['workspace_id'],alias='real-local-mcp'))
        response=client.post('/v1/connections/bindings:apply',json=apply,headers=headers['operator'])
        assert response.status_code==200,response.text
        binding=response.json()
        response=client.post('/api/v1/harness/grants',headers=headers['operator'],json={
            'actor_agent_id':'subject','endpoint_id':binding['endpoint_id'],
            'actions':['open','send','steer','interrupt','close'],'max_executions':3,
            'expires_at':iso_plus(deps.clock.now_iso(),600)})
        assert response.status_code==200,response.text
        setup=(deps,app,client,headers,{},candidate,workspace)
        approval_scope = None
        approved_requests = set()
        def decide_requested_tools():
            if approval_scope is None:
                return
            queued = client.get('/api/v1/approvals', headers=headers['operator'],
                params={'workspace': approval_scope['workspace_id'], 'status': 'pending'})
            assert queued.status_code == 200, queued.text
            for item in queued.json()['data']['items']:
                if item['action'] != 'execution.native.respond' or item['approval_id'] in approved_requests:
                    continue
                detail = client.get('/api/v1/approvals/'+item['approval_id'], headers=headers['operator'])
                assert detail.status_code == 200, detail.text
                proposal = detail.json()['data']['request_payload']['kwargs']
                key = proposal['approval_key']
                assert all(key[name] == approval_scope[name] for name in (
                    'server_id','executor_id','binding_id','agent_id','workspace_id','session_id','session_owner_generation'))
                # This authorized campaign approves only its three governed
                # MCP tools. Unexpected native input remains an observed failure.
                assert key['kind'] == 'native_approval', proposal['display']
                params = proposal['display']['params']
                assert params.get('tool_name') in {
                    'mcp__'+entry+'__'+name for name in ('handoff_get','handoff_claim','handoff_complete')}, proposal['display']
                arguments = params['input']
                assert arguments['project_root'] == approval_scope['workspace_id']
                assert arguments['agent_id'] == 'subject' and arguments['handoff_id'] == 'work'
                body = {name: proposal[name] for name in ('approval_key','expected_revision','request_hash','cas_token')}
                body.update(client_intent_id='real-'+item['approval_id'], decision='approve')
                decided = client.post('/v1/runtime/approval-decisions', headers=headers['operator'], json=body)
                assert decided.status_code == 202, decided.text
                replay = client.post('/v1/runtime/approval-decisions', headers=headers['operator'], json=body)
                assert replay.status_code == 200, replay.text
                assert replay.json()['native_operation_id'] == decided.json()['native_operation_id']
                approved_requests.add(item['approval_id'])
        def receipt(operation, stages):
            until=time.monotonic()+180
            while True:
                decide_requested_tools()
                result=client.get('/v1/runtime/operations/'+operation['operation_id'],headers=headers['subject']).json()
                if result.get('executor_stage') in stages:
                    return result
                assert result.get('executor_stage') not in ('FAILED','REJECTED','OUTCOME_UNKNOWN'),result
                assert owner.failure is None,repr(owner.failure)
                assert time.monotonic()<until,{'operation':operation['operation_id'],'stage':result.get('executor_stage')}
                time.sleep(.1)
        opened=admit(setup,binding,'real-mcp-open','runtime.start',new_session=True)
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
        entry=owner.tools.configurations[session]["template"].entry_name
        approval_scope = opened['scope']
        workspace_id=opened["scope"]["workspace_id"]
        sent=admit(setup,binding,'real-mcp-work','turn.submit',session_id=session,text=(
            f'Use only the MCP server {entry} for this task. Call handoff_get for handoff_id work, '
            'then handoff_claim for work, then handoff_complete '
            'for work with the returned claim_epoch and result string "Reviewed by real provider.". '
            f'For these calls use project_root "{workspace_id}" and agent_id "subject". '
            'Do not use filesystem, shell or any other MCP server. Finish with OK.'))
        report['turn_stage']=receipt(sent,('SUCCEEDED',))['executor_stage']
        report['explicit_operator_decisions'] = len(approved_requests)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            report['handoff_status']=uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id='work'").fetchone()[0]
            report['tool_claim_count']=uow.connection.execute('SELECT count(*) FROM execution_tool_claims').fetchone()[0]
            report['wss_ticket_count']=uow.connection.execute('SELECT count(*) FROM execution_link_tickets').fetchone()[0]
        assert report['handoff_status']=='COMPLETED',report
        assert report['tool_claim_count']>=1 and report['wss_ticket_count']==0,report
        closed=admit(setup,binding,'real-mcp-close','runtime.close',session_id=session)
        report['close_stage']=receipt(closed,('SUCCEEDED',))['executor_stage']
    assert not owner.tools.stored
    report['secret_removed']=True
    destination=os.environ.get('OKTO_NEXUS_REAL_MCP_REPORT')
    if destination:
        Path(destination+'-'+adapter+'.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
