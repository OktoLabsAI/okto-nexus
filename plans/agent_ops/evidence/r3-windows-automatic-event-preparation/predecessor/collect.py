"""Read-only Windows-event collector; no OS event, task or service control."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from datetime import datetime,timezone

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from automation_contract import EVENTS, classify_event, require, validate_window

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load(path,sha):
    require(digest(path)==sha,'PLAN_CHANGED')
    plan=json.loads(Path(path).read_bytes())
    require(plan.get('selected_event') in EVENTS,'EVENT_WINDOW_NOT_SELECTED')
    require(plan.get('reviewed_for_execution') is True,'ROOT_REVIEW_REQUIRED')
    require(Path(sys.prefix).resolve()==Path(plan['python_prefix']).resolve(),'INSTALLED_PREFIX_CHANGED')
    for pin in plan['read_only_dependencies']:
        require(digest(pin['path'])==pin['sha256'],'DEPENDENCY_CHANGED')
    def module(name,path):
        spec=importlib.util.spec_from_file_location(name,path)
        value=importlib.util.module_from_spec(spec);sys.modules[name]=value;spec.loader.exec_module(value)
        return value
    native=module('event_native',plan['native_source'])
    observer=module('event_observer',plan['observer_source'])
    history=module('real_history',plan['history_source'])
    return plan,native,observer,history

def before(P,N,O,H,plan_sha):
    event=P['selected_event']; directory=Path(P['root'])/'evidence'/event
    directory.mkdir(parents=True,exist_ok=True)
    require(not (directory/'before.json').exists(),'BEFORE_ALREADY_SELECTED')
    value,handles=N.snapshot(P,retain=True)
    try:
        require(all(O.ready(value['components'][n]) for n in O.NAMES),'FRESH_BOTH_READY_REQUIRED')
        require(set(handles)==set(O.expected_handles(value)),'SIX_HANDLES_REQUIRED')
        require(not value['own_session'].get('unconfirmed'),'OWN_LOGON_UNCONFIRMED')
        require(validate_window(P['window'],datetime.now(timezone.utc),value['own_session']['principal_sha256'])==event,'WINDOW_EVENT_MISMATCH')
        for name in O.NAMES:
            require(value['components'][name]['task']['digest']==P['task_digests'][name],'TASK_CHANGED')
        state=H.capture(P)
        require(not any(h.exited() for h in handles.values()),'OWNER_EXIT_DURING_HISTORY')
        for name in O.NAMES:
            now=N.canonical_status(P,name); old=value['components'][name]['canonical']
            require(all(now.get(k)==old.get(k) for k in ('pid','generation','instance_id'))
                    and now.get('state')=='ready' and now.get('ready_for_queries') is True,'OWNER_CHANGED')
        value.update(event_id=event,plan_sha256=plan_sha,history=state,
                     invocation_inventory=O.invocation_inventory(P['root']),event_action_selected=False)
        pin=O.save(directory/'before.json',value)
        print(json.dumps({'status':'BEFORE_RETAINED','before_sha256':pin}),flush=True)
        O.retained_watch(P,event,value,handles,pin);handles={}
    finally:
        for handle in handles.values():handle.close()

def after(P,N,O,H,plan_sha):
    event=P['selected_event'];directory=Path(P['root'])/'evidence'/event
    old=O.read(directory/'before.json');old_sha=digest(directory/'before.json')
    require(old.get('plan_sha256')==plan_sha,'BEFORE_PLAN_CHANGED')
    # A logon task can run again. Existing evidence is never overwritten.
    if (directory/'after.json').exists():return {'status':'AFTER_ALREADY_RECORDED_NO_REPLAY'}
    with (directory/'after.reserved').open('x',encoding='ascii') as f:f.write(plan_sha)
    deadline=time.monotonic()+180;samples=[]
    while True:
        current,handles=N.snapshot(P)
        for h in handles.values():h.close()
        samples.append(current)
        if all(O.ready(current['components'][n]) for n in O.NAMES) or time.monotonic()>=deadline:break
        time.sleep(min(2,max(0,deadline-time.monotonic())))
    history=H.capture(P)
    # No manual-performed marker is fabricated. Suspend still needs independent
    # OS-transition evidence; elapsed time/API success alone is not that proof.
    assessment=classify_event(event,old['own_session'],current['own_session'])
    assessment.update(history=H.compare(old['history'],history),
                      before_sha256=old_sha,prior_generation_physical_exit='UNKNOWN',
                      provider_calls=0,productive_continuity_claimed=False,components={})
    for name in O.NAMES:
        assessment['components'][name]={
            'ready':O.ready(current['components'][name]),
            'task_digest_matches':current['components'][name]['task'].get('digest')==P['task_digests'][name],
            'old_generation_shutdown_receipt':O.old_shutdown(old['components'][name],current['components'][name]),
            'logon_trigger_correlated':O.logon_correlation(old,current,name),
            'work_settlement':'NOT_ASSERTED'}
    value={'event_id':event,'before_sha256':old_sha,'plan_sha256':plan_sha,
           'current':current,'samples':samples,'history':history,'assessment':assessment,
           'automatic_start_selected':False,'os_io_preemption_claimed':False}
    O.save(directory/'after.json',value)
    return {'status':'AFTER_RECORDED','event_id':event,'event_observed':assessment['event_observed'],'provider_calls':0}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',required=True);parser.add_argument('--sha256',required=True)
    parser.add_argument('--action',choices=('before','after'),default='after');args=parser.parse_args()
    P,N,O,H=load(args.plan,args.sha256)
    if args.action=='before':before(P,N,O,H,args.sha256)
    else:print(json.dumps(after(P,N,O,H,args.sha256)))

if __name__=='__main__':main()
