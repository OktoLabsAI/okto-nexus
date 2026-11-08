from pathlib import Path
import hashlib,json,os,subprocess,sys,time
E=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v9-approved-execution/requirements-lf-correction')
R=json.loads((E/'reference.json').read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(R['proposal'])==R['proposal_sha256']
assert sha(R['approval_path'])==R['approval_sha256']
P=json.loads(Path(R['proposal']).read_text(encoding='utf-8'))
A=json.loads(Path(R['approval_path']).read_text(encoding='utf-8'))
assert A['status']=='USER_APPROVED' and A['proposal_sha256']==R['proposal_sha256']
C=json.loads(Path(P['execution_bundle']['commands']['path']).read_text(encoding='utf-8'))
assert sha(P['execution_bundle']['commands']['path'])==P['execution_bundle']['commands']['sha256']
mode,*selection=sys.argv[1:]
stdin_value=None
common=['--proposal',R['proposal'],'--expected-proposal-sha256',R['proposal_sha256'],
    '--approval-path',R['approval_path'],'--approval-sha256',R['approval_sha256']]
if mode in ('timed_install','lifecycle','setup','work','remote_setup'):
    entry=P['execution_bundle']['files'][mode]
    assert sha(entry['path'])==entry['sha256']
    argv=[R['python'],'-I','-B',entry['path'],*common,*selection]
elif mode=='plan':
    assert len(selection)==1
    assert sha(Path(R['bundle'])/'planning-commands.json')==R['planning_commands_sha256']
    plans=json.loads((Path(R['bundle'])/'planning-commands.json').read_text(encoding='utf-8'))
    argv=plans[selection[0]]['argv']
    assert selection[0]!='operator_login','Secret login uses its dedicated in-memory bootstrap helper'
    stdin_value=plans[selection[0]].get('nonsecret_stdin')
else:raise ValueError('unsupported approved invocation')
name='-'.join([mode,*selection]).replace('--','')
assert all(c.isalnum() or c in '_-' for c in name)
allowed={'SYSTEMROOT','WINDIR','COMSPEC','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA','HOMEDRIVE','HOMEPATH','USERNAME','USERDOMAIN','PATHEXT','PROGRAMDATA','PROGRAMFILES','PROGRAMFILES(X86)'}
env={k:v for k,v in os.environ.items() if k.upper() in allowed}
env['PATH']=os.pathsep.join(C['required_parent_path']);env['PYTHONIOENCODING']='utf-8'
with (E/(name+'.stdout')).open('xb') as out,(E/(name+'.stderr')).open('xb') as err:
    child=subprocess.Popen(argv,cwd=E,env=env,stdout=out,stderr=err,stdin=subprocess.PIPE if stdin_value is not None else subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    with (E/(name+'-process.json')).open('x',encoding='utf-8') as record:
        json.dump({'pid':child.pid,'selected_at':time.time(),'mode':mode,'selection':selection},record)
        record.flush();os.fsync(record.fileno())
    if stdin_value is not None:
        child.communicate(stdin_value.encode('utf-8'))
    code=child.wait()
print(json.dumps({'mode':mode,'selection':selection,'returncode':code,'stdout':str(E/(name+'.stdout')),'stderr':str(E/(name+'.stderr'))}))
raise SystemExit(code)
