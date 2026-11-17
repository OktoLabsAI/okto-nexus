"""Installed-only own canonical fixture. NO launch before Root window gate."""
import asyncio
from dataclasses import replace
from datetime import datetime,timezone
import hashlib
import importlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
ALLOC=json.loads((HERE/'allocation.json').read_text())
assert ALLOC.get('start_authorized') is True
ROOT=Path(ALLOC['root']).resolve();PREFIX=Path(ALLOC['prefix']).resolve()
assert ROOT.name.startswith('nexus-hst-') and sys.flags.isolated and sys.dont_write_bytecode
assert Path(sys.prefix).resolve()==PREFIX
sys.path.insert(0,str(ROOT/'helpers'))
from protocol_fixture import install_native,BASE_SOURCE
from peer_source import source as peer_source
from canonical_controls import Controls
from browser_surface import BrowserSurface
import pytest
from fastapi.testclient import TestClient
import uvicorn
from nexus_connector_core import InstallationCandidate
import nexus_connector_core.availability as availability
from nexus_connector_core.discovery import fingerprint
from okto_nexus.bootstrap import embedded_inventory
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.mcp.tools.identity import build_service
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.application import execution_local_observations as observations
from okto_nexus.application.terminal_connection import TerminalConnection

def write(name,value):
    (ROOT/'control'/name).write_text(json.dumps(value,indent=2)+'\n')

