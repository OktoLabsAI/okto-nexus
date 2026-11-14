"""Finite SVC-T15 terminal-only reference case; inert until reviewed execute."""
from pathlib import Path
import argparse,json,os,secrets,sys,time,zipfile,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parent))
import runtime_support as S
import cohort
import connection_case as C

BASE=Path(__file__).resolve().parent
ROOT=BASE/'case'
PUBLIC=BASE/'public'
PRIVATE=BASE/'private'
PENDING={'STARTUP_PENDING','CONCURRENT_START','SUPERVISOR_PENDING','STARTUP_INCOMPLETE',
    'SERVICE_UNREACHABLE','INSTANCE_OWNERSHIP_UNCONFIRMED','INSTANCE_METADATA_UNAVAILABLE'}

def classify_ready(value,instance_id):
    C.require(isinstance(value,dict),'READY_OBSERVATION_INVALID')
    C.require(value.get('instance_id')==instance_id,'INSTANCE_CHANGED')
    if value.get('state')=='ready':
        C.require(value.get('ready_for_queries') is True and value.get('supervisor')=='windows-task-scheduler'
            and type(value.get('pid')) is int and value['pid']>0 and bool(value.get('generation')),'READY_IDENTITY_UNCONFIRMED')
        return True
    C.require(value.get('state') in ('starting','degraded','unknown') and value.get('reason') in PENDING,
        'POSITIVE_START_REFUSAL')
    return False

def passive_ready(inspect,first,instance_id,*,clock=time.monotonic,sleep=time.sleep,record=None):
    """One passive GET observation window after the single start45 selection."""
    deadline=clock()+180;value=first;selected={};samples=[]
    try:
        while True:
            samples.append({'at_monotonic':clock(),'state':value.get('state'),'reason':value.get('reason'),
                'pid':value.get('pid'),'generation':value.get('generation')})
            ready=classify_ready(value,instance_id)
            for key in ('pid','generation'):
                if value.get(key) is not None:
                    C.require(key not in selected or selected[key]==value[key],'PENDING_OWNER_CHANGED')
                    selected[key]=value[key]
            C.require(clock()<=deadline,'PASSIVE_READY_DEADLINE')
            if ready:return value
            remaining=deadline-clock();C.require(remaining>0,'PASSIVE_READY_DEADLINE')
            sleep(min(.5,remaining))
            remaining=deadline-clock();C.require(remaining>0,'PASSIVE_READY_DEADLINE')
            value=inspect(timeout=min(1,remaining))
    finally:
        if record:record({'observations':samples,'deadline_seconds':180,'post_count':0})

def verify(plan):
    C.require(sys.flags.isolated and Path(sys.executable).resolve()==Path(plan['python']).resolve(),'INSTALLED_PYTHON_REQUIRED')
    C.require(plan['root']==str(BASE) and plan['homes']=={'nexus':str(ROOT/'nexus-home')}
        and plan['port']==59107 and plan['model_turn_limit']==0 and plan['status']=='OFFLINE_QUALIFIED_ROOT_REVIEW_PENDING','PLAN_SCOPE_CHANGED')
    for pin in plan['pins'].values():C.require(C.sha(pin['path'])==pin['sha256'],'SOURCE_PIN_CHANGED')
    for image,digest in plan['python_images'].items():C.require(C.sha(image)==digest,'PYTHON_IMAGE_CHANGED')
    site=BASE/'venv/Lib/site-packages';count=0
    for key,package in [('nexus_wheel','okto_nexus/'),('core_wheel','nexus_connector_core/'),('connector_wheel','okto_nexus_connector/')]:
        with zipfile.ZipFile(plan['pins'][key]['path']) as archive:
            for name in archive.namelist():
                if name.startswith(package) and not name.endswith('/'):
                    C.require(C.sha(site/name)==hashlib.sha256(archive.read(name)).hexdigest(),'INSTALLED_PAYLOAD_CHANGED');count+=1
    return {'wheel_equal_payloads':count,'services_or_provider_started_by_verification':False}

def capture_ready_cohort(plan,service,ready,inspect):
    C.require(classify_ready(ready,plan['instance_ids']['nexus']),'READY_REQUIRED')
    owner=S.Owner(ready,can_terminate=False)
    C.require(Path(owner.image).name.lower()=='pythonw.exe' and owner.image in plan['python_images']
        and C.sha(owner.image)==plan['python_images'][owner.image],'RUNTIME_IMAGE_CHANGED')
    again=inspect(timeout=1)
    C.require(all(again.get(k)==v for k,v in owner.identity.items()),'OWNER_CHANGED_DURING_CAPTURE')
    contract,other,cycle=cohort.capture_cycle(plan,'nexus',service,owner)
    C.require(cycle['attempts_started']==1,'UNEXPECTED_RECOVERY_BEFORE_CREDENTIAL_CASE')
    return owner,contract,{'runtime':owner,**other},cycle

