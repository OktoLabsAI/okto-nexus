"""Finite lifecycle for adopted homes; initialize only new evidence directories."""
from pathlib import Path
import hashlib,importlib.util,json,os,subprocess,sys,time
sys.path.insert(0,str(Path(__file__).parent))
from campaign_context import load,reserve_json,require
X=load()  # refuses before any product import or effect when approval is absent
P,C,ROOT=X.P,X.C,X.ROOT

def initialize():
    require(ROOT.is_dir() and X.CONTROL==ROOT/'successor13','OWNERSHIP_ROOT_REQUIRED')
    require(not X.PUBLIC.exists() and not X.PRIVATE.exists(),'FRESH_CONTROL_EVIDENCE_REQUIRED')
    fixture=P['finite_work']['fixture']['numbers.csv'].encode()
    require(hashlib.sha256(fixture).hexdigest()==P['finite_work']['delivery']['expected_shape']['input_sha256'],'FIXTURE_MISMATCH')
    for lane in ('local_project','remote_project'):
        require((Path(P['paths'][lane])/'numbers.csv').read_bytes()==fixture,'ADOPTED_FIXTURE_CHANGED')
    for lane in ('local_output','connector_output'):
        require(not Path(P['finite_work']['delivery'][lane]).exists(),'PRIOR_DELIVERABLE_PRESENT')
    X.PUBLIC.mkdir();X.PRIVATE.mkdir()
    reserve_json(X.PUBLIC/'authorization-reference.json',{'proposal_sha256':X.args.expected_proposal_sha256,
        'approval_sha256':X.args.approval_sha256,'campaign_root':str(ROOT),'control_root':str(X.CONTROL),
        'scope':'Work successor control only; adopted homes, configured profile and predecessor checkpoint unchanged.'})
    print(json.dumps({'initialized':True,'ownership_root':str(ROOT),'control_root':str(X.CONTROL)}))

def lifecycle(component,action):
    command=next(s for s in C['steps'] if s['component']==component and s['action']==action)
    record=X.PUBLIC/f'lifecycle-{component}-{action}.json'
    if record.exists():
        print(json.dumps({'status':'EXISTING_ACTION_RECONCILE_ONLY','component':component,'action':action,'record':str(record),'replayed':False}))
        return 3
    cleanup_proof_sha256=None
    if action=='uninstall':
        raw=(X.PUBLIC/f'cleanup-{component}.json').read_bytes()
        proof=json.loads(raw)
        cleanup_proof_sha256=hashlib.sha256(raw).hexdigest()
        if proof.get('kind')=='NEVER_STARTED_OWNER_ABSENT':
            require(proof.get('component')==component and proof.get('task_name')==command['task_name'],
                    'CLEANUP_TARGET_MISMATCH')
            pin=P['execution_bundle']['files']['root_driver_confirm_cleanup']
            require(hashlib.sha256(Path(pin['path']).read_bytes()).hexdigest()==pin['sha256'],'CLEANUP_VALIDATOR_CHANGED')
            spec=importlib.util.spec_from_file_location('m1_v13_cleanup_validator',pin['path'])
            helper=importlib.util.module_from_spec(spec);sys.modules[spec.name]=helper;spec.loader.exec_module(helper)
            require(helper.validate_never_started(X,proof,allow_current_uninstall=True) is True,'NEVER_STARTED_PROOF_REQUIRED')
        else:
            require(proof.get('task_name')==command['task_name'] and proof.get('owned_pid_birth_exit_confirmed') is True
                    and proof.get('task_stopped_confirmed') is True and proof.get('force_used') is False,'NORMAL_STOP_EXIT_PROOF_REQUIRED')
    reserve_json(record,{'state':'DISPATCH_RESERVED','component':component,'action':action,
        'task_name':command['task_name'],'argv':command['argv'],'proposal_sha256':X.args.expected_proposal_sha256,
        'cleanup_proof_sha256':cleanup_proof_sha256,'time':time.time()})
    out,err=X.PRIVATE/f'{component}-{action}.stdout',X.PRIVATE/f'{component}-{action}.stderr'
    with out.open('xb') as stdout,err.open('xb') as stderr:
        process=subprocess.Popen(command['argv'],cwd=ROOT,env=X.env(),stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
        reserve_json(X.PUBLIC/f'process-{component}-{action}.json',{'pid':process.pid,'created':time.time(),'component':component,'action':action})
        code=process.wait()  # keep outer handle; never timeout-kill/replay
    try:value=json.loads(out.read_text(encoding='utf-8'))
    except (ValueError,UnicodeError):value={}
    public={'state':'RETURNED','component':component,'action':action,'task_name':command['task_name'],'returncode':code,
        'reported_state':value.get('state'),'reported_code':value.get('code'),'cleanup_proof_sha256':cleanup_proof_sha256,
        'output_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'error_sha256':hashlib.sha256(err.read_bytes()).hexdigest()}
    reserve_json(X.PUBLIC/f'lifecycle-{component}-{action}-result.json',public)
    print(json.dumps(public));return code

if X.remaining==['initialize']:initialize()
else:
    require(len(X.remaining)==2 and X.remaining[0] in ('nexus','connector') and X.remaining[1] in ('install','start','stop','uninstall'),'ACTION_INVALID')
    raise SystemExit(lifecycle(*X.remaining))