def main():
    assert version('okto-nexus')=='0.3.7'
    origins={n:importlib.import_module(n).__file__ for n in ['okto_nexus','nexus_connector_core','okto_nexus_connector']}
    assert all(Path(p).resolve().is_relative_to(PREFIX) for p in origins.values())
    write('origins.json',dict(origins=origins,prefix=sys.prefix,isolated=True))
    patch=pytest.MonkeyPatch();mode=ALLOC.get('mode','baseline')
    binary=ROOT/'inert-codex-candidate.exe';binary.write_bytes(b'HST inert candidate; never executed')
    candidate=replace(InstallationCandidate('codex_app_server',str(binary),fingerprint(binary),'explicit','untrusted'),architecture='x86_64')
    patch.setattr(embedded_inventory,'discover_local_candidates',lambda **kw:type('Candidates',(),{'candidates':(candidate,) if not kw.get('adapter_ids') or candidate.adapter_id in kw['adapter_ids'] else ()})())
    for name in ['qualified_build','can_probe_protocol']:patch.setattr(availability,name,lambda *a,**k:True)
    patch.setattr(availability,'containment_preflight',lambda **kw:{'job_objects':'ok'})
    async def probe(selected):
        assert selected.trust=='selected';return replace(selected,version='0.159.0')
    patch.setattr(observations,'probe_version',probe)
    deps=bootstrap({},['--home',str(ROOT/'home'),'--embedding-mode','off','--metrics-mode','disabled',
        '--metrics-dir',str(ROOT/'metrics'),'--feature-harness-integrations','true','--feature-verification','true',
        '--feature-hitl','true',
        '--runtime-handoff-auto-claim-enabled','false'])
    app=build_app(deps);identity=build_service(deps);auth=AgentKeyAuthService(deps.repos.agents,deps.clock)
    keys={};refs=[];sessions=[];peers=[];records=[];requests=[];operations=[];unknown=False
    def agent(name):
        identity.agent_register(agent_id=name,role='builder',metadata={'display_name':name.replace('-',' ').title()})
        with deps.connection_factory.unit_of_work() as uow:keys[name]=auth.issue_key(uow,agent_id=name)
    try:
      with TestClient(app,base_url='http://127.0.0.1',raise_server_exceptions=False,client=('127.0.0.1',50000)) as client:
        async def inventory():
            owner=app.state.embedded_inventory_owner
            async with asyncio.timeout(15):
                while owner.published_batch is None or any(r.state=='PENDING' for r in owner.published_batch.observations):
                    if owner.failure:raise owner.failure
                    await asyncio.sleep(.02)
        client.portal.call(inventory)
        async def inert_test(entry,request,selected):entry.update(status='succeeded',stage='Synthetic Test boundary')
        patch.setattr(app.state.connection_tests,'run',inert_test)
        def call(method,path,body=None,headers=None):
            response=client.request(method,path,json=body,headers=headers or {'X-Nexus-UI':'1'})
            records.append(dict(method=method,path=path.split('?')[0],status=response.status_code))
            assert response.status_code<400,('Canonical request refused',response.status_code,response.json().get('error',{}).get('code'))
            value=response.json();return value.get('data',value)
        workers=['hst-a','hst-b'] if mode=='scope_two' else ['hst-worker'] if mode!='idle_three' else ['hst-one','hst-two','hst-three']
        for index,name in enumerate(workers):
            agent(name);home=ROOT/('provider-'+str(index));home.mkdir()
            flow=TerminalConnection(call,lambda value:None)
            project=ROOT/('project-b' if mode=='scope_two' and index else 'project');project.mkdir(exist_ok=True)
            review=flow.review(dict(agent=name,client='codex',project=str(project),label='HST Second Project' if mode=='scope_two' and index else 'HST Demo Project',
                workspace_id=refs[0]['workspace_id'] if refs and mode!='scope_two' else None,binding_id=None,candidate_ref=None,provider_home=str(home)))
            configured=flow.apply(review,approval=review['review_revision']);assert configured['state']=='configured'
            binding=call('GET','/api/v1/runtime-management/connections/bindings/'+configured['binding_id'])
            ref={k:binding[k] for k in ['server_id','executor_id','binding_id','endpoint_id','agent_id','workspace_id','workspace_binding_id']};refs.append(ref)
            call('POST','/api/v1/runtime-management/connections/public-ids/associate-existing',dict(approved=True,
                client_intent_id='hst-id-'+str(index),connect_id='reviewer' if mode=='scope_two' else 'reviewer-'+str(index+1),expected_binding_ref=ref,expected_binding_revision=binding['binding_revision']))
        if mode=='scope_two':assert len({ref['workspace_id'] for ref in refs})==2,'Canonical projects must remain distinct'
        setup=(deps,app,client,{},None,candidate,ROOT/'project')
        peer_env={k:v for k,v in os.environ.items() if k.upper() in ['SYSTEMROOT','WINDIR','COMSPEC','PATHEXT']}
        peer_env.update(PATH='',HOME=str(ROOT/'os-home'),USERPROFILE=str(ROOT/'os-home'),PYTHONDONTWRITEBYTECODE='1')
        peers,_=install_native((setup,refs[0],None),peer_source(BASE_SOURCE,ROOT/'control'),environment=peer_env)
        def admit(ref,intent,*,operator=False,wait=True,expected='SUCCEEDED',**extra):
            nonlocal unknown
            path='/api/v1/runtime-management/runtime' if operator else '/v1/runtime'
            headers=controls.operator_headers() if operator else {'Authorization':'Bearer '+keys[ref['agent_id']],'Cookie':''}
            body=dict(client_intent_id='hst-'+str(len(operations)),intent=intent,binding_id=ref['binding_id'],workspace_binding_id=ref['workspace_binding_id'],**extra)
            if operator:body['agent_id']=ref['agent_id']
            resolution=call('POST',path+'/intents:resolve',body,headers);assert resolution['can_submit']
            call('POST',path+'/operations',{k:resolution[k] for k in ['client_intent_id','operation_id','resolution_revision','intent_hash']},headers)
            operations.append(dict(intent=intent,operation_id=resolution['operation_id'],scope=resolution['scope']))
            end=time.monotonic()+30
            while True:
                state=call('GET',path+'/operations/'+resolution['operation_id'],headers=headers)
                stage=state.get('executor_stage')
                if stage==expected:return resolution
                if stage=='SUBMITTED' and (not wait or intent=='runtime.start'):
                    if intent!='runtime.start':return resolution
                    row=call('GET','/api/v1/runtime-management/runtime/sessions/'+resolution['scope']['session_id']+'?executor_id='+ref['executor_id'])
                    if row['lifecycle_state']=='READY':return resolution
                if stage in ['OUTCOME_UNKNOWN','FAILED','CANCELLED'] or time.monotonic()>end:
                    unknown=stage=='OUTCOME_UNKNOWN' or time.monotonic()>end
                    write('blocked.json',dict(intent=intent,operation_id=resolution['operation_id'],stage=stage))
                    raise RuntimeError('Native fixture did not reach expected state')
                time.sleep(.03)
        controls=Controls(deps,app,client,ROOT,refs[0],record=records.append)
        browser_ready=False
        try:
          if mode in ['question','delayed_info']:
            controls.configure_browser_session();browser_ready=True
          for ref in refs:
            total=0 if mode in ['verification','failed_cancelled'] else 1 if mode in ['idle_three','scope_two'] else 2
            for index in range(total):
                opened=admit(ref,'runtime.start',new_session=True);sid=opened['scope']['session_id']
                sessions.append(dict(session_id=sid,reference=ref,text='HST synthetic output '+sid,closed=False))
                gated=mode in ['question','delayed_info']
                text='HST:'+json.dumps(dict(gate='release-'+str(index),question=index==0,blocking=True,message='Synthetic output')) if gated else 'HST safe fixture turn'
                admit(ref,'turn.submit',session_id=sid,text=text,operator=gated,wait=not gated)
                if not gated and index==0 and total==2:
                    admit(ref,'runtime.close',session_id=sid);sessions[-1]['closed']=True
          if mode=='failed_cancelled':
            ref=refs[0];negative=[]
            for outcome in ['failed','cancelled']:
                opened=admit(ref,'runtime.start',new_session=True);sid=opened['scope']['session_id']
                item=dict(session_id=sid,reference=ref,text='HST synthetic output '+sid,closed=False);sessions.append(item)
                gate='negative-'+outcome
                if outcome=='failed':(ROOT/'control'/gate).touch()
                turn=admit(ref,'turn.submit',session_id=sid,text='HST:'+json.dumps(dict(gate=gate,question=False,terminal_status='failed' if outcome=='failed' else 'completed')),
                    expected='FAILED' if outcome=='failed' else 'SUCCEEDED',wait=outcome=='failed')
                if outcome=='cancelled':
                    end=time.monotonic()+10;native_ids=[]
                    while not native_ids:
                        with deps.connection_factory.unit_of_work(write=False) as uow:
                            events=[json.loads(row[0]) for row in uow.connection.execute('SELECT payload_json FROM execution_event_ingress WHERE server_id=? AND executor_id=? AND session_id=?',(ref['server_id'],ref['executor_id'],sid))]
                        native_ids=[e['payload']['turn_id'] for e in events if e.get('operation_id')==turn['operation_id'] and e.get('payload',{}).get('delivery_phase')=='started']
                        assert time.monotonic()<end,'Exact native turn evidence absent'
                        if not native_ids:time.sleep(.03)
                    assert len(native_ids)==1
                    admit(ref,'turn.interrupt',session_id=sid,target=dict(kind='native_turn_id',expected_turn_id=native_ids[0]),wait=False)
                    end=time.monotonic()+20
                    while True:
                        value=call('GET','/v1/runtime/operations/'+turn['operation_id'],headers={'Authorization':'Bearer '+keys[ref['agent_id']],'Cookie':''})
                        if value.get('executor_stage')=='CANCELLED':break
                        assert time.monotonic()<end,'Canonical cancellation absent';time.sleep(.03)
                negative.append(dict(operation_id=turn['operation_id'],session_id=sid,outcome=outcome))
                admit(ref,'runtime.close',session_id=sid);item['closed']=True
            write('negative-preflight.json',negative)
          if mode in ['question','delayed_info']:
            # Wait for real committed input and productive receipt before
            # exposing a browser. Never turn a submitted intention into RUNNING
            # or a question merely by assigning a fixture flag.
            end=time.monotonic()+20
            while True:
                inputs=call('GET','/api/v1/runtime-management/runtime/input-requests')
                input_rows=inputs if isinstance(inputs,list) else inputs.get('items',[])
                turn=operations[-1]
                state=call('GET','/api/v1/runtime-management/runtime/operations/'+turn['operation_id'])
                if input_rows and state.get('executor_stage') in ['SUBMITTED','RUNNING']:
                    write('question-preflight.json',dict(requests=input_rows,parallel_operation_id=turn['operation_id'],stage=state.get('executor_stage'),
                        limits='SUBMITTED is not proof of Working; browser expected Working assertion remains independent.'))
                    break
                assert time.monotonic()<end,'Canonical question/productive receipt not ready'
                time.sleep(.05)
          j5=None
          if mode=='verification':
            creator='hst-creator';agent(creator)
            created=controls.prepare_handoff(keys[creator],creator,refs[0]['agent_id'])
            grant=controls.prepare_work_grant(refs[0]['agent_id'])
            claimed=controls.claim_handoff(keys[refs[0]['agent_id']],refs[0]['agent_id'],created['handoff_id'],grant['grant_id'])
            j5=dict(handoff_id=created['handoff_id'],claim_epoch=claimed.get('claim_epoch',1))
            end=time.monotonic()+30
            while True:
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    rows=[dict(r) for r in uow.connection.execute('SELECT o.operation_id,o.session_id FROM runtime_handoff_bindings h JOIN execution_domain_deliveries d ON d.domain_operation_id=h.operation_id JOIN execution_operations o ON o.operation_id=d.operation_id AND o.server_id=d.server_id AND o.executor_id=d.executor_id WHERE h.handoff_id=? AND o.action=?',(j5['handoff_id'],'turn.submit'))]
                if rows:
                    state=call('GET','/v1/runtime/operations/'+rows[-1]['operation_id'],headers={'Authorization':'Bearer '+keys[refs[0]['agent_id']],'Cookie':''})
                    if state.get('executor_stage')=='SUCCEEDED':break
                assert time.monotonic()<end,'Managed work terminal absent';time.sleep(.05)
            assert controls.handoff_state(keys[refs[0]['agent_id']],refs[0]['agent_id'],j5['handoff_id'])['status']=='CLAIMED'
            j5['turn']=rows[-1];sessions.append(dict(session_id=rows[-1]['session_id'],reference=refs[0],text='HST synthetic output '+rows[-1]['session_id'],closed=False));write('j5-preflight.json',j5)
          if not browser_ready:controls.configure_browser_session()
          from dataclasses import asdict
          from okto_nexus.adapters.outbound.sqlite.home_operational_facts import SESSIONS, LEASES, normalize
          with deps.connection_factory.unit_of_work(write=False) as uow:
            params=dict(server_id=refs[0]['server_id'],workspace_id=refs[0]['workspace_id'])
            fact_rows=[dict(r) for r in uow.connection.execute(SESSIONS,params)]
            lease_rows=[dict(r) for r in uow.connection.execute(LEASES,params)]
          facts=normalize(fact_rows,lease_rows,lambda:None)
          write('preclose-runtime-facts.json',dict(at=deps.clock.now_iso(),facts=[asdict(f) for f in facts],
            rows=[{k:v for k,v in row.items() if k not in ['native_metadata_json']} for row in fact_rows],
            leases=[{k:v for k,v in row.items() if k in ['session_id','lease_serial','status','applied_at','valid_until_server','scope_json','connection_id','connection_generation','owner_generation','position']} for row in lease_rows]))
          public=call('GET','/api/v1/home/harness-board?presentation_version=2&workspace_id='+refs[0]['workspace_id'],headers=controls.operator_headers())
          assert public['presentation_version']==2
          write('initial-board.json',public)
          server=None
          async def expose():
            nonlocal server
            surface=BrowserSurface(app,record=requests.append,delay_info_seconds=12 if mode=='delayed_info' else 0,allow_native_decision=ALLOC.get('allow_native_decision_post',False))
            server=uvicorn.Server(uvicorn.Config(surface,host='127.0.0.1',port=0,lifespan='off',log_level='warning',access_log=False,timeout_graceful_shutdown=3))
            sock=server.config.bind_socket();port=sock.getsockname()[1];storage=controls.write_private_storage(port)
            cards=[v for lane in public['columns'].values() for v in lane['items'] if v['kind']=='harness']
            write('ready.json',dict(url='http://127.0.0.1:'+str(port),server_id=refs[0]['server_id'],workspace_id=refs[0]['workspace_id'],
                references=refs,sessions=sessions,card_id=cards[0]['id'] if cards else None,storage=str(storage),mode=mode,j5=j5,provider_invocations=0))
            await server.serve(sockets=[sock])
          future=client.portal.start_task_soon(expose);end=time.monotonic()+300;done=set();fault=None
          try:
            while not (ROOT/'control/stop').exists() and time.monotonic()<end:
                for name in ['complete','verify','revoke-reader','partial-results','restore-results']:
                    if name in done or not (ROOT/'control'/name).exists():continue
                    if name=='complete':assert j5;controls.complete_handoff(keys[refs[0]['agent_id']],refs[0]['agent_id'],j5['handoff_id'],j5['claim_epoch'])
                    if name=='verify':assert j5;controls.verify_handoff(j5['handoff_id'],j5['claim_epoch'])
                    if name=='revoke-reader':controls.revoke_browser_session()
                    if name=='partial-results':fault=controls.unavailable_results();fault.__enter__()
                    if name=='restore-results' and fault:fault.__exit__(None,None,None);fault=None
                    done.add(name);write('controls.json',dict(done=sorted(done)))
                time.sleep(.1)
          finally:
            if fault:fault.__exit__(None,None,None)
            server.should_exit=True;future.result(timeout=15)
        finally:
          if not unknown:
            for index,item in enumerate(sessions):
                if not item['closed']:
                    try:admit(item['reference'],'runtime.close',session_id=item['session_id']);item['closed']=True
                    except BaseException as error:write('close-failure-'+str(index)+'.json',dict(type=type(error).__name__))
          write('final.json',dict(sessions=sessions,operations=operations,requests=requests,controls=records,unknown=unknown,provider_invocations=0))
    finally:patch.undo()

if __name__=='__main__':
    try:main()
    except BaseException as error:
        write('failure.json',dict(type=type(error).__name__,message=str(error)));raise