def handoff(plan,service,handles,*,seconds=7200,clock=time.monotonic,sleep=time.sleep):
    if set(handles)=={'runtime','launcher','parent'}:
        cohort.failure_handoff(seconds=seconds)
        return
    # A selected start with no complete retained cohort is not an empty success.
    C.save(PUBLIC/'uncaptured-handoff.json',{'status':'UNKNOWN_UNCAPTURED_SELECTED_START',
        'complete_retained_cohort':False,'physical_exit_proven':False,'cleanup_confirmed':False,
        'task_name':service.name,'observation_limit_seconds':seconds,'automatic_actions':False})
    deadline=clock()+seconds;last={};capture_attempted=False
    while clock()<deadline:
        try:
            current=S.inspect(plan,'nexus');task=service.tasks.read(service.name)
            last={'canonical':S.public_status(current),'native':{'present':task is not None,
                'state':getattr(task,'state',None),'active':getattr(task,'active',None)},
                'physical_exit_proven':False,'cleanup_confirmed':False}
            if not capture_attempted and current.get('state')=='ready':
                capture_attempted=True
                owner,contract,acquired,cycle=capture_ready_cohort(plan,service,current,
                    lambda timeout:S.inspect(plan,'nexus'))
                handles.update(acquired)
                C.save(PUBLIC/'handoff-cohort-acquired.json',{'after_failure':True,'cleanup_confirmed':False,
                    'cycle':cycle,'native':contract,'query_only':True})
                cohort.failure_handoff(seconds=max(0,deadline-clock()))
                return
        except Exception as error:
            last={'observation_error':type(error).__name__,'physical_exit_proven':False,'cleanup_confirmed':False}
        pending=PUBLIC/'uncaptured-handoff-current.pending'
        with pending.open('w',encoding='utf-8') as out:json.dump(last,out,indent=2)
        os.replace(pending,PUBLIC/'uncaptured-handoff-current.json')
        sleep(min(5,max(0,deadline-clock())))
    C.save(PUBLIC/'uncaptured-handoff-final.json',{'status':'UNKNOWN_OBSERVER_EXPIRED',
        'complete_retained_cohort':False,'physical_exit_proven':False,'cleanup_confirmed':False,'last':last})

def wait_all_and_uninstall(plan,service,handles,cli):
    """One canonical stop; no uninstall unless every retained identity exited."""
    C.require(all(p.poll() is not None for p in S.CHILDREN),'CLI_STILL_RUNNING_NO_PARALLEL_CLEANUP')
    code,value=cli('stop')
    C.require(code==0 and value.get('state')=='stopped' and value.get('shutdown_outcome')=='drained','NORMAL_DRAIN_UNCONFIRMED')
    C.require(set(handles)=={'runtime','launcher','parent'},'COMPLETE_COHORT_REQUIRED')
    proof=cohort.wait_exits(handles,'normal-stop')
    cohort.wait_native_inactive(service)
    current=S.inspect(plan,'nexus')
    C.require(current.get('state')=='stopped','CANONICAL_STOP_UNCONFIRMED')
    before=C.retained_data(ROOT/'nexus-home');C.save(PUBLIC/'retained-data-before.json',before)
    code,_=cli('uninstall')
    C.require(code==0 and service.tasks.read(service.name) is None,'TASK_REMOVAL_UNCONFIRMED')
    after=C.retained_data(ROOT/'nexus-home');C.require(before==after,'UNINSTALL_CHANGED_RETAINED_DATA')
    C.save(PUBLIC/'cleanup.json',{'all_cohort_exits':proof,'normal_stop_drained':True,'native_task_absent':True,
        'before':before,'after':after,'data_preserved':True,'force_used':False})
    return True

