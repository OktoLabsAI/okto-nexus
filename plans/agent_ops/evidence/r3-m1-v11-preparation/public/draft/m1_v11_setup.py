"""One reviewed local setup; reserve and monitor before its canonical CLI effect."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
sys.path.insert(0,str(Path(__file__).parent))
from campaign_context import load,require,reserve_json
X=load()
P,C,ROOT=X.P,X.C,X.ROOT
from publication import poll_and_publish
require(X.remaining==['local'],'ONLY_LOCAL_STANDALONE_SETUP_SOURCE_IS_QUALIFIED')
profile=P['execution_bundle']['profiles']['local']
review=json.loads((Path(P['paths']['server_home'])/'terminal/profiles'/(profile+'.json')).read_text())
configuration=review['request']['configuration']
require(review['state']=='review' and review['selection']['candidate_ref']==P['native_selection']['candidate_ref'],'SETUP_REVIEW_MISMATCH')
require(Path(configuration['provider_home']).resolve()==Path(P['provider_context']['provider_home']).resolve()
    and Path(configuration['workspace_root']).resolve()==Path(P['paths']['local_project']).resolve(),'SETUP_PATH_MISMATCH')
require(configuration['harness_settings']=={} and configuration['secret_bindings']=={}
    and configuration['tool_access']=='ask' and not review['request']['broadcast_handoff_auto_claim'],'SETUP_POLICY_MISMATCH')
require(configuration['authorization']=={'minutes':60,'no_expiry':False,'actions':20,'unlimited_actions':False},'SETUP_LIMIT_MISMATCH')
request='m1v11-local-setup'
require(request in P['request_ids']['setup'],'SETUP_INTENT_OUTSIDE_PROPOSAL')
require(not (ROOT/'public/local-setup-result.json').exists(),'SETUP_RESULT_ALREADY_EXISTS')
require(not (ROOT/'private/controller.json').exists(),'SETUP_CANNOT_REPLAY_OR_RECREATE_CONTROLLER')
controller=X.controller(create=True)
stops=[];handles=[];diagnostics={};gaps=[]

def public_write(name,value):
    target=ROOT/'public'/name;pending=target.with_suffix('.pending')
    with pending.open('w',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2);stream.flush();os.fsync(stream.fileno())
    os.replace(pending,target)

def stop_owner():
    out=(ROOT/'private/nexus-stop-wrapper.stdout').open('xb')
    err=(ROOT/'private/nexus-stop-wrapper.stderr').open('xb');handles.extend((out,err))
    child=subprocess.Popen(X.stop_argv('nexus'),cwd=ROOT,env=X.env(),stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    stops.append(child);return {'wrapper_pid':child.pid,'action_record':'lifecycle-nexus-stop.json'}

controller.attach_owner('local',P['paths']['server_home'],stop_owner)
argv=C['steps'][0]['argv'][:5]+['connect','--profile',P['execution_bundle']['profiles']['local'],
    '--approve',review['review_revision'],'--no-chat','--timeout','120','--json']+C['service_selection_args']
out=(ROOT/'private/local-setup.stdout').open('xb');err=(ROOT/'private/local-setup.stderr').open('xb');handles.extend((out,err))

def dispatch():
    stored=json.loads(controller.path.read_text())
    require(stored['requests'][request]['kind']=='setup','RESERVATION_MISSING')
    child=subprocess.Popen(argv,cwd=ROOT,env=X.env(),stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    reserve_json(ROOT/'public/local-setup-dispatch.json',{'pid':child.pid,'time':time.time(),
        'review_revision':review['review_revision'],'request_id':request,'reservation_persisted':True})
    return child

started=time.time();previous=None;child=None
try:
    child=controller.setup(request,'local',P['paths']['server_home'],dispatch,stop_owner)
    while True:
        now=time.monotonic()
        if previous is not None:gaps.append(now-previous)
        previous=now
        summary=poll_and_publish(controller,lambda v:public_write('live-accounting.json',v),diagnostics,request)
        if child.poll() is not None:
            record=controller.data['requests'][request]
            if not record['settled'] and not record['stop_selected']:
                controller.fault('SETUP_CLI_RETURNED_WITHOUT_SETTLED_USAGE');controller.poll()
            if all(s.poll() is not None for s in stops):break
        time.sleep(.2)
    for handle in handles:handle.flush()
    raw=(ROOT/'private/local-setup.stdout').read_bytes()
    try:value=json.loads(raw.decode('utf-8'))
    except (UnicodeError,ValueError):value={}
    result={'started':started,'finished':time.time(),'cli_exit':child.returncode,
        'reported_state':value.get('state'),'reported_code':value.get('code'),
        'summary':controller.summary(),'monitor':controller.data['requests'][request]['monitor'],
        'stop_selected':controller.data['requests'][request]['stop_selected'],
        'stop_wrapper_exits':[s.returncode for s in stops],
        'maximum_poll_start_interval_seconds':max(gaps,default=0),'poll_count':len(gaps)+1,
        'publication_diagnostics':diagnostics,'output_sha256':hashlib.sha256(raw).hexdigest()}
    public_write('local-setup-result.json',result);print(json.dumps(result),flush=True)
except BaseException as error:
    controller.fault('SETUP_RUNNER_EXCEPTION')
    try:controller.poll()
    except BaseException:pass
    while any(s.poll() is None for s in stops):
        try:controller.poll()
        except BaseException:pass
        time.sleep(.2)
    public_write('local-setup-runner-error.json',{'error_type':type(error).__name__,
        'summary':controller.summary(),'stop_wrapper_exits':[s.returncode for s in stops],
        'scope':'Control dispatch is not an exit receipt; no replay or force.'})
    raise
finally:
    controller.close()
    for handle in handles:handle.close()
