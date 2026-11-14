"""Retained query-only lifecycle cohort, extracted from qualified T19 helpers."""
from pathlib import Path
import time,xml.etree.ElementTree as ET
import runtime_support as support
from runtime_support import PUBLIC,require,sha,save
def native_stamp(service):
    """Read one exact task only; no registration or global task enumeration."""
    import win32com.client
    scheduler=win32com.client.Dispatch('Schedule.Service');scheduler.Connect()
    task=scheduler.GetFolder('\\').GetTask(service.name)
    return str(task.LastRunTime)


def native_contract(service):
    receipt,task=service.observe()
    require(receipt and task and task.active and task.enabled,'TASK_NOT_ACTIVE')
    ns={'t':'http://schemas.microsoft.com/windows/2004/02/mit/task'}
    tree=ET.fromstring(task.xml)
    require(tree.find('t:Settings/t:RestartOnFailure',ns) is None
        and tree.findtext('t:Settings/t:MultipleInstancesPolicy',namespaces=ns)=='IgnoreNew','RETRY_CONTRACT_CHANGED')
    from nexus_connector_core.user_service_supervision import RestartPolicy
    policy=RestartPolicy()
    require(policy.backoff_seconds==60 and policy.max_restarts==3,'PARENT_RETRY_POLICY_CHANGED')
    return {'name':service.name,'digest':task.digest,'interval_seconds':60,'count':3,
        'native_restart_on_failure':False,'last_run_time':native_stamp(service)}


def cycle_projection(plan,name,service):
    """Allowlisted lifecycle identities only; never publish token/nonce/context."""
    home=Path(plan['homes'][name]);receipt=service.receipt()
    if name=='nexus':
        from okto_nexus.adapters.outbound.service_manager.supervision import read_record
        value=read_record(home,receipt,plan['instance_ids'][name])
    else:
        from okto_nexus_connector.platform.service_supervision import read_cycle
        value=read_cycle(home,receipt)
    require(isinstance(value,dict),'SUPERVISOR_RECORD_MISSING')
    result={key:value.get(key) for key in ('cycle_id','phase','attempts_started','last_exit_code','child_acknowledged')}
    for role in ('parent','launcher','child'):
        identity=value.get(role)
        require(isinstance(identity,dict),'SUPERVISOR_IDENTITY_MISSING')
        birth=identity.get('birth') if name=='nexus' else int(identity['birth_token'].removeprefix('filetime:'))
        result[role]={'pid':identity['pid'],'birth':birth}
    result['child_exit_confirmed']=(value['child'].get('physical_exit') is True if name=='nexus' else value.get('child_exit_confirmed') is True)
    result['launcher_exit_confirmed']=(value['launcher'].get('physical_exit') is True if name=='nexus' else value.get('launcher_exit_confirmed') is True)
    return result


def validate_cycle(value,owner,contract,attempt):
    require(value['cycle_id']==contract['cycle_id'] and value['parent']==contract['parent']
        and value['attempts_started']==attempt and value['phase']=='running'
        and value['child_acknowledged'] is True,'SUPERVISOR_CYCLE_CHANGED')
    require(value['child']=={'pid':owner.identity['pid'],'birth':owner.birth}
        and not value['child_exit_confirmed'] and not value['launcher_exit_confirmed'],'RUNTIME_HANDSHAKE_CHANGED')


def capture_cycle(plan,name,service,owner,contract=None):
    value=cycle_projection(plan,name,service)
    require(value['phase']=='running' and value['child_acknowledged'] is True,'HANDSHAKE_NOT_ACKNOWLEDGED')
    selected={**(contract or native_contract(service)), 'cycle_id':value['cycle_id'],'parent':value['parent']}
    validate_cycle(value,owner,selected,value['attempts_started'])
    handles={}
    for role in ('parent','launcher'):
        identity=value[role]
        handle=support.Owner({'pid':identity['pid'],'generation':value['cycle_id'],
            'instance_id':plan['instance_ids'][name]},can_terminate=False)
        require(handle.birth==identity['birth'] and handle.image in plan['python_images']
            and sha(handle.image)==plan['python_images'][handle.image],'SUPERVISOR_PROCESS_CHANGED')
        handles[role]=handle
    require(cycle_projection(plan,name,service)==value,'SUPERVISOR_CHANGED_DURING_CAPTURE')
    return selected,handles,value


def wait_exits(handles,label):
    end=time.monotonic()+30
    while not all(h.exited() for h in handles.values()) and time.monotonic()<end:time.sleep(.1)
    require(all(h.exited() for h in handles.values()),'SUPERVISOR_PHYSICAL_EXIT_UNCONFIRMED')
    proof={role:{'pid':h.identity['pid'],'birth_filetime':h.birth,'exit_code':h.exit_code(),
        'physical_exit_confirmed':True,'terminate_right':h.can_terminate} for role,h in handles.items()}
    save(PUBLIC/(label+'-process-exits.json'),proof)
    return proof


def wait_native_inactive(service):
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        task=service.tasks.read(service.name)
        if task and task.state==3 and not task.active:return task
        time.sleep(.1)
    raise ValueError('NATIVE_EXIT_UNCONFIRMED')


def failure_handoff(seconds=7200):
    """No cleanup actions: preserve owned handles while root selects normal cleanup."""
    def current():
        owners=[];wrappers=[]
        for h in support.HANDLES:
            try:exited=h.exited()
            except (OSError,ValueError):exited=None
            owners.append({'pid':h.identity['pid'],'birth_filetime':getattr(h,'birth',None),
                'generation':h.identity['generation'],'instance_id':h.identity['instance_id'],
                'physical_exit_confirmed':exited,'terminate_right':h.can_terminate})
        for p in support.CHILDREN:
            try:code=p.poll()
            except (OSError,ValueError):code=None
            wrappers.append({'pid':p.pid,'exit_code':code,'retained_popen_handle':True})
        return {'owned_processes':owners,'cli_wrappers':wrappers}
    def done(value):
        return all(p['physical_exit_confirmed'] is True for p in value['owned_processes']) and all(p['exit_code'] is not None for p in value['cli_wrappers'])
    first=current()
    save(PUBLIC/'failure-handoff.json',{'status':'OBSERVING_RETAINED_HANDLES','observation_limit_seconds':seconds,
        'automatic_cleanup':False,'kill_used':False,'work_settlement':'not_asserted',**first})
    end=time.monotonic()+seconds;last=first
    while not done(last) and time.monotonic()<end:
        time.sleep(min(1,max(0,end-time.monotonic())))
        last=current()
    save(PUBLIC/'failure-handoff-final.json',{'status':'CAPTURED_PROCESSES_EXITED' if done(last) else 'UNKNOWN_OBSERVER_EXPIRED',
        'campaign_pass':False,'cleanup_confirmed':False,'work_settlement':'not_asserted',**last})
