from pathlib import Path
import hashlib, json, os, subprocess, sys, time

E = Path(__file__).parent
B = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v10-bundle-pscf18t5/draft')
proposal_path = B / 'm1-codex-campaign-proposal-v10.json'
proposal_hash = '90c2ed2ca18e7fd86380c614e516a5f8975af2a2052b56a3609004be4814405a'
approval_hash = '8500ae2cd11ff8dca2bc1551a9a5349f76075a0578f2e931c436a09ee2515620'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(proposal_path) == proposal_hash and sha(E/'authorization.json') == approval_hash
P = json.loads(proposal_path.read_text())
C = json.loads(Path(P['execution_bundle']['commands']['path']).read_text())
assert sha(P['execution_bundle']['commands']['path']) == P['execution_bundle']['commands']['sha256']
common = ['--proposal',str(proposal_path),'--expected-proposal-sha256',proposal_hash,
          '--approval-path',str(E/'authorization.json'),'--approval-sha256',approval_hash]
mode, *selection = sys.argv[1:]
stdin_value = None
if mode in ('lifecycle','setup','work','remote_setup'):
    choices = {'lifecycle': [('initialize',)] + [(c,a) for c in ('nexus','connector') for a in ('install','start','stop','uninstall')],
               'setup': [('local',)], 'work': [(c,a) for c in ('local','connector') for a in ('useful','continuation')],
               'remote_setup': [('transfer',)]}
    assert tuple(selection) in choices[mode]
    entry = P['execution_bundle']['files'][mode]
    assert sha(entry['path']) == entry['sha256']
    argv = [P['package_pins']['python'],'-I','-B',entry['path'],*common,*selection]
elif mode == 'plan':
    assert len(selection) == 1 and selection[0] in ('local_plan','connector_host_draft','remote_plan')
    entry = next(v for v in P['execution_bundle']['files'].values() if Path(v['path']).name == 'planning-commands.json')
    assert sha(entry['path']) == entry['sha256']
    plans = json.loads(Path(entry['path']).read_text())
    # Validate the exact installed context before a planning command as well.
    sys.path.insert(0,str(B))
    from campaign_context import load
    sys.argv = [sys.argv[0],*common]
    X = load()
    argv = plans[selection[0]]['argv']
    stdin_value = plans[selection[0]].get('nonsecret_stdin')
else:
    raise ValueError('Unsupported finite invocation')
name = '-'.join([mode,*selection])
allowed = {'SYSTEMROOT','WINDIR','COMSPEC','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA','HOMEDRIVE','HOMEPATH','USERNAME','USERDOMAIN','PATHEXT','PROGRAMDATA','PROGRAMFILES','PROGRAMFILES(X86)'}
env = {k:v for k,v in os.environ.items() if k.upper() in allowed}
env['PATH'] = os.pathsep.join(C['required_parent_path'])
env['PYTHONIOENCODING'] = 'utf-8'
with (E/(name+'.stdout')).open('xb') as out, (E/(name+'.stderr')).open('xb') as err:
    child = subprocess.Popen(argv,cwd=E,env=env,stdout=out,stderr=err,
        stdin=subprocess.PIPE if stdin_value is not None else subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW)
    with (E/(name+'-process.json')).open('x',encoding='utf-8') as record:
        json.dump({'pid':child.pid,'selected_at':time.time(),'mode':mode,'selection':selection,
                   'proposal_sha256':proposal_hash,'approval_sha256':approval_hash},record)
        record.flush();os.fsync(record.fileno())
    if stdin_value is not None: child.communicate(stdin_value.encode('utf-8'))
    code = child.wait()
print(json.dumps({'mode':mode,'selection':selection,'returncode':code,
    'stdout_sha256':sha(E/(name+'.stdout')),'stderr_sha256':sha(E/(name+'.stderr'))}),flush=True)
raise SystemExit(code)
