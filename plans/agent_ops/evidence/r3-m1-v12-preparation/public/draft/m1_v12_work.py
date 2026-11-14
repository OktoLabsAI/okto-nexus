"""One authorized finite successor work request through canonical actor APIs."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
from urllib.parse import quote
sys.path.insert(0,str(Path(__file__).parent))
from campaign_context import load,require
X=load()  # approval and exact proposal gate precede product imports and effects
P,C,ROOT=X.P,X.C,X.ROOT
sys.path.insert(0,str(X.modules))
from controller import POLICY
from independent_journal import CanonicalIntentReader, CoreJournalReader, reader_error_metadata
from serial_flow import SerialFlow
from cli_flow import CLIFlow
from history_observers import attach_existing_work
sys.path.insert(0,str(Path(P['execution_bundle']['files']['response_loss']['path']).parent))
from response_loss import CampaignState,FiniteResponseLoss
from publication import poll_and_publish,publish_live
from okto_nexus.application.terminal_connection import ConnectionError,document_revision
from okto_nexus.adapters.inbound.cli.terminal_target import resolve_terminal_target
from okto_nexus.adapters.inbound.cli.service import resolve_local_service
import okto_nexus

require(len(X.remaining)==2 and X.remaining[0] in ('local','connector') and X.remaining[1] in ('useful','continuation'),'WORK_SELECTION_INVALID')
LANE,PHASE=X.remaining
if LANE=='connector':
    from supervisor_check import require_work_owner
    require_work_owner(X)  # fresh read of exact post-setup PID/birth/generation before work
pin=P['package_pins']
profile=P['execution_bundle']['profiles'][LANE]
request=profile+'-work-'+('01' if PHASE=='useful' else '02')
require(request in P['request_ids']['work'],'INTENT_OUTSIDE_PROPOSAL')
assert not (ROOT/'public'/(request+'-result.json')).exists()
controller=X.controller()
driverpath=ROOT/'private/response-loss.json'
faults=CampaignState(driverpath,**({'campaign_id':'m1-v12'} if not driverpath.exists() else {}))
flows={}; raw_flows={}; bindings={}; observed={}; stops=[]; handles=[]; selected_decisions=set()
recovered_decisions={}
publication_diagnostics={}
final_publication_diagnostics={}
pending_publication_diagnostics={}
configuration_events={}
call_counts={'GET':0,'POST':0,'productive_posts':0,'decision_posts':0}

def capture_configuration(page):
    fields=('approvalPolicy','approvalsReviewer','cwd','instructionSources','model','modelProvider','sandbox','reasoningEffort')
    for event in page.get('events',[]):
        if event.get('native_type')!='core/codex_thread_configuration':continue
        payload=event['payload']
        record={key:event.get(key) for key in ('server_id','executor_id','session_id','stream_epoch','sequence','category','native_type','operation_id')}
        record['observation']={key:payload.get(key) for key in ('schema_version','adapter_id','source','thread_id')}
        record['observation']['fields']={field:{key:value for key,value in payload.get('fields',{}).get(field,{'status':'missing'}).items()
            if key in ('status','value','reason')} for field in fields}
        require(len(json.dumps(record).encode())<=52000,'CONFIGURATION_OBSERVATION_UNBOUNDED')
        key=(event['server_id'],event['executor_id'],event['session_id'],event['stream_epoch'],event['sequence'])
        configuration_events[key]=record

def replay_configuration(flow,session):
    # Existing canonical read path only. Continuation may start after the opening
    # metadata cursor; recover that event from0 without a new native operation.
    after=0
    for _ in range(100):
        page=flow.events(session_id=session,after_sequence=after)['events']
        require(not page['gap_pending'],'CONFIGURATION_REPLAY_GAP')
        capture_configuration(page)
        if any(item['session_id']==session for item in configuration_events.values()):return
        if not page['has_more']:return
        after=page['next_after_sequence']
    raise RuntimeError('CONFIGURATION_REPLAY_LIMIT')

def stop_owner(lane):
    component='nexus' if lane=='local' else 'connector'
    out=(ROOT/'private'/(component+'-stop-wrapper.stdout')).open('xb')
    err=(ROOT/'private'/(component+'-stop-wrapper.stderr')).open('xb')
    handles.extend((out,err))
    child=subprocess.Popen(X.stop_argv(component),
        cwd=ROOT,env=X.env(),stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    stops.append(child)
    return {'pid':child.pid}

def attach(lane):
    name=P['execution_bundle']['profiles'][lane]
    args=C['service_selection_args'] if lane=='local' else ['--home',P['paths']['operator_home']]
    service=resolve_terminal_target(args,name,None if lane=='local' else P['execution_bundle']['operator_profile'],resolve_local_service)
    expected_home=Path(P['paths']['server_home' if lane=='local' else 'operator_home']).resolve()
    require(service.adapter.home.resolve()==expected_home,'ACTOR_HOME_MISMATCH')
    require(expected_home.is_relative_to(ROOT.resolve()),'ACTOR_HOME_OUTSIDE_CAMPAIGN')
    flow=CLIFlow(service,name,args,None if lane=='local' else P['execution_bundle']['operator_profile'])
    transport=flow.call
    # Bound individual requests; any unknown observation closes admissions.
    flow.set_timeout(30)  # accounting and deadline ticks do not wait for this worker
    checkpoint=service.adapter.home/'terminal/work'/(name+'.json')
    def load():return json.loads(checkpoint.read_text())
    def counted(method,path,body=None):
        call_counts[method]=call_counts.get(method,0)+1
        if method=='POST' and path.endswith('/runtime/operations'):
            slot=load().get('work',{})
            if slot.get('submission')==body:call_counts['productive_posts']+=1
        if method=='POST' and path.endswith('/runtime/approval-decisions'):call_counts['decision_posts']+=1
        return transport(method,path,body)
    flow.call=FiniteResponseLoss(counted,load,faults,lane)
    original=flow.observe
    def observe(**kwargs):
        value=original(**kwargs); observed[lane]=value
        capture_configuration(value.get('events',{}))
        return value
    flow.observe=observe
    raw_flows[lane]=flow
    controller.attach_api_flow(lane,flow)
    owner=P['paths']['server_home'] if lane=='local' else P['paths']['connector_state']
    controller.attach_owner(lane,owner,lambda:stop_owner(lane))
    facade=SerialFlow(controller,flow,lane,lambda:poll_and_publish(controller,
        lambda value:public_write('live-accounting.json',value),publication_diagnostics,request))
    flows[lane]=facade
    return facade

def public_write(name,value):
    target=ROOT/'public'/name
    pending=target.with_suffix('.pending')
    with pending.open('w',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2);stream.flush();os.fsync(stream.fileno())
    os.replace(pending,target)

def publish_approval(flow,detail):
    approval=detail['approval_id']; proposal=detail['request_payload']['kwargs']
    key=proposal['approval_key']; revision=document_revision(proposal)
    assert key['session_id']==controller.data['requests'][request]['session']
    # Only current canonical request metadata, never response/output/auth headers.
    published=publish_live(lambda value:public_write('pending-native-request.json',value),
        {'request_id':request,'approval_id':approval,'review_revision':revision,
         'approval_key':key,'display':proposal['display'],'policy':'No decision until the actual command is reviewed against the exact source/output and approved successor constraints.'},
        pending_publication_diagnostics)
    if not published:return  # no decision from an unavailable/stale public snapshot
    decision_path=ROOT/'private'/(approval+'-reviewed-decision.json')
    if not decision_path.exists() or approval in selected_decisions:return
    current=controller.data['requests'][request]
    if (current['stop_selected'] or controller.data['faults'] or
            controller.summary()['known_observed_tokens']>=POLICY['preventive_cumulative_tokens']):return
    if selected_decisions or any(d['lane']==LANE for d in faults.data['decisions']):return
    # The successor permits only one native decision per lane, across process restarts too.
    decision=json.loads(decision_path.read_text())
    assert decision['approval_id']==approval and decision['review_revision']==revision
    assert decision['decision'] in ('approve','deny')
    selected_decisions.add(approval)
    if LANE=='connector' and 'decision' not in faults.data['faults']:faults.arm('decision',LANE,approval)
    public_write(approval+'-decision-selection.json',{'approval_id':approval,'review_revision':revision,'decision':decision['decision'],'selected_before_dispatch':True})
    try:flow.decide(approval,decision['decision'],reviewed_revision=revision,session_id=key['session_id'])
    except ConnectionError as error:
        if error.stage!='m1_response_loss':raise
        public_write(approval+'-response-lost.json',{'approval_id':approval,'possible_effect':True,'replay':False})

def recover_decisions(flow):
    # Always GET, including after an answered request leaves the pending list.
    for approval in selected_decisions-recovered_decisions.keys():
        metadata=flow.document['decision']
        assert metadata['approval_key']['canonical_request_id']==approval
        detail=flow.decision_detail(approval,session_id=metadata['approval_key']['session_id'])
        existing=detail.get('executed_result') or {}
        if not existing.get('decision_id'):continue
        receipt=flow.api('GET','/runtime/approval-decisions/'+quote(existing['decision_id'],safe=''))
        assert receipt['decision_id']==existing['decision_id'] and receipt['canonical_state']=='CONFIRMED'
        assert receipt['approval_key']==metadata['approval_key'] and receipt['request_hash']==metadata['request_hash']
        assert receipt['client_intent_id']==metadata['client_intent_id']
        recovered_decisions[approval]={k:receipt.get(k) for k in ('decision_id','client_intent_id','canonical_state','native_stage','actor_agent_id','request_hash','approval_key')}
        public_write(approval+'-recovered-decision.json',dict(recovered_decisions[approval],recovery='GET_ONLY_NO_REPEAT_POST'))

started=time.time();started_monotonic_ns=time.monotonic_ns();intervals=[];previous=None;submission_error=None
try:
    active_lanes={r['lane'] for r in controller.data['requests'].values() if r['kind']=='work'}|{LANE}
    # Retain the setup home callback even when observing remote work.
    controller.attach_owner('local',P['paths']['server_home'],lambda:stop_owner('local'))
    for lane in sorted(active_lanes):attach(lane)
    # Restore all historical observers before the first API job can pump
    # the global ledger. No binding, decision or final GET runs on owner.
    attach_existing_work(controller,campaign_root=ROOT,server_home=P['paths']['server_home'],
        connector_state=P['paths']['connector_state'],stop_for_lane=stop_owner)
    for lane in sorted(active_lanes):
        binding=flows[lane].binding();bindings[lane]=binding
        if lane not in controller._readers:
            me=flows[lane].api('GET','/connections/me')
            require(me['server_id']==binding['server_id'],'ACTOR_SERVER_MISMATCH')
            selected={k:binding[k] for k in ('server_id','executor_id','binding_id','agent_id','workspace_id','workspace_binding_id')}
            controller.attach_observer(lane,CanonicalIntentReader(ROOT,P['paths']['server_home'],
                server_id=binding['server_id'],actor_id=me['agent_id'],pre_scope=selected),
                CoreJournalReader(ROOT,P['paths']['server_home' if lane=='local' else 'connector_state'],lane))
        raw_flows[lane].expect(binding,controller._readers[lane].actor_id,raw_flows[lane].document.get('session_id'))
    flow=flows[LANE]
    if LANE=='connector' and PHASE=='useful':faults.arm('admission',LANE,request)
    text=P['finite_work']['request'] if PHASE=='useful' else P['finite_work']['continuation']
    project=P['paths']['local_project' if LANE=='local' else 'remote_project']
    deliverables=P['paths']['local_deliverables' if LANE=='local' else 'remote_deliverables']
    text=text.replace('<project>',project).replace('<lane_deliverables>',deliverables)
    if PHASE=='useful':assert not (Path(deliverables)/'report.json').exists()
    public_write(request+'-dispatch-selection.json',{'request_id':request,'lane':LANE,'phase':PHASE,'time':started,'prompt_sha256':hashlib.sha256(text.encode()).hexdigest(),'client_pin':pin})
    controller.start_work(request,LANE,text,binding=bindings[LANE],checkpoint=flow.document,
        stage='useful_work' if PHASE=='useful' else 'continuation')
    while True:
        now=time.monotonic()
        if previous is not None:intervals.append(now-previous)
        previous=now
        summary=poll_and_publish(controller,lambda value:public_write('live-accounting.json',value),publication_diagnostics,request)
        current=controller.data['requests'][request]
        returned=controller.take_api_result()
        if returned is not None:
            require(returned['label']==request,'DISPATCH_RESULT_MISMATCH')
            if not returned['ok']:
                error=returned['error']
                submission_error={'code':getattr(error,'code','UNKNOWN'),'stage':getattr(error,'stage','unknown'),
                    'possible_effect':bool(getattr(error,'possible_effect',False))}
        if current['settled'] and controller.api.thread is None:break
        if current['stop_selected'] and current['stop_selected']['action']=='stop_owner' and stops and all(p.poll() is not None for p in stops):
            break
        if controller.api.thread is None and current.get('stream') and not current['stop_selected']:
            value=flow.observe(session_id=current['session'])
            for detail in value.get('requests',{}).get('items',[]):publish_approval(flow,detail)
            recover_decisions(flow)
        if current['stop_selected'] and current['stop_selected']['action']=='stop_owner' and stops and all(p.poll() is not None for p in stops):
            # Attempted stop is reported as such; no termination/usage guarantee.
            break
        time.sleep(.2)
    # Drain before any snapshot: a returned stop wrapper does not prove
    # native exit, and a late worker result may add usage or diagnostics.
    controller.drain_api()
    late=controller.take_api_result()
    if late is not None and not late['ok']:
        error=late['error']
        submission_error=submission_error or {'code':getattr(error,'code','UNKNOWN'),
            'stage':getattr(error,'stage','unknown'),'possible_effect':bool(getattr(error,'possible_effect',False))}
    controller.poll()
    current=controller.data['requests'][request]
    report=Path(deliverables)/'report.json'
    if current['settled'] and current.get('session') and not controller.data['faults']:
        replay_configuration(flow,current['session'])
    output={'exists':report.exists()}
    if report.exists():
        raw=report.read_bytes()
        if len(raw)<=4096:
            try:
                parsed=json.loads(raw)
                output.update(sha256=hashlib.sha256(raw).hexdigest(),matches_expected=parsed==P['finite_work']['delivery']['expected_shape'])
            except ValueError:output['matches_expected']=False
    receipt_metadata=None
    operation_id=controller.data['requests'][request].get('operation')
    if operation_id and current['settled'] and not controller.data['faults']:
        receipt=flow.operation(operation_id,flow.binding())
        receipt_metadata={k:receipt.get(k) for k in ('operation_id','executor_stage','admission_state','action','possible_effect')}
        output_text=(receipt.get('result') or {}).get('output_text')
        if isinstance(output_text,str):
            import re
            receipt_metadata['output_sha256']=hashlib.sha256(output_text.encode()).hexdigest()
            receipt_metadata['output_characters']=len(output_text)
            receipt_metadata['standalone_10_mentions']=len(re.findall(r'(?<!\d)10(?!\d)',output_text))
    useful_confirmed=(PHASE=='useful' and output.get('matches_expected') is True
        and receipt_metadata is not None and receipt_metadata.get('executor_stage')=='SUCCEEDED')
    result={'request_id':request,'started':started,'finished':time.time(),'started_monotonic_ns':started_monotonic_ns,
            'finished_monotonic_ns':time.monotonic_ns(),'summary':controller.summary(),
            'useful_result_confirmed':useful_confirmed,
            'useful_confirmed_monotonic_ns':time.monotonic_ns() if useful_confirmed else None,
            'record':controller.data['requests'][request],'report':output,'submission_error':submission_error,
            'maximum_poll_start_interval_seconds':controller.data.get('independent_observation',{}).get('maximum_poll_start_interval_seconds'),
            'outer_loop_interval_seconds':max(intervals,default=0),'calls':call_counts,
            'independent_observation':controller.data.get('independent_observation'),
            'preopen_failure':current.get('preopen_failure'),
            'publication_diagnostics':publication_diagnostics,'pending_publication_diagnostics':pending_publication_diagnostics,
            'codex_thread_configuration':list(configuration_events.values()),
            'configuration_observation_limit':'Canonical Core metadata only: missing/invalid stays unknown; instructionSources are references, not file contents or enforcement proof; no complete tool inventory is inferred.',
            'decision_count':len(selected_decisions),'recovered_decisions':recovered_decisions,'response_loss':faults.snapshot(),'canonical_receipt':receipt_metadata,
            'cli_execution':{lane:flow.diagnostics() for lane,flow in raw_flows.items()},
            'stop_wrapper_exits':[p.returncode for p in stops],'native_policy_fields':'Only fields actually reported in canonical evidence are attributable; unknown inherited settings remain unknown.'}
    public_write(request+'-result.json',result)
    print(json.dumps(result),flush=True)
except BaseException as error:
    # A runner failure after dispatch must not silently abandon owned work.
    controller.fault('CAMPAIGN_RUNNER_EXCEPTION')
    containment_error=None
    try:controller.poll()
    except BaseException as failed:containment_error=type(failed).__name__
    while any(p.poll() is None for p in stops):
        try:controller.poll()
        except BaseException:pass
        time.sleep(.2)
    controller.drain_api()
    # Best-effort final public projection follows fault and retained-worker
    # drain. The canonical checkpoint remains authority if publication fails.
    try:
        publish_live(lambda value:public_write('live-accounting.json',value),
            {'time':time.time(),'summary':controller.summary(),'active_request':request},
            final_publication_diagnostics)
    except BaseException as publication_error:
        final_publication_diagnostics['error_type']=type(publication_error).__name__
    public_write(request+'-runner-error.json',{'error_type':type(error).__name__,
        'cli_execution':{lane:flow.diagnostics() for lane,flow in raw_flows.items()},
        'reader_diagnostic':reader_error_metadata(error),
        'publication_diagnostics':publication_diagnostics,'pending_publication_diagnostics':pending_publication_diagnostics,
        'final_publication_diagnostics':final_publication_diagnostics,
        'containment_error_type':containment_error,'summary':controller.summary(),
        'independent_observation':controller.data.get('independent_observation'),
        'request':controller.data['requests'].get(request),'stop_wrapper_exits':[p.returncode for p in stops],
        'scope':'No automatic retry; a selected canonical control is not a termination receipt.'})
    raise
finally:
    controller.close()
    for handle in handles:handle.close()
