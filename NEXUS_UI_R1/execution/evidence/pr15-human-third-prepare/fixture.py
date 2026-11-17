"""Human usability fixture: one canonical app/DB, inert test peer, no providers."""
import argparse,asyncio,hashlib,importlib,importlib.util,json,sys,tempfile,threading,time
from dataclasses import replace
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
import pytest
from observation_window import ObservationWindow
import uvicorn
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from nexus_connector_core import InstallationCandidate,encode_r4_frame,R4_PREVIEW_REVISION
ROOT=Path(__file__).resolve().parents[4];sys.path[:0]=[str(ROOT),str(ROOT/'tests/execution_r4')]
spec=importlib.util.spec_from_file_location('ui043base',ROOT/'NEXUS_UI_R1/execution/evidence/pr04-browser/fixture.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

class WallClock:
    def now_iso(self):return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')
    def now_epoch(self):return time.time()

def configure_inert_catalog(s,patch,home):
    import nexus_connector_core
    import nexus_connector_core.availability as availability
    from nexus_connector_core.discovery import fingerprint
    from okto_nexus.bootstrap import embedded_inventory
    from okto_nexus.application import execution_local_observations
    candidates=[];provider=home/'inert-provider-home';provider.mkdir();catalog=home/'catalog-stubs';catalog.mkdir()
    for adapter,name,version in [('codex_app_server','codex.exe','0.159.0'),('claude_stream','claude.exe','2.1.0')]:
        binary=catalog/name;binary.write_text('INERT USABILITY FIXTURE. NEVER EXECUTE.',encoding='utf-8')
        candidates.append(InstallationCandidate(adapter,str(binary),fingerprint(binary),'explicit','selected',version=version,architecture='x86_64'))
    paths={c.executable for c in candidates}
    patch.setattr(embedded_inventory,'discover_local_candidates',lambda **kw:SimpleNamespace(candidates=tuple(c for c in candidates if not kw.get('adapter_ids') or c.adapter_id in kw['adapter_ids'])))
    patch.setattr(nexus_connector_core,'discover_provider_home',lambda adapter:str(provider) if adapter=='claude_stream' else None)
    patch.setattr(availability,'qualified_build',lambda *a,**kw:True)
    patch.setattr(availability,'can_probe_protocol',lambda *a,**kw:True)
    patch.setattr(availability,'containment_preflight',lambda **kw:{'job_objects':'ok'})
    async def inert_probe(candidate):
        if candidate.executable not in paths:raise RuntimeError('Only owned inert candidate allowed')
        return replace(candidate,version='0.159.0' if candidate.adapter_id=='codex_app_server' else '2.1.0')
    patch.setattr(execution_local_observations,'probe_version',inert_probe)
    async def inert_test(entry,request,candidate):
        # The only execution effect replaced is the established ConnectionTests.run boundary.
        if candidate.executable not in paths:raise RuntimeError('Only owned inert test candidate allowed')
        entry.update(status='succeeded',stage='Connection verified')
    patch.setattr(s.app.state.connection_tests,'run',inert_test)
    s.app.state.test_opening_socket.portal.call(s.app.state.embedded_inventory_owner.refresh)

def seed_result(s,home):
    from tests.ui_simplification.test_entry_relations import link_handoff
    from okto_nexus.adapters.inbound.mcp.tools.artifacts import build_service
    now=s.clock.now_iso();project=home/'participant-project';project.mkdir()
    with s.factory.unit_of_work() as uow:
        c=uow.connection
        # Result link references ONLY the closed historical ui-success operation,
        # never the native human question turn. Recipient/origin stays canonical.
        link_handoff(c,now)
        c.execute("INSERT INTO execution_domain_deliveries(server_id,executor_id,operation_id,domain_operation_id) VALUES(?,?,'ui-success','entry-domain')",(s.connections[0].server_id,s.connections[0].executor_id))
        c.execute("UPDATE handoffs SET status='VERIFYING',claimed_by='B',verify_by=?,result='A short report is available for review.' WHERE handoff_id='ui-handoff-0'",(json.dumps({'kind':'agent','agent_id':'operator'}),))
        c.execute("UPDATE workspaces SET display_name='Sample project',root_realpath=? WHERE workspace_id='ws'",(str(project),))
    artifact=build_service(s.deps).artifact_upload(workspace_id='ws',filename='sample-report.txt',data=b'Synthetic usability report. No private data.',media_type='text/plain',agent_id='operator')
    with s.factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO execution_event_ingress VALUES(?,?,'ui-session-2','ui-historical-epoch',10,'ui043-result-event','turn.completed','{}',?)",(s.connections[0].server_id,s.connections[0].executor_id,now))
        uow.connection.execute("INSERT INTO execution_results VALUES(?,?,'ui-success','ui-session-2','ui-historical-epoch',10,'Synthetic usability result',0,1,'success',?)",(s.connections[0].server_id,s.connections[0].executor_id,now))
        uow.connection.execute("INSERT INTO runtime_results(result_id,payload,captured_at,operation_id,canonical_server_id,canonical_executor_id,canonical_operation_id,output_artifact_id) VALUES('ui043-result','{}',?,'entry-domain',?,?,'ui-success',?)",(now,s.connections[0].server_id,s.connections[0].executor_id,artifact['artifact_id']))
    return {'artifact_id':artifact['artifact_id'],'workspace':'ws','project_root':str(project),'question_session':s.sessions[0],'closed_session':s.sessions[1]}

def publish_fresh_question(s,state):
    """Explicit facilitator arrival: new native ID, never replay/extend the old request."""
    from okto_nexus.application.execution_events import commit_execution_events
    channel=state[5];scope=state[6]['scope']
    with s.factory.unit_of_work(write=False) as uow:
        operation=uow.connection.execute("SELECT operation_id FROM execution_operations WHERE action='turn.submit' AND session_id=? AND actor_agent_id='operator' ORDER BY created_at LIMIT 1",(s.sessions[0],)).fetchone()[0]
        sequence=uow.connection.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM execution_event_ingress WHERE session_id=? AND stream_epoch='native-epoch'",(s.sessions[0],)).fetchone()[0]
    proposal=dict(schema_version=1,request_id=8,request_hash=hashlib.sha256(b'own-usability-fresh-question').hexdigest(),method='item/tool/requestUserInput',params=dict(turnId='native-turn',itemId='usability-fresh',isBlocking=True,questions=[dict(id='usability-choice',header='Choice',question='Choose the next step',isOther=True,options=[dict(label='Continue',description='Proceed with the reviewed work'),dict(label='Stop',description='End this work')])]))
    event=dict(server_id=channel.server_id,executor_id=channel.executor_id,session_id=s.sessions[0],stream_epoch='native-epoch',sequence=sequence,category='input_request',operation_id=operation,payload=dict(native_approval=proposal,native_approval_display=proposal))
    frame={k:scope[k] for k in ('server_id','executor_id','binding_id','agent_id','session_id')};frame.update(protocol_major=1,contract_revision=R4_PREVIEW_REVISION,type='event.batch',connection_id=channel.connection_id,connection_generation=channel.connection_generation,stream_epoch='native-epoch',events=[event])
    commit_execution_events(s.factory,channel=channel,frame=frame,approvals=s.deps.approvals)
    with s.factory.unit_of_work(write=False) as uow:
        row=uow.connection.execute("SELECT canonical_request_id,received_at,expires_at FROM execution_native_requests WHERE session_id=? AND source_sequence=?",(s.sessions[0],sequence)).fetchone()
    return dict(row)

async def serve(s,args,home,identities,stop,diagnostics):
    actions=[];started=time.monotonic();window=ObservationWindow(started,args.duration);static=ROOT/'src/okto_nexus/adapters/inbound/http/static'
    if args.expected_bundle not in(static/'index.html').read_text():raise RuntimeError('Frozen bundle guard')
    allowed_suffixes=('setup:test','setup:finish','setup:recover','installations:check','authorizations:review')
    async def app(scope,receive,send):
        if scope['type']!='http':return await s.app(scope,receive,send)
        path=scope['path'];method=scope['method'];stamp=datetime.now(timezone.utc).isoformat()
        if path=='/__ui043/action' and method=='GET':
            from urllib.parse import parse_qs
            q=parse_qs(scope.get('query_string',b'').decode());label=q.get('label',[''])[0][:120]
            actions.append({'at':stamp,'type':'ui_action','label':label});return await JSONResponse({'recorded':True})(scope,receive,send)
        permitted=method in{'GET','HEAD','OPTIONS'} or(method=='POST' and(path.endswith(allowed_suffixes) or path=='/api/v1/runtime-management/runtime/approval-decisions' or path.startswith('/api/v1/attention/') and path.endswith(('/seen','/unseen','/snooze','/unsnooze'))))
        if not permitted:return await JSONResponse({'fixture':'Only canonical usability setup/decision/viewing writes allowed; runtime/provider execution disabled'},status_code=405)(scope,receive,send)
        if any(k==b'authorization' for k,v in scope['headers']):
            return await JSONResponse({'fixture':'Use canonical loopback operator; bearer impersonation not accepted'},status_code=403)(scope,receive,send)
        async def logged(message):
            if message['type']=='http.response.start':actions.append({'at':stamp,'type':'http','method':method,'path':path,'status':message['status']})
            await send(message)
        return await s.app(scope,receive,logged)
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=0,lifespan='off',log_level='warning',timeout_graceful_shutdown=3));sock=server.config.bind_socket()
    s.app.state.server=server
    pins={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(__file__).with_name('observation_window.py'),ROOT/'NEXUS_UI_R1/execution/fixtures.py',static/'index.html',static/'assets'/args.expected_bundle]}
    with s.factory.unit_of_work(write=False) as uow:
        authority_times=[dict(row) for row in uow.connection.execute("SELECT l.binding_id,t.expires_at AS lane_ticket_expires_at FROM execution_control_lanes l JOIN execution_link_tickets t ON t.ticket_id=l.ticket_id")]
        grants=[dict(row) for row in uow.connection.execute("SELECT grant_id,expires_at,max_executions FROM runtime_execution_grants")]
    ready={'url':'http://127.0.0.1:'+str(sock.getsockname()[1]),'home':str(home),'identities':identities,'observation_window_seconds':args.duration,'extend_read_window_file':str(args.ready_file.with_name('extend-read-window.json')),'extension_scope':'Observation only; no grant, ticket or native request expiry change','decision_authority_times':authority_times,'original_grants':grants,'authority_limit':'Each native request expires120s after ingress; original control-lane ticket normally10min. No hidden grant or lane-ticket renewal; UI observation starts60min and can be extended explicitly without changing authority.','facilitator_trigger':str(args.ready_file.with_name('publish-fresh-question')),'trigger_policy':'Only after root starts task3, never under an existing human draft. New request8/source-sequence, same admitted operator turn/grant; old request expiry remains immutable.','provider_calls':0,'native_binary_calls':0,'test_is_simulated':True,'loopback_operator':True,'source_sha256':pins,'fixture_pid':__import__('os').getpid()}
    args.ready_file.write_text(json.dumps(ready,indent=2),encoding='utf-8');print(json.dumps({'READY':ready['url'],'ready_file':str(args.ready_file)}),flush=True)
    async def watch():
        while not server.should_exit:
            args.ready_file.with_name('actions.json').write_text(json.dumps(actions,indent=2),encoding='utf-8')
            args.ready_file.with_name('peer-status.json').write_text(json.dumps(diagnostics[-10:],indent=2),encoding='utf-8')
            extension=window.consume(args.ready_file.with_name('extend-read-window.json'),time.monotonic())
            if extension:diagnostics.append({'at':s.clock.now_iso(),'kind':'observation_window_control',**extension})
            if args.stop_file.exists() or window.expired(time.monotonic()):server.should_exit=True;return
            await asyncio.sleep(1)
    task=asyncio.create_task(watch())
    try:await server.serve(sockets=[sock])
    finally:task.cancel();sock.close();stop.set();args.ready_file.with_name('actions.json').write_text(json.dumps(actions,indent=2),encoding='utf-8')

