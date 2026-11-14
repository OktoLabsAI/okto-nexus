"""Finite disposable READY-owner crash campaign. Import performs no OS actions."""
from pathlib import Path
import argparse
import ctypes
from ctypes import wintypes
import json
import os
import sys
import time
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parent))
import runtime_support as support
from runtime_support import ROOT,PUBLIC,PRIVATE,require,sha,read,save,cli,inspect,own_ready,stop_owner

def package_proof(plan):
    require(sys.flags.isolated and Path(sys.executable).resolve()==Path(plan['python']).resolve(),'PYTHON_SCOPE_CHANGED')
    for entry in plan['pins']:
        require(sha(entry['path'])==entry['sha256'],'FROZEN_PAYLOAD_CHANGED')
    require(plan['status']=='FROZEN_QUALIFIED_OFFLINE' and plan['root']==str(ROOT),'PLAN_NOT_FROZEN')

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
    require(tree.findtext('t:Settings/t:RestartOnFailure/t:Interval',namespaces=ns)=='PT1M'
        and tree.findtext('t:Settings/t:RestartOnFailure/t:Count',namespaces=ns)=='3'
        and tree.findtext('t:Settings/t:MultipleInstancesPolicy',namespaces=ns)=='IgnoreNew','RETRY_CONTRACT_CHANGED')
    return {'name':service.name,'digest':task.digest,'interval_seconds':60,'count':3,'last_run_time':native_stamp(service)}

def validate_crash_selection(plan,name,owner,current,task,contract):
    require(name in ('nexus','connector') and current.get('state')=='ready'
        and current.get('supervisor')=='windows-task-scheduler'
        and all(current.get(k)==v for k,v in owner.identity.items()),'READY_OWNER_CHANGED')
    require(owner.identity['instance_id']==plan['instance_ids'][name]
        and contract['name']==plan['tasks'][name] and task.active and task.digest==contract['digest'],'TASK_OWNER_SCOPE_CHANGED')
    require(owner.image in plan['python_images'] and sha(owner.image)==plan['python_images'][owner.image]
        and Path(owner.image).name.lower()=='pythonw.exe' and type(owner.birth) is int and owner.birth>0
        and not owner.exited(),'PROCESS_IDENTITY_CHANGED')

def crash_once(plan,name,owner,service,contract,round_number):
    require(type(round_number) is int and 0<=round_number<4,'CRASH_LIMIT')
    # Selection and the irreversible OS effect use the same retained handle.
    # No PID lookup/termination fallback exists.
    _,task=service.observe()
    validate_crash_selection(plan,name,owner,inspect(plan,name),task,contract)
    path=PRIVATE/(name+'-crash-'+str(round_number)+'.reserved.json')
    save(path,{**owner.identity,'birth_filetime':owner.birth,'image':owner.image,
        'image_sha256':sha(owner.image),'native_digest':contract['digest'],'exit_code':3,
        'effect':'TerminateProcess on retained exclusive disposable READY owner handle','at':time.time()})
    _,task=service.observe()
    validate_crash_selection(plan,name,owner,inspect(plan,name),task,contract)
    owner.kernel.TerminateProcess.argtypes=(wintypes.HANDLE,wintypes.UINT)
    owner.kernel.TerminateProcess.restype=wintypes.BOOL
    at=time.time()
    require(owner.kernel.TerminateProcess(owner.handle,3),'FAULT_INJECTION_UNCONFIRMED')
    end=time.monotonic()+30
    while not owner.exited() and time.monotonic()<end:time.sleep(.1)
    require(owner.exited(),'CRASH_PHYSICAL_EXIT_UNCONFIRMED')
    save(PUBLIC/(name+'-crash-'+str(round_number)+'.json'),{**owner.identity,
        'birth_filetime':owner.birth,'image_sha256':sha(owner.image),'exit_confirmed':True,
        'retained_handle':True,'injected_exit_code':3,'injected_at':at,'canonical_force_stop_used':False})
    return at

