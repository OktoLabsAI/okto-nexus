"""Exactly one each of the eight proposed lifecycle actions; no force/replay."""
from pathlib import Path
import hashlib,importlib.util,json,os,subprocess,sys,time
sys.path.insert(0,str(Path(__file__).parent))
from campaign_context import load,reserve_json,require
X=load()  # refuses before any product import or effect when approval is absent
P,C,ROOT=X.P,X.C,X.ROOT

def initialize():
    require(not ROOT.exists(),'FRESH_ROOT_REQUIRED')
    ROOT.mkdir()
    for key,value in P['paths'].items():
        if key not in ('campaign_root','codex_executable'):
            Path(value).mkdir(parents=True,exist_ok=False)
    fixture=P['finite_work']['fixture']['numbers.csv'].encode()
    require(hashlib.sha256(fixture).hexdigest()==P['finite_work']['delivery']['expected_shape']['input_sha256'],'FIXTURE_MISMATCH')
    for lane in ('local_project','remote_project'):
        with (Path(P['paths'][lane])/'numbers.csv').open('xb') as stream:
            stream.write(fixture);stream.flush();os.fsync(stream.fileno())
    reserve_json(ROOT/'public/authorization-reference.json',{'proposal_sha256':X.args.expected_proposal_sha256,
        'approval_sha256':X.args.approval_sha256,'scope':'This fresh successor only; no force or replay.'})
    print(json.dumps({'initialized':True,'root':str(ROOT)}))

def lifecycle(component,action):
    command=next(s for s in C['steps'] if s['component']==component and s['action']==action)
    record=ROOT/'public'/f'lifecycle-{component}-{action}.json'
    if record.exists():
        print(json.dumps({'status':'EXISTING_ACTION_RECONCILE_ONLY','component':component,'action':action,'record':str(record),'replayed':False}))
        return 3
    cleanup_proof_sha256=None
    if action=='uninstall':
        raw=(ROOT/'public'/f'cleanup-{component}.json').read_bytes()
        proof=json.loads(raw)
        cleanup_proof_sha256=hashlib.sha256(raw).hexdigest()
        if proof.get('kind')=='NEVER_STARTED_OWNER_ABSENT':
            require(proof.get('component')==component and proof.get('task_name')==command['task_name'],
                    'CLEANUP_TARGET_MISMATCH')
            pin=P['execution_bundle']['files']['root_driver_confirm_cleanup']
            require(hashlib.sha256(Path(pin['path']).read_bytes()).hexdigest()==pin['sha256'],'CLEANUP_VALIDATOR_CHANGED')
            spec=importlib.util.spec_from_file_location('m1_v11_cleanup_validator',pin['path'])
            helper=importlib.util.module_from_spec(spec);sys.modules[spec.name]=helper;spec.loader.exec_module(helper)
            require(helper.validate_never_started(X,proof,allow_current_uninstall=True) is True,'NEVER_STARTED_PROOF_REQUIRED')
        else:
            require(proof.get('task_name')==command['task_name'] and proof.get('owned_pid_birth_exit_confirmed') is True
                    and proof.get('task_stopped_confirmed') is True and proof.get('force_used') is False,'NORMAL_STOP_EXIT_PROOF_REQUIRED')
    reserve_json(record,{'state':'DISPATCH_RESERVED','component':component,'action':action,
        'task_name':command['task_name'],'argv':command['argv'],'proposal_sha256':X.args.expected_proposal_sha256,
        'cleanup_proof_sha256':cleanup_proof_sha256,'time':time.time()})
    out,err=ROOT/'private'/f'{component}-{action}.stdout',ROOT/'private'/f'{component}-{action}.stderr'
    with out.open('xb') as stdout,err.open('xb') as stderr:
        process=subprocess.Popen(command['argv'],cwd=ROOT,env=X.env(),stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
        reserve_json(ROOT/'public'/f'process-{component}-{action}.json',{'pid':process.pid,'created':time.time(),'component':component,'action':action})
        code=process.wait()  # keep outer handle; never timeout-kill/replay
    try:value=json.loads(out.read_text(encoding='utf-8'))
    except (ValueError,UnicodeError):value={}
    public={'state':'RETURNED','component':component,'action':action,'task_name':command['task_name'],'returncode':code,
        'reported_state':value.get('state'),'reported_code':value.get('code'),'cleanup_proof_sha256':cleanup_proof_sha256,
        'output_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'error_sha256':hashlib.sha256(err.read_bytes()).hexdigest()}
    reserve_json(ROOT/'public'/f'lifecycle-{component}-{action}-result.json',public)
    print(json.dumps(public));return code

if X.remaining==['initialize']:initialize()
else:
    require(len(X.remaining)==2 and X.remaining[0] in ('nexus','connector') and X.remaining[1] in ('install','start','stop','uninstall'),'ACTION_INVALID')
    raise SystemExit(lifecycle(*X.remaining))
