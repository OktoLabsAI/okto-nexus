"""Only the exact eight v7 lifecycle commands. No provider command execution."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
REPO=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
P=json.loads((REPO/'plans/agent_ops/evidence/r3-m1-controller/m1-codex-campaign-proposal-v7.json').read_text())
C=json.loads((REPO/'plans/agent_ops/evidence/r3-m1-execution-context/proposed-commands.json').read_text())
ROOT=Path(P['paths']['campaign_root'])
def env():
    allowed=('SystemRoot','WINDIR','COMSPEC','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA','HOMEDRIVE','HOMEPATH','USERNAME','USERDOMAIN','PATHEXT','PROGRAMDATA','PROGRAMFILES','PROGRAMFILES(X86)')
    value={k:v for k,v in os.environ.items() if k.upper() in {x.upper() for x in allowed}}
    value['PATH']=os.pathsep.join(C['required_parent_path'])
    value['PYTHONIOENCODING']='utf-8'
    return value
def initialize():
    assert not ROOT.exists()
    ROOT.mkdir()
    for key,value in P['paths'].items():
        if key not in ('campaign_root','codex_executable'):
            path=Path(value); assert path.is_relative_to(ROOT)
            path.mkdir(parents=True,exist_ok=False)
    fixture=P['finite_work']['fixture']['numbers.csv'].encode()
    assert hashlib.sha256(fixture).hexdigest()==P['finite_work']['delivery']['expected_shape']['input_sha256']
    for lane in ('local_project','remote_project'):
        with (Path(P['paths'][lane])/'numbers.csv').open('xb') as f:f.write(fixture)
    (ROOT/'public'/'authorization.json').write_text(json.dumps({'proposal_revision':7,'user_answer':'sim pode executar','relayed_by':'root','scope':'Exact v7 finite M1 and two owned tasks; no personal files read by agent.'},indent=2))
    print(json.dumps({'initialized':True,'root':str(ROOT)}))
def lifecycle(component,action):
    command=next(x for x in C['steps'] if x['component']==component and x['action']==action)
    record=ROOT/'public'/('lifecycle-'+component+'-'+action+'.json')
    assert not record.exists(), 'An action record exists: reconcile, never replay.'
    record.write_text(json.dumps({'state':'DISPATCH_RESERVED','component':component,'action':action,'task_name':command['task_name'],'argv':command['argv']},indent=2))
    out=ROOT/'private'/(component+'-'+action+'.stdout')
    err=ROOT/'private'/(component+'-'+action+'.stderr')
    with out.open('xb') as stdout,err.open('xb') as stderr:
        process=subprocess.Popen(command['argv'],cwd=ROOT,env=env(),stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
        (ROOT/'public'/('process-'+component+'-'+action+'.json')).write_text(json.dumps({'pid':process.pid,'created':time.time(),'component':component,'action':action}))
        code=process.wait() # outer exec handle retained; never timeout-kill
    try:value=json.loads(out.read_text(encoding='utf-8'))
    except (ValueError,UnicodeError):value={}
    public={'state':'RETURNED','component':component,'action':action,'task_name':command['task_name'],'returncode':code,
            'reported_state':value.get('state'),'reported_code':value.get('code'),
            'output_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'error_sha256':hashlib.sha256(err.read_bytes()).hexdigest()}
    record.write_text(json.dumps(public,indent=2))
    print(json.dumps(public))
    return code
if __name__=='__main__':
    if sys.argv[1:] == ['initialize']:initialize()
    else:
        assert len(sys.argv)==3 and sys.argv[1] in ('nexus','connector') and sys.argv[2] in ('install','start','stop','uninstall')
        raise SystemExit(lifecycle(*sys.argv[1:]))