def quiet(plan,name,service,seconds,label,expected_reason):
    stamp=native_stamp(service);start=time.monotonic();samples=0;last=None
    while True:
        last=inspect(plan,name);task=service.tasks.read(service.name)
        require(task and not task.active and task.state==3,'UNEXPECTED_NATIVE_ATTEMPT')
        require(native_stamp(service)==stamp,'UNEXPECTED_NATIVE_LAUNCH')
        require(last.get('pid') is None and last.get('state') in ('stopped','unknown')
            and last.get('reason')==expected_reason,'UNEXPECTED_OWNER_OR_DIAGNOSTIC')
        samples+=1
        if time.monotonic()-start>=seconds:break
        time.sleep(max(0,min(1,seconds-(time.monotonic()-start))))
    proof={'seconds':time.monotonic()-start,'samples':samples,'last_run_time_unchanged':stamp,
        'canonical':support.public_status(last),'automatic_launches_observed':0}
    save(PUBLIC/(name+'-'+label+'.json'),proof)
    return proof

def wait_native_inactive(service):
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        task=service.tasks.read(service.name)
        if task and task.state==3 and not task.active:return task
        time.sleep(.1)
    raise ValueError('NATIVE_EXIT_UNCONFIRMED')

def execute(plan):
    package_proof(plan)
    require(not (PUBLIC/'started.json').exists(),'CAMPAIGN_ALREADY_SELECTED')
    for name in ('private','nexus','connector','project-a','caller-b','profile'):
        support.secure(ROOT/name)
    PUBLIC.mkdir(exist_ok=True)
    for name in ('appdata','localappdata','tmp'):(ROOT/'profile'/name).mkdir(exist_ok=True)
    require(all(not any(Path(p).iterdir()) for p in plan['homes'].values()),'OWN_HOME_NOT_EMPTY')
    support.port_available(plan)
    os.environ.clear();os.environ.update(plan['environments']['A'])
    from okto_nexus.adapters.outbound.service_manager.installation import ServerInstallation
    from okto_nexus_connector.platform.user_service import UserService
    services={'nexus':ServerInstallation(Path(plan['homes']['nexus']),Path(plan['homes']['nexus'])/'nexus.db'),
        'connector':UserService(Path(plan['homes']['connector']))}
    require(all(s.name==plan['tasks'][n] and s.tasks.read(s.name) is None for n,s in services.items()),'TASK_ALREADY_PRESENT')
    save(PUBLIC/'started.json',{'plan_sha256':sha(ROOT/'plan.json'),'at':time.time(),'providers':0})
    results={}
    for name,service in services.items():
        code,_=cli(plan,name,'install');require(code==0,'INSTALL_FAILED')
        code,_=cli(plan,name,'start-initial');require(code in (0,3),'START_REFUSED')
        owner,ready=own_ready(plan,name,'windows-task-scheduler')
        contract=native_contract(service)
        save(PUBLIC/(name+'-initial-ready.json'),{'ready':support.public_status(ready),
            'birth_filetime':owner.birth,'image':owner.image,'native':contract})
        stop_owner(plan,name,'stop-t20',owner,service,task_present=True)
        stopped=inspect(plan,name)
        require(service.control(service.receipt())['desired']=='draining','STOP_LATCH_MISSING')
        quiet(plan,name,service,190,'T20-no-resurrection',stopped['reason'])
        connect_code,connect_result=cli(plan,name,'next-connect')
        if name=='connector':
            require(connect_code!=0 and inspect(plan,name)['state']=='stopped','EMPTY_CONNECT_UNEXPECTED_EFFECT')
            save(PUBLIC/'connector-next-connect-scope.json',{'status':'REFUSAL_WITHOUT_IDENTITY_ONLY',
                'returncode':connect_code,'successful_configured_connect_qualified':False})
            code,_=cli(plan,name,'start-for-crash');require(code in (0,3),'START_REFUSED')
        owner,ready=own_ready(plan,name,'windows-task-scheduler')
        require(owner.identity['generation']!=stopped.get('generation'),'NEW_OWNER_REQUIRED')
        contract=native_contract(service);births=[owner.birth];stamps=[contract['last_run_time']]
        for number in range(4):
            at=crash_once(plan,name,owner,service,contract,number)
            if number==3:break
            replacement,new_ready=own_ready(plan,name,'windows-task-scheduler')
            require(replacement.birth not in births and replacement.identity['generation']!=owner.identity['generation'],
                'AUTOMATIC_REPLACEMENT_NOT_NEW')
            delta=replacement.birth/10_000_000-11644473600-at
            require(delta>=59,'BACKOFF_SHORTER_THAN_CONTRACT_TOLERANCE')
            stamp=native_stamp(service);require(stamp not in stamps,'NATIVE_RESTART_TIMESTAMP_UNCHANGED')
            save(PUBLIC/(name+'-automatic-replacement-'+str(number+1)+'.json'),
                {'ready':support.public_status(new_ready),'birth_filetime':replacement.birth,'backoff_seconds':delta,
                 'measurement_tolerance_seconds':1,'native_last_run_time':stamp,'manual_start_issued':False})
            births.append(replacement.birth);stamps.append(stamp);owner=replacement
        task=wait_native_inactive(service);require(task.last_result==3,'INJECTED_EXIT_NOT_OBSERVED')
        last=inspect(plan,name)
        require(last.get('reason')=='SUPERVISOR_LAST_ATTEMPT_FAILED' and bool(last.get('next_action')),'ACTIONABLE_FAILURE_REQUIRED')
        quiet(plan,name,service,190,'T19-no-fourth-retry','SUPERVISOR_LAST_ATTEMPT_FAILED')
        code,value=cli(plan,name,'stop-after-exhaustion')
        require(code==0 and value.get('shutdown_outcome')=='drained','NORMAL_CLEANUP_STOP_UNCONFIRMED')
        before=support.fingerprint(Path(plan['homes'][name]),plan['uninstall_removes'][name])
        code,_=cli(plan,name,'uninstall');require(code==0 and service.tasks.read(service.name) is None,'UNINSTALL_UNCONFIRMED')
        after=support.fingerprint(Path(plan['homes'][name]),plan['uninstall_removes'][name])
        support.validate_preservation(before,after)
        save(PUBLIC/(name+'-data-retained.json'),{'before':before,'after':after,
            'identical':True,'excluded_integration_receipts':plan['uninstall_removes'][name]})
        require(Path(plan['homes'][name]).is_dir(),'DATA_HOME_REMOVED')
        results[name]={'T19':'PASS_KNOWN_EXIT_3_BOUNDED_SEQUENCE','T20':'PASS_SCOPED' if name=='nexus' else 'STOP_PASS_CONNECT_WITHOUT_IDENTITY_REFUSED',
            'crashes':4,'automatic_replacements':3,'task_absent':True,'data_home_retained':True}
    require(all(owner.exited() for owner in support.HANDLES),'CAPTURED_OWNER_STILL_LIVE')
    support.port_available(plan);package_proof(plan)
    save(PUBLIC/'qualification.json',{'status':'PASS_SCOPED','hosts':results,
        'no_provider_or_active_work_created':True,'M1_mutations':False,'canonical_force_stop_used':False,
        'limits':['Known injected code3, not arbitrary NTSTATUS','Connector successful configured next-connect not exercised','No model/M1 acceptance inferred']})

def main():
    p=argparse.ArgumentParser();p.add_argument('operation',choices=['execute'])
    p.add_argument('--expected-plan-sha256',required=True);p.add_argument('--expected-runner-sha256',required=True)
    args=p.parse_args()
    require(sha(ROOT/'plan.json')==args.expected_plan_sha256 and sha(__file__)==args.expected_runner_sha256,'SOURCE_CHANGED')
    try:
        execute(read(ROOT/'plan.json'))
    except BaseException as error:
        PUBLIC.mkdir(exist_ok=True)
        save(PUBLIC/'progression-failed.json',{'code':str(error) if isinstance(error,ValueError) else type(error).__name__,
            'cleanup_confirmed':False,'automatic_retry':False,'live_wrappers':[p.pid for p in support.CHILDREN if p.poll() is None]})
        raise
    finally:
        for owner in support.HANDLES:owner.close()

if __name__=='__main__':main()
