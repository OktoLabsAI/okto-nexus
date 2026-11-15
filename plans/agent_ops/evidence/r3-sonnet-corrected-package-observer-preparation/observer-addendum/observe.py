"""Read-only retained handles for the single pending force target. No control API."""
from pathlib import Path
import argparse,hashlib,json,os,sys,time

HERE=Path(__file__).resolve().parent
R=HERE.parent.parent
ROLES=('parent','launcher','child')

def require(value,reason):
    if not value:raise RuntimeError(reason)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(65536),b''):h.update(block)
    return h.hexdigest()

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def publish(path,value):
    path=Path(path);pending=path.with_suffix('.pending')
    require(not path.exists(),'OBSERVATION_OUTPUT_ALREADY_EXISTS')
    with pending.open('x',encoding='utf-8') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.rename(pending,path)  # Windows rename refuses replacement of an existing final.

def validate_status(raw,selected):
    require(all(raw.get(k)==selected[k] for k in ('pid','generation','instance_id')),'EXACT_OWNER_CHANGED')
    drain=raw.get('drain') or {}
    require(raw.get('state')=='stopping' and raw.get('running') is True and raw.get('ipc_ok') is True
        and raw.get('draining') is True and drain.get('state')=='DRAINING_PENDING'
        and drain.get('force_available') is True and drain.get('force_requested') is False,
        'PENDING_CANONICAL_FORCE_NOT_AVAILABLE')
    return {k:drain.get(k) for k in ('state','phase','observation','force_available','force_requested')}

def exact_handle(handle,identity,images):
    require(handle.pid==identity['pid'] and handle.birth==identity['birth'] and handle.image in images
        and sha(handle.image)==images[handle.image] and not handle.exited(),'EXACT_LIVE_PROCESS_REQUIRED')

def wait_for_exits(handles,seconds,*,clock=time.monotonic,sleep=time.sleep):
    require(set(handles)==set(ROLES) and 0<seconds<=3600,'FINITE_THREE_HANDLE_OBSERVATION_REQUIRED')
    deadline=clock()+seconds
    while clock()<deadline:
        if all(h.exited() for h in handles.values()):
            return {'physical_exit_confirmed':True,'exits':{r:{'pid':h.pid,'birth':h.birth,
                'physical_exit':True,'exit_code':h.exit_code()} for r,h in handles.items()}}
        sleep(.2)
    return {'physical_exit_confirmed':False}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--expected-addendum-sha256',required=True)
    args=parser.parse_args();plan=HERE/'addendum.json'
    require(sha(plan)==args.expected_addendum_sha256,'ADDENDUM_CHANGED');P=read(plan)
    for item in P['pins'].values():require(sha(item['path'])==item['sha256'],'SOURCE_OR_ANCESTRY_CHANGED')
    sys.path.insert(0,str(R))
    from recovery_context import RecoveryContext
    import recovery_observation as observed
    import recovery_connector as connector
    from okto_nexus_connector.daemon import manager
    X=RecoveryContext(P['pins']['lifecycle']['path'],P['pins']['lifecycle']['sha256'])
    selected=read(P['pins']['selection']['path']);X.require_tags(selected)
    proposal=read(P['pins']['original_proposal']['path'])
    require(proposal['target_pid']==selected['pid']==39640
        and proposal['target_generation']==selected['generation']=='fbc0042be355e83da5bb695a64de4910'
        and proposal['target_cycle']==selected['cohort']['cycle_id']=='c5964050ef52fa22d53730a8f20872f7'
        and proposal['max_calls']==1,'ORIGINAL_TARGET_CHANGED')
    require(selected['cohort']==P['cohort'],'SELECTED_COHORT_CHANGED')
    require(proposal['argv']==P['canonical_force_argv'],'ORIGINAL_FORCE_ARGV_CHANGED')
    expired=read(P['pins']['expired_observation']['path'])
    require(expired['physical_exit_confirmed'] is False and expired['cohort']==selected['cohort'],
        'EXPIRED_OBSERVATION_PROVENANCE_CHANGED')
    handles={};own=None;started=False
    public=HERE/'public';public.mkdir(exist_ok=True)
    def recheck():
        service=connector.installation(X);_,task=service.observe()
        require(task is not None and task.active and task.enabled and task.digest==selected['task']['digest']
            and service.name==selected['task']['name'],'EXACT_ACTIVE_TASK_REQUIRED')
        observed.same_cycle(selected['cohort'],connector.cycle(X))
        raw=manager.status(Path(X.P['paths']['connector_state']),timeout=5).to_json()
        value=validate_status(raw,selected)
        for role,h in handles.items():exact_handle(h,selected['cohort'][role],X.installed['python_images'])
        observed.same_cycle(selected['cohort'],connector.cycle(X))
        return value
    try:
        recheck()
        for role in ROLES:
            handles[role]=observed.Process(selected['cohort'][role]['pid'])
            exact_handle(handles[role],selected['cohort'][role],X.installed['python_images'])
        canonical=recheck()
        own=observed.Process(os.getpid())
        exact_handle(own,{'pid':own.pid,'birth':own.birth},X.installed['python_images'])
        common={'addendum_sha256':args.expected_addendum_sha256,
            'original_proposal_sha256':P['pins']['original_proposal']['sha256'],
            'expired_observation_sha256':P['pins']['expired_observation']['sha256'],
            'cohort':selected['cohort'],'owner':{k:selected[k] for k in ('pid','generation','instance_id')},
            'task':selected['task'],'observer':{'pid':own.pid,'birth':own.birth},
            'observation_only':True,'terminate_right':False,'control_calls':0,'provider_calls':0,
            'work_settlement_claimed':False,'force_effect_provenance':'SEPARATE_ROOT_CANONICAL_ACTION_RECEIPT_REQUIRED'}
        publish(public/'watch-started.json',dict(common,retained_roles=list(ROLES),canonical=canonical,
            bound_seconds=P['observation_seconds'],observed_at=time.time()))
        started=True
        print(json.dumps({'status':'EXACT_THREE_HANDLES_RETAINED','receipt':str(public/'watch-started.json')}),flush=True)
        outcome=wait_for_exits(handles,P['observation_seconds'])
        if outcome['physical_exit_confirmed']:
            publish(public/'exit-proof.json',dict(common,**outcome,observed_at=time.time()))
            print(json.dumps({'status':'THREE_PHYSICAL_EXITS_CONFIRMED','force_effect_not_inferred':True}),flush=True)
            return 0
        publish(public/'watch-timeout.json',dict(common,**outcome,observed_at=time.time()))
        print(json.dumps({'status':'OBSERVATION_TIMEOUT_NOT_EXIT'}),flush=True);return 1
    except Exception as error:
        publish(public/'watch-failed.json',{'status':'OBSERVATION_UNCONFIRMED','physical_exit_confirmed':False,
            'handshake_published':started,'error_type':type(error).__name__,'control_calls':0,
            'addendum_sha256':args.expected_addendum_sha256})
        raise
    finally:
        if own is not None:own.close()
        for h in handles.values():h.close()

if __name__=='__main__':raise SystemExit(main())
