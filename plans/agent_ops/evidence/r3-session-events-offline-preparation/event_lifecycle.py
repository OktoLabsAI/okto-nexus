"""Finite future canonical lifecycle; no OS event, force, provider or third task."""
from pathlib import Path
import json,socket,subprocess,time
import event_native as native
from event_observer import save,read,digest,stamp,ready,NAMES,EVENTS
require=native.require

def free_port(port):
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1);s.bind(('127.0.0.1',port))

def prepare(P):
    root=Path(P['root']);require(not (root/'lifecycle').exists(),'PREPARATION_ALREADY_SELECTED')
    for name in NAMES:
        require(not Path(P['homes'][name]).exists(),'OWN_HOME_ALREADY_PRESENT')
        service=native.installation(P,name);require(service.tasks.read(service.name) is None,'OWN_TASK_ALREADY_PRESENT')
    free_port(P['port'])
    for path in ('lifecycle','evidence','profile','profile/appdata','profile/localappdata','profile/tmp',
        'profile/.codex','profile/.claude','project','caller','nexus','connector'):
        native.secure_directory(root/path,root)
    for event in EVENTS:native.secure_directory(root/'evidence'/event,root)
    result={'status':'PREPARED','plan_sha256':digest(root/'plan.json'),'utc':stamp(),
        'task_absence_confirmed_before_creation':True,'port_free_before_creation':True,'provider_calls':0}
    save(root/'lifecycle'/'prepared.json',result);return result

def invoke(P,name,action,*,popen=subprocess.Popen):
    require(name in NAMES and action in ('install','initial_start','cleanup_stop','cleanup_uninstall'),'ACTION_INVALID')
    directory=Path(P['root'])/'lifecycle';spec=P['commands'][name][action];prefix=name+'-'+action
    require((directory/'prepared.json').exists(),'PREPARE_REQUIRED')
    require('--force' not in spec['argv'] and Path(spec['argv'][0])==Path(P['python']),'COMMAND_BOUNDARY')
    reservation={'component':name,'action':action,'argv_sha256':__import__('hashlib').sha256(json.dumps(spec['argv']).encode()).hexdigest(),
        'plan_sha256':digest(Path(P['root'])/'plan.json'),'reserved_utc':stamp(),'provider_calls':0}
    save(directory/(prefix+'.reserved.json'),reservation)
    with (directory/(prefix+'.stdout')).open('xb') as out,(directory/(prefix+'.stderr')).open('xb') as err:
        process=popen(spec['argv'],env=P['environments'][spec['environment']],cwd=spec['cwd'],stdin=subprocess.DEVNULL,stdout=out,stderr=err)
        # CLI's selected 45s lifecycle bound is unchanged. This launcher never kills it.
        try:code=process.wait(timeout=180)
        except subprocess.TimeoutExpired:
            save(directory/(prefix+'.wait-expired.json'),{'status':'CLI_EXIT_UNCONFIRMED','pid':process.pid,'no_force':True,'utc':stamp()})
            code=process.wait() # retain own CLI rather than abandon an ambiguous effect
    result={'component':name,'action':action,'exit_code':code,'utc':stamp(),'reservation_sha256':digest(directory/(prefix+'.reserved.json')),
        'stdout_sha256':digest(directory/(prefix+'.stdout')),'stderr_sha256':digest(directory/(prefix+'.stderr')),'force':False}
    save(directory/(prefix+'.returned.json'),result);return result

def prior_success(P,name,action):
    path=Path(P['root'])/'lifecycle'/(name+'-'+action+'.returned.json')
    require(path.exists() and read(path).get('exit_code')==0,'PRIOR_COMMAND_NOT_SUCCESSFUL')

def initial(P,name,action):
    service=native.installation(P,name)
    if action=='install':require(service.tasks.read(service.name) is None,'OWN_TASK_ALREADY_PRESENT')
    elif action=='initial_start':
        prior_success(P,name,'install');_,task=service.observe();require(task is not None and not task.active,'INITIAL_TASK_NOT_IDLE')
    else:raise RuntimeError('INITIAL_ACTION_INVALID')
    return invoke(P,name,action)

