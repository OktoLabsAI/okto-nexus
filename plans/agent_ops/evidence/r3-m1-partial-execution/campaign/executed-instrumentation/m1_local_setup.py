"""One approved local setup, with the unchanged finite controller armed first."""
from pathlib import Path
import hashlib,json,subprocess,sys,time
sys.path.insert(0,'C:/Users/jpamb/AppData/Local/Temp')
from m1_real_lifecycle import P,C,ROOT,env,REPO
PREP=REPO/'plans/agent_ops/evidence/r3-m1-controller/preparation'
sys.path.insert(0,str(PREP))
from controller import Controller
assert hashlib.sha256((PREP/'controller.py').read_bytes()).hexdigest()=='1423494d75217983477dd464ffbc46bd3bc9fbde4664217fa5fa73376b35d90e'
assert hashlib.sha256((PREP/'setup_journal.py').read_bytes()).hexdigest()=='3598363815a340d8324b7743fff42738e1bf7e936b87e4d6b1856ecaf6a927e5'
review=json.loads((ROOT/'public'/'local-plan.json').read_text())['review']
config=review['request']['configuration']
assert review['state']=='review' and review['selection']['candidate_ref']==P['native_selection']['candidate_ref']
assert config['provider_home']==P['provider_context']['provider_home'] and config['workspace_root']==P['paths']['local_project']
assert config['harness_settings']=={} and config['secret_bindings']=={} and config['tool_access']=='ask'
assert not review['request']['broadcast_handoff_auto_claim']
assert config['authorization']=={'minutes':60,'no_expiry':False,'actions':20,'unlimited_actions':False}
assert not (ROOT/'public'/'local-setup-result.json').exists()
controller=Controller(ROOT/'private'/'controller.json',ROOT,create=True)
stops=[]
streams=[]
def stop_owner():
    # Spawn only the exact recorded canonical stop; polling never waits 45s here.
    stdout=(ROOT/'private'/'nexus-stop-wrapper.stdout').open('xb')
    stderr=(ROOT/'private'/'nexus-stop-wrapper.stderr').open('xb')
    streams.extend([stdout,stderr])
    child=subprocess.Popen([C['steps'][0]['argv'][0],'-I',str(Path(__file__).with_name('m1_real_lifecycle.py')),'nexus','stop'],
        cwd=ROOT,env=env(),stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
    stops.append(child)
    return {'stop_wrapper_pid':child.pid}
controller.attach_owner('local',P['paths']['server_home'],stop_owner)
argv=C['steps'][0]['argv'][:5]+['connect','--profile','m1-local','--approve',review['review_revision'],'--no-chat','--timeout','120','--json']+C['service_selection_args']
stdout=(ROOT/'private'/'local-setup.stdout').open('xb'); stderr=(ROOT/'private'/'local-setup.stderr').open('xb')
streams.extend([stdout,stderr])
def dispatch():
    stored=json.loads(controller.path.read_text())
    assert stored['requests']['m1-local-setup']['kind']=='setup'
    child=subprocess.Popen(argv,cwd=ROOT,env=env(),stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
    (ROOT/'public'/'local-setup-dispatch.json').write_text(json.dumps({'pid':child.pid,'time':time.time(),'review_revision':review['review_revision'],'request_id':'m1-local-setup','reservation_persisted':True},indent=2))
    return child
started=time.time(); gaps=[]; prior=None; previous_summary=None
try:
    child=controller.setup('m1-local-setup','local',P['paths']['server_home'],dispatch,stop_owner)
    while True:
        now=time.monotonic()
        if prior is not None:gaps.append(now-prior)
        prior=now
        summary=controller.poll()
        if summary!=previous_summary:
            (ROOT/'public'/'live-accounting.json').write_text(json.dumps({'time':time.time(),'summary':summary},indent=2))
            print(json.dumps({'accounting':summary}),flush=True)
            previous_summary=summary
        exited=child.poll() is not None
        if exited:
            record=controller.data['requests']['m1-local-setup']
            if not record['settled'] and not record['stop_selected']:
                controller.fault('SETUP_CLI_RETURNED_WITHOUT_SETTLED_USAGE')
                controller.poll()
            if all(s.poll() is not None for s in stops):break
        time.sleep(.2)
    for f in streams:f.flush()
    raw=(ROOT/'private'/'local-setup.stdout').read_bytes()
    try:out=json.loads(raw.decode('utf-8'))
    except UnicodeDecodeError:out=json.loads(raw.decode('cp1252'))
    except ValueError:out={}
    result={'started':started,'finished':time.time(),'cli_exit':child.returncode,'reported_state':out.get('state'),
            'reported_code':out.get('code'),'summary':controller.summary(),
            'monitor':controller.data['requests']['m1-local-setup']['monitor'],
            'stop_selected':controller.data['requests']['m1-local-setup']['stop_selected'],
            'stop_wrapper_exits':[s.returncode for s in stops],
            'maximum_poll_start_interval_seconds':max(gaps,default=0),'poll_count':len(gaps)+1,
            'output_sha256':hashlib.sha256(raw).hexdigest(),'native_effective_policy':'not yet established by canonical setup review; inherited settings preserved'}
    (ROOT/'public'/'local-setup-result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)
finally:
    controller.close()
    for f in streams:f.close()