def main():
    p=argparse.ArgumentParser();p.add_argument('--ready-file',type=Path,required=True);p.add_argument('--stop-file',type=Path,required=True);p.add_argument('--expected-bundle',required=True);p.add_argument('--duration',type=int,default=3600);args=p.parse_args()
    if not 60<=args.duration<=3600:p.error('finite60..3600seconds required')
    opening=importlib.import_module('test_open_bootstrap');lease_helper=importlib.import_module('test_session_capabilities');original=opening.opening.__wrapped__;captured={};stop=threading.Event();diagnostics=[]
    def observe(*a,**kw):
        gen=original(*a,**kw);value=next(gen);captured['state']=value
        try:yield value
        finally:gen.close()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(opening.opening,'__wrapped__',observe)
        home=Path(tempfile.mkdtemp(prefix='nexus-ui043-third-'))
        with base.fixtures.scenario(home,recipient='operator',clock=WallClock()) as s:
            identities=seed_result(s,home);configure_inert_catalog(s,patch,home)
            state=captured['state'];channel=state[5];ws=s.app.state.test_opening_socket
            # Existing canonical maintenance helper rebuilds the actual owned
            # original candidate and PUTs with the authenticated channel ticket.
            # It asserts unchanged inventory_revision; never edit freshness SQL.
            from ns14_load import refresh_inventory
            producer_client=TestClient(s.app,base_url='https://127.0.0.1:8202')
            frame=dict(protocol_major=1,contract_revision=R4_PREVIEW_REVISION,type='heartbeat',**channel.identity())
            def peer():
                last_renew=time.monotonic();last_inventory=0.0;fresh_published=False
                while not stop.wait(2):
                    try:
                        ws.send_text(encode_r4_frame(frame).decode())
                        if not fresh_published and args.ready_file.with_name('publish-fresh-question').exists():
                            arrival=publish_fresh_question(s,state);fresh_published=True
                            args.ready_file.with_name('fresh-question-arrival.json').write_text(json.dumps(arrival,indent=2),encoding='utf-8')
                            diagnostics.append({'at':s.clock.now_iso(),'kind':'explicit_fresh_question_arrival',**arrival})
                        if time.monotonic()-last_inventory>=30:
                            refresh_inventory(state,home,producer_client);last_inventory=time.monotonic()
                            diagnostics.append({'at':s.clock.now_iso(),'kind':'canonical_inventory_published'})
                        if time.monotonic()-last_renew>=15:
                            with s.factory.unit_of_work(write=False) as uow:serial=uow.connection.execute('SELECT MAX(lease_serial) FROM execution_leases WHERE session_id=?',(s.sessions[0],)).fetchone()[0]
                            service,_,grant,ack=lease_helper.apply_lease(state,serial=serial,purpose='renew',request_id=f'ui043-renew-{serial}');service.applied(ack,channel=channel);last_renew=time.monotonic();diagnostics.append({'at':s.clock.now_iso(),'kind':'lease_applied','serial':grant['lease_serial']})
                    except Exception as e:diagnostics.append({'at':s.clock.now_iso(),'kind':'peer_failed','type':type(e).__name__,'error':str(e)});return
            thread=threading.Thread(target=peer,name='own-ui043-inert-peer',daemon=True);thread.start()
            try:asyncio.run(serve(s,args,home,identities,stop,diagnostics))
            finally:stop.set();thread.join(5);producer_client.close()
    args.ready_file.with_name('cleanup.json').write_text(json.dumps({'peer_thread_stopped':not thread.is_alive(),'wss_lifespan_factory_closed':True}),encoding='utf-8');print('CLOSED human fixture peer/WSS/factory',flush=True)
if __name__=='__main__':main()
