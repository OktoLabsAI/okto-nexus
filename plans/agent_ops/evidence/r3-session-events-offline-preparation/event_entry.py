"""Explicit reviewed entry. OS actions remain manual; no such API is present."""
from pathlib import Path
import argparse,hashlib,json,sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(value,code):
    if not value:raise RuntimeError(code)

def load(freeze_sha,authorization_path,authorization_sha):
    require(sha(HERE/'runtime-freeze.json')==freeze_sha,'RUNTIME_FREEZE_CHANGED')
    freeze=json.loads((HERE/'runtime-freeze.json').read_bytes())
    for name,pin in freeze['runtime'].items():require(sha(HERE/name)==pin['sha256'],'RUNTIME_CHANGED_'+name)
    P=json.loads((HERE/'plan.json').read_bytes())
    require(Path(P['root']).resolve()==HERE and Path(sys.executable).resolve()==Path(P['python']).resolve()
        and Path(sys.prefix).resolve()==Path(P['python_prefix']).resolve(),'EXECUTION_PREFIX_MISMATCH')
    require(sha(P['package']['path'])==P['package']['sha256'],'PACKAGE_MANIFEST_CHANGED')
    package=json.loads(Path(P['package']['path']).read_bytes())
    for pin in [*package['files'],*P['source_pins']]:require(sha(pin['path'])==pin['sha256'],'INSTALLED_PAYLOAD_CHANGED')
    for path,digest in P['python_images'].items():require(sha(path)==digest,'PYTHON_IMAGE_CHANGED')
    path=Path(authorization_path)
    require(path.resolve()==HERE/'authorization.json' and sha(path)==authorization_sha,'AUTHORIZATION_REFERENCE_CHANGED')
    auth=json.loads(path.read_bytes())
    require(auth.get('status')=='USER_COORDINATED_EVENTS_SELECTED' and auth.get('plan_sha256')==sha(HERE/'plan.json')
        and auth.get('runtime_freeze_sha256')==freeze_sha and auth.get('manual_os_actions_only') is True
        and auth.get('temporary_tasks_selected') is True and bool(auth.get('user_reference')),'EVENT_COORDINATION_NOT_SELECTED')
    expected={e['id'] for e in P['events']}
    require(isinstance(auth.get('events'),list) and bool(auth['events']) and set(auth['events'])<=expected,'EVENT_SELECTION_INVALID')
    return P,auth

def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--freeze-sha256',required=True)
    parser.add_argument('--authorization',required=True);parser.add_argument('--authorization-sha256',required=True)
    parser.add_argument('action',choices=('prepare','install','initial_start','ready','before','after','assess','cleanup_stop','cleanup_uninstall'))
    parser.add_argument('--component',choices=('nexus','connector'));parser.add_argument('--event')
    parser.add_argument('--actual-marker');args=parser.parse_args(argv)
    P,auth=load(args.freeze_sha256,args.authorization,args.authorization_sha256)
    import event_lifecycle as L
    import event_observer as O
    if args.action=='prepare':result=L.prepare(P)
    elif args.action in ('install','initial_start'):
        require(args.component is not None,'COMPONENT_REQUIRED');result=L.initial(P,args.component,args.action)
    elif args.action=='ready':result=L.observe_ready(P)
    elif args.action in ('before','after','assess'):
        require(args.event in auth['events'],'EVENT_NOT_SELECTED')
        if args.action=='before':
            value,handles,before_sha=O.before(P,args.event)
            print(json.dumps({'status':'BEFORE_DURABLE','event_id':args.event,'sha256':before_sha}),flush=True)
            result=O.retained_watch(P,args.event,value,handles,before_sha)
        elif args.action=='after':
            require(args.actual_marker is not None,'ACTUAL_EVENT_MARKER_REQUIRED')
            result=O.after(P,args.event,O.read(args.actual_marker))
        else:result=O.assessment(P,args.event)
    elif args.action=='cleanup_stop':
        require(args.component is not None,'COMPONENT_REQUIRED');result=L.current_stop(P,args.component)
    else:
        require(args.component is not None,'COMPONENT_REQUIRED');result=L.uninstall(P,args.component)
    # Full metadata are durable own files; terminal output is deliberately concise.
    print(json.dumps({'action':args.action,'status':result.get('status',result.get('classification','RECORDED')),'provider_calls':0}))
    return 0
if __name__=='__main__':raise SystemExit(main())