def execute(plan):
    installed=verify(plan)
    C.require(not PUBLIC.exists() and not PRIVATE.exists() and not ROOT.exists(),'CASE_ALREADY_SELECTED')
    S.secure(ROOT);S.secure(PRIVATE);PUBLIC.mkdir()
    for name in ('nexus-home','profile','profile/.codex','appdata','localappdata','tmp','project'):
        (ROOT/name).mkdir(exist_ok=True)
    (ROOT/'profile/.codex/config.toml').write_text(C.CONFIG,encoding='utf-8')
    env=C.environment(ROOT,plan['python'],plan['pins']['native']['path'],os.environ)
    C.require(not any(k.upper().endswith('API_KEY') for k in env) and C.VARIABLE not in env,'AMBIENT_CREDENTIAL_REFUSED')
    terminal=dict(env);terminal[C.VARIABLE]='svc-t15-synthetic-not-a-login-'+secrets.token_hex(24)
    runtime_plan={**plan,'environments':{'terminal':terminal}}
    os.environ.clear();os.environ.update(env)
    from okto_nexus.adapters.outbound.service_manager.installation import ServerInstallation
    from okto_nexus.adapters.outbound.service_manager.local import LocalServerLifecycle
    service=ServerInstallation(ROOT/'nexus-home',ROOT/'nexus-home/nexus.db')
    inspect=LocalServerLifecycle(home=ROOT/'nexus-home',database=ROOT/'nexus-home/nexus.db',host='127.0.0.1',port=plan['port']).inspect
    C.require(service.name==plan['tasks']['nexus'] and service.instance_id==plan['instance_ids']['nexus'],'OWN_SCOPE_CHANGED')
    C.require(service.tasks.read(service.name) is None,'OWN_TASK_ALREADY_EXISTS');S.port_available(plan)
    def cli(label):return S.cli(runtime_plan,'nexus',label)
    result={'status':'UNCONFIRMED','model_turn_limit':0,'vault_tested':False,'installed':installed,
        'plan_sha256':C.sha(BASE/'plan.json'),'task_name':service.name}
    handles={};start_selected=False;failure=None;cleanup=False
    try:
        code,value=cli('terminal-probe')
        C.require(code==0 and value=={'resolved':True,'reference':C.REFERENCE,'synthetic_not_login':True,
            'vault_calls':0,'unicode_roundtrip':chr(0x2014)},'TERMINAL_AVAILABILITY_UNCONFIRMED')
        result['terminal']=value
        code,_=cli('install');C.require(code==0 and service.receipt() is not None,'INSTALL_UNCONFIRMED')
        context=json.loads((ROOT/'nexus-home/service-context.json').read_bytes())
        C.require(C.VARIABLE.casefold() not in {k.casefold() for k in context['environment']},'SENTINEL_CAPTURED_BY_SERVICE')
        result['context_excludes_terminal_reference']=True
        start_selected=True
        code,value=cli('start');C.require(code in (0,3),'START_RETURN_UNCONFIRMED')
        ready=passive_ready(inspect,value,service.instance_id,
            record=lambda document:C.save(PUBLIC/'passive-ready.json',document))
        owner,contract,handles,cycle=capture_ready_cohort(plan,service,ready,inspect)
        C.save(PUBLIC/'ready-cohort.json',{'runtime':owner.identity|{'birth_filetime':owner.birth},
            'cycle':cycle,'native':contract,'query_only':True})
        selected=C.observe_candidate(plan)
        def plan_cli(label,args):
            C.require(label=='plan' and args==plan['connection_plan_arguments'],'CLI_PLAN_ARGUMENTS_CHANGED')
            return cli('plan')
        result['service_test']=C.setup_case(selected,plan_cli,owner,inspect)
        current=inspect(timeout=1)
        C.require(classify_ready(current,service.instance_id) and all(current.get(k)==v for k,v in owner.identity.items())
            and not owner.exited(),'OWNER_CHANGED_AFTER_DIAGNOSIS')
        cohort.validate_cycle(cohort.cycle_projection(plan,'nexus',service),owner,contract,1)
        result['owner_ready_after_diagnosis']=True
    except Exception as error:
        failure=str(error) if isinstance(error,(C.Refused,ValueError)) else type(error).__name__
        from okto_nexus.application.terminal_connection import ConnectionError
        if isinstance(error,ConnectionError):
            import re
            def safe(value):return value if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}',value) else 'UNCONFIRMED'
            result['failure_detail']={'code':safe(error.code),'stage':safe(error.stage),
                'possible_effect':error.possible_effect if type(error.possible_effect) is bool else None}
    finally:
        if start_selected:
            try:cleanup=wait_all_and_uninstall(plan,service,handles,cli)
            except Exception as error:
                result['cleanup_uncertainty']=str(error) if isinstance(error,(C.Refused,ValueError)) else type(error).__name__
        else:result['cleanup_uncertainty']='NO_START_SELECTED_REVIEW_INSTALLATION_IF_PRESENT'
    result['failure']=failure
    result['cleanup_confirmed']=cleanup
    result['all_cli_children_exited']=all(p.poll() is not None for p in S.CHILDREN)
    if failure is None and cleanup and result['all_cli_children_exited']:
        try:
            result['journal']=C.journal_proof(ROOT/'nexus-home')
            result['status']='SVC_T15_TERMINAL_ONLY_REFERENCE_DIAGNOSED_IN_REAL_SERVICE'
        except Exception as error:result['failure']=str(error) if isinstance(error,C.Refused) else type(error).__name__
    C.save(PUBLIC/'result.json',result)
    if result['status']=='UNCONFIRMED':
        if start_selected:handoff(plan,service,handles)
        else:cohort.failure_handoff()
    for handle in S.HANDLES:handle.close()
    print(json.dumps(result),flush=True)
    return 0 if result['status'].startswith('SVC_T15_') else 3

def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('execute','probe'))
    parser.add_argument('--expected-plan-sha256');args=parser.parse_args()
    if args.mode=='probe':C.probe();return 0
    C.require(args.expected_plan_sha256 is not None and C.sha(BASE/'plan.json')==args.expected_plan_sha256,'PLAN_HASH_CHANGED')
    return execute(json.loads((BASE/'plan.json').read_bytes()))

if __name__=='__main__':raise SystemExit(main())
