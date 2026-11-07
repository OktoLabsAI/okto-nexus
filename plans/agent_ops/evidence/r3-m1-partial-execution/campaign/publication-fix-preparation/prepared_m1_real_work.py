"""One finite v7 work admission using reviewed installed client and controller.

Requires a separately recorded client pin. No setup, login or automatic approval.
The same process continues budget polling while a concrete native request awaits
an exact reviewed decision file. No original profile or product bytes are edited.
"""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
from urllib.parse import quote
sys.path.insert(0,str(Path(__file__).parent))
from publication import poll_and_publish
sys.path.insert(0,'C:/Users/jpamb/AppData/Local/Temp')
from m1_real_lifecycle import P,C,ROOT,env,REPO
PREP=REPO/'plans/agent_ops/evidence/r3-m1-controller/preparation'
sys.path.insert(0,str(PREP))
from controller import Controller
from response_loss import CampaignState,FiniteResponseLoss
from okto_nexus.application.terminal_connection import ConnectionError,document_revision
from okto_nexus.adapters.inbound.cli.work import open_work
from okto_nexus.adapters.inbound.cli.terminal_target import resolve_terminal_target
from okto_nexus.adapters.inbound.cli.service import resolve_local_service
from okto_nexus.adapters.outbound.service_manager.locking import ExclusiveFileLock
import okto_nexus