def observe_ready(P,*,clock=time.monotonic,sleep=time.sleep):
    deadline=clock()+180;samples=[]
    while True:
        value,handles=native.snapshot(P)
        for h in handles.values():h.close()
        samples.append(value)
        if all(ready(value['components'][n]) for n in NAMES) or clock()>=deadline:break
        sleep(min(2,max(0,deadline-clock())))
    result={'status':'READY' if all(ready(samples[-1]['components'][n]) for n in NAMES) else 'READINESS_UNCONFIRMED',
        'samples':samples,'automatic_start_selected':False,'provider_calls':0}
    save(Path(P['root'])/'lifecycle'/'initial-readiness.json',result);return result

def current_stop(P,name,*,clock=time.monotonic,sleep=time.sleep):
    component,handles=native.collect_component(P,name,retain=True)
    require(component.get('cohort_confirmed') is True and set(handles)==set(native.ROLES),'CURRENT_COHORT_REQUIRED')
    directory=Path(P['root'])/'lifecycle'
    try:
        save(directory/(name+'-cleanup-cohort.json'),component)
        result=invoke(P,name,'cleanup_stop');deadline=clock()+120
        while not all(h.exited() for h in handles.values()) and clock()<deadline:sleep(min(1,max(0,deadline-clock())))
        processes={role:{'identity':component['cohort'][role],'physical_exit_confirmed':h.exited(),
            'exit_code':h.exit_code() if h.exited() else None} for role,h in handles.items()}
        service=native.installation(P,name);task=service.tasks.read(service.name)
        same_task=task is not None and task.digest==component['task']['digest']
        native_deadline=clock()+30
        while same_task and task.active and clock()<native_deadline:
            sleep(min(1,max(0,native_deadline-clock())))
            task=service.tasks.read(service.name)
            same_task=task is not None and task.digest==component['task']['digest']
        inactive=same_task and not task.active
        receipts=native.receipt_projection(P,name)
        # Receipt facts are independent of retained process exit, not a work settlement claim.
        from event_observer import old_shutdown
        shutdown=old_shutdown(component,{'receipts':receipts})
        proof={'component':name,'cohort':component['cohort'],'generation':component['canonical']['generation'],
            'task_digest':component['task']['digest'],'processes':processes,
            'all_physical_exit_confirmed':all(v['physical_exit_confirmed'] for v in processes.values()),
            'native_inactive_same_definition':inactive,'normal_cli_exit_code':result['exit_code'],
            'canonical_shutdown_receipt':shutdown,'work_settlement':'NOT_ASSERTED','force':False}
        save(directory/(name+'-cleanup-proof.json'),proof);return proof
    finally:
        for h in handles.values():h.close()

def data_fingerprints(P,name):
    root=Path(P['homes'][name]);paths=[root/'nexus.db',root/'nexus.db-wal',root/'nexus.db-shm'] if name=='nexus' else [root/'state.json']
    return {str(p):{'present':p.exists(),'sha256':digest(p) if p.exists() else None} for p in paths}

def uninstall(P,name):
    directory=Path(P['root'])/'lifecycle';proof=read(directory/(name+'-cleanup-proof.json'))
    require(proof.get('component')==name and proof.get('all_physical_exit_confirmed') is True
        and proof.get('native_inactive_same_definition') is True and proof.get('force') is False,'PHYSICAL_CLEANUP_NOT_PROVED')
    require(set(proof.get('processes',{}))==set(native.ROLES) and all(v.get('physical_exit_confirmed') is True for v in proof['processes'].values()),'INCOMPLETE_PHYSICAL_PROOF')
    service=native.installation(P,name);_,task=service.observe()
    require(task is not None and not task.active and task.digest==proof['task_digest'],'TASK_CHANGED_OR_ACTIVE')
    current=native.read_cycle(P,name,service)
    identity_fields=('cycle_id','attempts_started','child_acknowledged',*native.ROLES)
    require(all(current.get(k)==proof['cohort'].get(k) for k in identity_fields),'CYCLE_CHANGED_AFTER_CLEANUP')
    before=data_fingerprints(P,name);result=invoke(P,name,'cleanup_uninstall')
    absent=service.tasks.read(service.name) is None;after=data_fingerprints(P,name)
    summary={'component':name,'exit_code':result['exit_code'],'task_absent':absent,'data_before':before,'data_after':after,
        'data_equal':before==after,'homes_retained':Path(P['homes'][name]).is_dir(),'work_settlement':'NOT_ASSERTED'}
    save(directory/(name+'-data-preservation.json'),summary);return summary
