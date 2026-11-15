"""Root-selected canonical stop, with an exclusive reservation and no retry."""
from pathlib import Path
import hashlib,json,subprocess,sys,time

HERE=Path(__file__).resolve().parent
R=HERE.parent.parent
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(ok,reason):
    if not ok:raise RuntimeError(reason)
def save_new(path,value):
    with path.open('x',encoding='utf-8') as out:
        json.dump(value,out,indent=2);out.write('\n');out.flush()

def main():
    require(sha(HERE/'addendum.json')=='f9e17f6827d28204f3764c3f3456c435b66ec21616c998c1b4bfd4827fd05555','ADDENDUM_CHANGED')
    plan=read(HERE/'addendum.json')
    for pin in plan['pins'].values():require(sha(pin['path'])==pin['sha256'],'PIN_CHANGED')
    sys.path.insert(0,str(R))
    from recovery_context import RecoveryContext
    import recovery_connector as connector
    import recovery_observation as observed
    from okto_nexus_connector.daemon import manager
    X=RecoveryContext(plan['pins']['lifecycle']['path'],plan['pins']['lifecycle']['sha256'])
    selected=read(plan['pins']['selection']['path']);X.require_tags(selected)
    public=HERE/'public'
    require(not any((public/name).exists() for name in ('watch-timeout.json','watch-failed.json','exit-proof.json')),'WATCH_NOT_CURRENT')
    started=read(public/'watch-started.json')
    require(started['cohort']==selected['cohort']==plan['cohort'] and started['retained_roles']==list(observed.ROLES),'WATCH_SCOPE_CHANGED')
    require(started['addendum_sha256']==sha(HERE/'addendum.json'),'WATCH_ADDENDUM_CHANGED')
    watcher=observed.Process(started['observer']['pid'])
    try:
        require(watcher.birth==started['observer']['birth'] and not watcher.exited(),'OBSERVER_NOT_LIVE')
        require(watcher.image in X.installed['python_images'] and sha(watcher.image)==X.installed['python_images'][watcher.image],'OBSERVER_IMAGE_CHANGED')
        _,task=connector.installation(X).observe()
        require(task is not None and task.active and task.enabled and task.digest==selected['task']['digest'],'TASK_CHANGED')
        observed.same_cycle(selected['cohort'],connector.cycle(X))
        status=manager.status(Path(X.P['paths']['connector_state']),timeout=5).to_json()
        require(all(status.get(k)==selected[k] for k in ('pid','generation','instance_id')),'OWNER_CHANGED')
        require(status.get('running') is True and status.get('ipc_ok') is True and status.get('state')=='stopping','OWNER_NOT_PENDING')
        drain=status.get('drain') or {}
        require(drain.get('state')=='DRAINING_PENDING' and drain.get('force_available') is True and drain.get('force_requested') is False,'FORCE_NOT_AVAILABLE')
        require(not watcher.exited(),'OBSERVER_EXITED_BEFORE_SELECTION')
        authorization={'user_response':'pode fazer a parada que voce precisar do nexus',
            'scope':'Necessary stop of the pending temporary Nexus campaign Connector; root clarified target before action',
            'target_pid':selected['pid'],'generation':selected['generation'],'cycle':selected['cohort']['cycle_id'],
            'max_force_calls':1,'data_deletion':False,'provider_calls':0,'observed_at':time.time()}
        save_new(public/'force-authorization.json',authorization)
        save_new(public/'force-reservation.json',{'selected_at':time.time(),'argv':plan['canonical_force_argv'],
            'generation':selected['generation'],'max_calls':1,'unknown_result_must_not_replay':True,
            'watch_started_sha256':sha(public/'watch-started.json'),'canonical_preflight':status})
        print(json.dumps({'status':'ONE_CANONICAL_FORCE_RESERVED','pid':selected['pid']}),flush=True)
        # No wrapper timeout, signal, retry, or direct process termination.
        result=subprocess.run(plan['canonical_force_argv'],capture_output=True,text=True,encoding='utf-8')
        save_new(public/'force-result.json',{'argv':plan['canonical_force_argv'],'returncode':result.returncode,
            'stdout':result.stdout,'stderr':result.stderr,'completed_at':time.time(),
            'actual_canonical_command_calls':1,'physical_exit_proof_separate':True,'provider_calls':0})
        print(json.dumps({'status':'CANONICAL_FORCE_RETURNED','returncode':result.returncode,
            'receipt':str(public/'force-result.json')}),flush=True)
        return result.returncode
    finally:watcher.close()

if __name__=='__main__':raise SystemExit(main())