assert len(sys.argv)==3 and sys.argv[1] in ('local','connector') and sys.argv[2] in ('useful','continuation')
LANE,PHASE=sys.argv[1:]
pin=json.loads((ROOT/'public/client-runtime-pin.json').read_text())
assert pin['qualification_status']=='QUALIFIED' and pin['root_execution_release'] is True
assert Path(sys.prefix).resolve()==Path(pin['python_prefix']).resolve()
assert Path(okto_nexus.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
source=Path(okto_nexus.__file__).parent/'application/terminal_connection.py'
assert hashlib.sha256(source.read_bytes()).hexdigest()==pin['terminal_connection_sha256']
profile='m1-local' if LANE=='local' else 'm1-remote'
request=profile+'-work-'+('01' if PHASE=='useful' else '02')
assert not (ROOT/'public'/(request+'-result.json')).exists()
controller=Controller(ROOT/'private/controller.json',ROOT)
driverpath=ROOT/'private/response-loss.json'
faults=CampaignState(driverpath,**({'campaign_id':'m1-v7'} if not driverpath.exists() else {}))
flows={}; observed={}; guards=[]; stops=[]; handles=[]; selected_decisions=set()
recovered_decisions={}
publication_diagnostics={}
call_counts={'GET':0,'POST':0,'productive_posts':0,'decision_posts':0}

def stop_owner(lane):
    component='nexus' if lane=='local' else 'connector'
    out=(ROOT/'private'/(component+'-stop-wrapper.stdout')).open('xb')
    err=(ROOT/'private'/(component+'-stop-wrapper.stderr')).open('xb')
    handles.extend((out,err))
    child=subprocess.Popen([C['steps'][0]['argv'][0],'-I',str(Path('C:/Users/jpamb/AppData/Local/Temp/m1_real_lifecycle.py')),component,'stop'],
        cwd=ROOT,env=env(),stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    stops.append(child)
    return {'pid':child.pid}

def attach(lane):
    name='m1-local' if lane=='local' else 'm1-remote'
    args=C['service_selection_args'] if lane=='local' else ['--home',P['paths']['operator_home']]
    service=resolve_terminal_target(args,name,None if lane=='local' else 'm1-human',resolve_local_service)
    guard=ExclusiveFileLock(service.adapter.home/'terminal/profiles'/(name+'.guard'))
    guard.acquire(); guards.append(guard)
    flow=open_work(service,name)
    transport=flow.call
    # Bound individual requests; any unknown observation closes admissions.
    transport.timeout=.5
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
        value=original(**kwargs); observed[lane]=value; return value
    flow.observe=observe
    flows[lane]=flow
    controller.attach(lane,flow)
    owner=P['paths']['server_home'] if lane=='local' else P['paths']['connector_state']
    controller.attach_owner(lane,owner,lambda:stop_owner(lane))
    return flow

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
    public_write('pending-native-request.json',{'request_id':request,'approval_id':approval,'review_revision':revision,
        'approval_key':key,'display':proposal['display'],'policy':'No decision until the actual command is reviewed against the exact source/output and v7 constraints.'})
    decision_path=ROOT/'private'/(approval+'-reviewed-decision.json')
    if not decision_path.exists() or approval in selected_decisions:return
    current=controller.data['requests'][request]
    if (current['stop_selected'] or controller.data['faults'] or
            controller.summary()['known_observed_tokens']>=100000):return
    if selected_decisions or any(d['lane']==LANE for d in faults.data['decisions']):return
    # v7 permits only one native decision per lane, across process restarts too.
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

started=time.time();intervals=[];previous=None;submission_error=None
try:
    active_lanes={r['lane'] for r in controller.data['requests'].values() if r['kind']=='work'}|{LANE}
    # Retain the setup home callback even when observing remote work.
    controller.attach_owner('local',P['paths']['server_home'],lambda:stop_owner('local'))
    for lane in sorted(active_lanes):attach(lane)
    flow=flows[LANE]
    if LANE=='connector' and PHASE=='useful':faults.arm('admission',LANE,request)
    text=P['finite_work']['request'] if PHASE=='useful' else P['finite_work']['continuation']
    project=P['paths']['local_project' if LANE=='local' else 'remote_project']
    deliverables=P['paths']['local_deliverables' if LANE=='local' else 'remote_deliverables']
    text=text.replace('<project>',project).replace('<lane_deliverables>',deliverables)
    if PHASE=='useful':assert not (Path(deliverables)/'report.json').exists()
    public_write(request+'-dispatch-selection.json',{'request_id':request,'lane':LANE,'phase':PHASE,'time':started,'prompt_sha256':hashlib.sha256(text.encode()).hexdigest(),'client_pin':pin})
    try:controller.work(request,LANE,text,stage='useful_work' if PHASE=='useful' else 'continuation')
    except ConnectionError as error:
        submission_error={'code':error.code,'stage':error.stage,'possible_effect':error.possible_effect}
        if request not in controller.data['requests']:raise
    while True:
        now=time.monotonic()
        if previous is not None:intervals.append(now-previous)
        previous=now
        summary=poll_and_publish(controller,lambda value:public_write('live-accounting.json',value),publication_diagnostics,request)
        current=controller.data['requests'][request]
        value=observed.get(LANE,{})
        for detail in value.get('requests',{}).get('items',[]):publish_approval(flow,detail)
        recover_decisions(flow)
        if current['settled']:break
        if current['stop_selected'] and all(p.poll() is not None for p in stops):
            # Attempted stop is reported as such; no termination/usage guarantee.
            break
        time.sleep(.2)
    report=Path(deliverables)/'report.json'
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
    if operation_id:
        receipt=flow.operation(operation_id,flow.binding())
        receipt_metadata={k:receipt.get(k) for k in ('operation_id','executor_stage','admission_state','action','possible_effect')}
        output_text=(receipt.get('result') or {}).get('output_text')
        if isinstance(output_text,str):
            import re
            receipt_metadata['output_sha256']=hashlib.sha256(output_text.encode()).hexdigest()
            receipt_metadata['output_characters']=len(output_text)
            receipt_metadata['standalone_10_mentions']=len(re.findall(r'(?<!\d)10(?!\d)',output_text))
    result={'request_id':request,'started':started,'finished':time.time(),'summary':controller.summary(),
            'record':controller.data['requests'][request],'report':output,'submission_error':submission_error,
            'maximum_poll_start_interval_seconds':max(intervals,default=0),'calls':call_counts,
            'publication_diagnostics':publication_diagnostics,'decision_count':len(selected_decisions),'recovered_decisions':recovered_decisions,'response_loss':faults.snapshot(),'canonical_receipt':receipt_metadata,
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
    public_write(request+'-runner-error.json',{'error_type':type(error).__name__,
        'publication_diagnostics':publication_diagnostics,'containment_error_type':containment_error,'summary':controller.summary(),
        'request':controller.data['requests'].get(request),'stop_wrapper_exits':[p.returncode for p in stops],
        'scope':'No automatic retry; a selected canonical control is not a termination receipt.'})
    raise
finally:
    controller.close()
    for guard in reversed(guards):guard.release()
    for handle in handles:handle.close()
