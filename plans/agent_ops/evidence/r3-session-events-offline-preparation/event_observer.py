"""Finite before/after evidence. No Windows event or productive action is implemented."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib,json,os,time
import event_native as native

NAMES=('nexus','connector')
EVENTS=('01-suspend-resume','02-sign-out-logon','03-shutdown-power-on-logon','04-restart-logon')
ACTIONS=dict(zip(EVENTS,('sleep-wake','sign-out-sign-in','shutdown-power-on-sign-in','restart-sign-in')))
require=native.require

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def stamp():return datetime.now(timezone.utc).isoformat()
def save(path,value):
    path=Path(path)
    if path.exists():raise FileExistsError(path)
    writing=path.with_name(path.name+'.writing')
    with writing.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    # Windows rename is atomic and refuses an existing destination. Interrupted
    # writes remain .writing and block replay; they are never parsed as final.
    require(os.name=='nt','WINDOWS_PUBLICATION_REQUIRED')
    os.rename(writing,path)
    return digest(path)

def ready(component):
    c=component.get('canonical',{});t=component.get('task',{});cycle=component.get('cohort',{})
    return (component.get('cohort_confirmed') is True and c.get('state')=='ready'
        and c.get('ready_for_queries') is True and bool(c.get('generation'))
        and (component.get('component')!='nexus' or c.get('storage_initialized') is True)
        and t.get('present') is True and t.get('enabled') is True and t.get('logon_trigger_enabled') is True
        and t.get('restart_on_failure_present') is False and cycle.get('child_acknowledged') is True)

def invocation_inventory(root):
    return {p.name:digest(p) for p in sorted((Path(root)/'lifecycle').glob('*.reserved.json'))}

def expected_handles(snapshot):
    result={}
    for name in NAMES:
        for role in native.ROLES:result[name+'/'+role]=snapshot['components'][name]['cohort'][role]
    return result

def before(P,event,*,snapshot=native.snapshot):
    require(event in EVENTS,'EVENT_INVALID');directory=Path(P['root'])/'evidence'/event
    require(directory.is_dir(),'PREPARE_REQUIRED')
    require(not (directory/'before.json').exists(),'BEFORE_ALREADY_SELECTED')
    value,handles=snapshot(P,retain=True)
    try:
        require(all(ready(value['components'][n]) for n in NAMES),'PRE_EVENT_READY_UNCONFIRMED')
        require(set(handles)==set(expected_handles(value)),'SIX_HANDLES_REQUIRED')
        require(not value.get('own_session',{}).get('unconfirmed'),'OWN_LOGON_UNCONFIRMED')
        value.update(event_id=event,plan_sha256=digest(Path(P['root'])/'plan.json'),
            invocation_inventory=invocation_inventory(P['root']),event_action_selected=False)
        saved=save(directory/'before.json',value)
        return value,handles,saved
    except BaseException:
        for handle in handles.values():handle.close()
        raise

def retained_watch(P,event,value,handles,before_sha,*,clock=time.monotonic,sleep=time.sleep,seconds=1800):
    """Same finite foreground observer. Loss of this process leaves proof unavailable."""
    require(0<seconds<=1800,'WATCH_BOUND_INVALID')
    deadline=clock()+seconds;directory=Path(P['root'])/'evidence'/event
    result={'event_id':event,'before_sha256':before_sha,'identities':expected_handles(value),
        'started_utc':stamp(),'processes':{},'proof_source':'SAME_RETAINED_HANDLES','all_physical_exit_confirmed':False}
    try:
        while True:
            for key,h in handles.items():
                if key not in result['processes'] and h.exited():
                    result['processes'][key]={'physical_exit_confirmed':True,'exit_code':h.exit_code(),'observed_utc':stamp()}
            if len(result['processes'])==6 or (directory/'after.json').exists() or clock()>=deadline:break
            sleep(min(1,max(0,deadline-clock())))
        for key in handles:result['processes'].setdefault(key,{'physical_exit_confirmed':False,'state':'NOT_OBSERVED_EXITED'})
        result['all_physical_exit_confirmed']=all(x['physical_exit_confirmed'] for x in result['processes'].values())
        result['ended_utc']=stamp();save(directory/'retained-final.json',result)
        return result
    finally:
        for h in handles.values():h.close()

def validate_marker(marker,event,before_value):
    require(isinstance(marker,dict) and marker.get('event_id')==event and marker.get('action')==ACTIONS[event], 'ACTUAL_EVENT_MARKER_MISMATCH')
    require(marker.get('performed_by_user') is True and marker.get('no_manual_start_or_connect') is True,'MANUAL_ACTION_ATTESTATION_REQUIRED')
    require(isinstance(marker.get('source_reference'),str) and bool(marker['source_reference'].strip()),'ACTION_SOURCE_REQUIRED')
    began=datetime.fromisoformat(marker['started_utc']);ended=datetime.fromisoformat(marker['completed_utc'])
    require(began.tzinfo is not None and ended.tzinfo is not None and began>=datetime.fromisoformat(before_value['utc']) and ended>=began,'EVENT_TIMES_INVALID')
    return {k:marker[k] for k in ('event_id','action','performed_by_user','no_manual_start_or_connect','source_reference','started_utc','completed_utc')}

def after(P,event,marker,*,snapshot=native.snapshot,clock=time.monotonic,sleep=time.sleep):
    require(event in EVENTS,'EVENT_INVALID');directory=Path(P['root'])/'evidence'/event
    before_value=read(directory/'before.json');before_sha=digest(directory/'before.json')
    require(before_value['plan_sha256']==digest(Path(P['root'])/'plan.json'),'BEFORE_PLAN_MISMATCH')
    marker=validate_marker(marker,event,before_value)
    require(not (directory/'after.json').exists(),'AFTER_ALREADY_SELECTED')
    deadline=clock()+180;samples=[]
    while True:
        value,handles=snapshot(P)
        for h in handles.values():h.close()
        samples.append(value)
        if all(ready(value['components'][n]) for n in NAMES) or clock()>=deadline:break
        sleep(min(2,max(0,deadline-clock())))
    result={'event_id':event,'before_sha256':before_sha,'actual_event':marker,'observed_utc':stamp(),
        'samples':samples,'current':samples[-1],'invocation_inventory':invocation_inventory(P['root']),
        'automatic_start_selected':False,'provider_calls':0,'query_deadline_seconds':180,
        'os_call_preemption_claimed':False}
    save(directory/'after.json',result);return result

def old_shutdown(before_component,after_component):
    value=after_component.get('receipts',{}).get('shutdown',{})
    fields=value.get('fields',{})
    generation=before_component.get('canonical',{}).get('generation')
    if (value.get('present') is True and not value.get('unconfirmed') and generation
        and fields.get('generation')==generation and fields.get('state') in ('DRAINED','RECOVERY_REQUIRED')):
        return {'state':fields['state'],'generation_matches':True,'receipt_sha256':value.get('sha256'),'physical_exit_inferred':False}
    return {'state':'UNKNOWN','generation_matches':False,'physical_exit_inferred':False}

def instant(value):
    try:
        d=datetime.fromisoformat(value);return d.timestamp() if d.tzinfo else None
    except (ValueError,TypeError):return None

def logon_correlation(before_value,after_value,component):
    a=before_value.get('own_session',{});b=after_value.get('own_session',{})
    old=before_value['components'][component];new=after_value['components'][component]
    t=new.get('task',{});login=instant(b.get('logon_time_utc'));ran=instant(t.get('last_run_time_utc'))
    observed=instant(after_value.get('utc'))
    birth=new.get('cohort',{}).get('parent',{}).get('birth')
    born=(birth/10000000-11644473600) if type(birth) is int else None
    return bool(a.get('principal_sha256') and a.get('principal_sha256')==b.get('principal_sha256')
        and a.get('logon_authentication_id') and b.get('logon_authentication_id')
        and a['logon_authentication_id']!=b['logon_authentication_id']
        and ready(new) and old.get('task',{}).get('digest')==t.get('digest')
        and old.get('cohort')!=new.get('cohort') and login is not None and ran is not None
        and born is not None and observed is not None and login<=ran<=observed and login<=born<=observed)

def assess(before_value,after_value,before_sha,retained=None):
    require(after_value.get('before_sha256')==before_sha,'AFTER_BEFORE_HASH_MISMATCH')
    event=before_value['event_id'];require(after_value['event_id']==event,'EVENT_ID_MISMATCH')
    validate_marker(after_value['actual_event'],event,before_value)
    unchanged=before_value.get('invocation_inventory')==after_value.get('invocation_inventory')
    current=after_value['current'];result={'event_id':event,'before_sha256':before_sha,
        'classification':'OBSERVED_EVENT_FACTS_NOT_AUTOMATIC_ACCEPTANCE','productive_continuity_claimed':False,
        'provider_calls':0,'no_manual_start_in_owned_ledger':unchanged,'boot_without_login_claimed':False,'logon_correlation_is_not_absolute_causality':True,
        'prior_generation_physical_exit':'UNKNOWN','components':{}}
    if retained is not None:
        require(retained.get('before_sha256')==before_sha and retained.get('identities')==expected_handles(before_value),'RETAINED_PROOF_IDENTITY_MISMATCH')
        expected=set(expected_handles(before_value));actual=retained.get('processes',{})
        if (retained.get('proof_source')=='SAME_RETAINED_HANDLES' and set(actual)==expected
            and retained.get('all_physical_exit_confirmed') is True
            and all(v.get('physical_exit_confirmed') is True and type(v.get('exit_code')) is int for v in actual.values())):
            result['prior_generation_physical_exit']='ALL_SIX_RETAINED_HANDLES_OBSERVED_EXITED'
    for name in NAMES:
        old=before_value['components'][name];new=current['components'][name]
        identity_same=old.get('cohort')==new.get('cohort') and old.get('canonical',{}).get('generation')==new.get('canonical',{}).get('generation')
        result['components'][name]={'current_cohort_confirmed':new.get('cohort_confirmed') is True,
            'owner_relation':('SAME' if identity_same else 'REPLACED') if new.get('cohort_confirmed') is True else 'UNKNOWN',
            'old_generation_shutdown_receipt':old_shutdown(old,new),'current_ready':ready(new),
            'logon_trigger_correlated':event=='02-sign-out-logon' and unchanged and logon_correlation(before_value,current,name),
            'active_work_count':None,'work_settlement':'NOT_ASSERTED'}
    result['boot_marker_changed']=bool(before_value.get('own_session',{}).get('last_boot_up_time_dmtf')
        and current.get('own_session',{}).get('last_boot_up_time_dmtf')
        and before_value['own_session']['last_boot_up_time_dmtf']!=current['own_session']['last_boot_up_time_dmtf'])
    return result

def assessment(P,event):
    directory=Path(P['root'])/'evidence'/event
    result=assess(read(directory/'before.json'),read(directory/'after.json'),digest(directory/'before.json'),
        read(directory/'retained-final.json') if (directory/'retained-final.json').exists() else None)
    save(directory/'assessment.json',result);return result
