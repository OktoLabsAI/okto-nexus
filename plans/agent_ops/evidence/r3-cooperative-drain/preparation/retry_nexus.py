from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET

root=Path(__file__).parent
repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
source=root/'nexus-source-v1'
previous=root/'nexus-installed-v1'
assert (previous/'result.json').is_file(), 'First run must finish before input changes'
campaign=json.loads((previous/'canonical/campaign.json').read_text())
assert campaign['changed_inputs']==[]
out=root/'nexus-installed-fixture-retry'
out.mkdir()
changes=[]
for name in ('tools/offline_runtime_backup.py',):
    p=repo/name
    target=source/name
    assert not target.exists()
    shutil.copy2(p,target)
    changes.append({'path':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'reason':'missing repository backup test helper in frozen snapshot'})
for directory in ('plans/contratos','plans/r4_execution'):
    for p in (repo/directory).rglob('*'):
        if not p.is_file() or 'evidence' in p.parts or '__pycache__' in p.parts:
            continue
        if p.suffix not in {'.py','.json','.md','.sql'}:
            continue
        target=source/p.relative_to(repo)
        assert not target.exists(), str(target)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,target)
        changes.append({'path':p.relative_to(repo).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'reason':'missing normative test fixture in frozen snapshot'})
test='tests/execution_r4/test_renewal_storage_contention.py'
old=(source/test).read_bytes()
new=(repo/test).read_bytes()
assert old!=new
(source/test).write_bytes(new)
changes.append({'path':test,'before_sha256':hashlib.sha256(old).hexdigest(),'sha256':hashlib.sha256(new).hexdigest(),'reason':'existing fake owner needs _lease_wake event used by production constructor'})
cases=list(ET.parse(previous/'canonical/tests.xml').iter('testcase'))
selected=[]
diagnoses=[]
for case in cases:
    failure=case.find('failure')
    if failure is None:
        failure=case.find('error')
    if failure is None:
        continue
    trace=failure.text or ''
    assert ('FileNotFoundError' in trace and ('http-target.schema.json' in trace or 'offline_runtime_backup.py' in trace)) or ('_lease_wake' in trace), trace
    path=case.attrib['classname'].replace('.','/')+'.py'
    node=path+'::'+case.attrib['name']
    selected.append(node)
    diagnoses.append({'node':node,'classification':'missing normative fixture' if 'FileNotFoundError' in trace else 'incomplete fake owner','trace':trace})
# All four parameterizations verify the fixture repair; de-duplicate retry nodes.
selected=[s for s in selected if not s.startswith(test+'::')]+[test+'::test_transient_renewal_failure_retries_or_contains_only_session']
selected+=['tests/execution_r4/test_external_idle_scheduler_isolation.py']
selected+=json.loads((repo/'plans/agent_ops/evidence/r3-joint-contracts/recovery/selection.json').read_text())
(out/'fixture-provenance.json').write_text(json.dumps({'changes':changes,'diagnoses':diagnoses,'selected':selected,'product_bytes_changed':False},indent=2)+'\n')
env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','COMSPEC','PATH','PATHEXT','TEMP','TMP'}}
for name in ('USERPROFILE','APPDATA','LOCALAPPDATA'):
    env[name]=str(root/'isolated-env'/name.lower())
env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OKTO_NEXUS_NO_BANNER='1')
(out/'environment.json').write_text(json.dumps({'forwarded_names':sorted(env),'personal_profile_forwarded':False,'provider_credentials_forwarded':False,'native_service_registration':False},indent=2)+'\n')
python=root/'venv/Scripts/python.exe'
wheel=next((root/'nexus-wheel-v1').glob('*.whl'))
command=[str(python),'-I','-X','utf8',str(source/'tools/ci_installed.py'),'test','--wheel',str(wheel),'--output',str(out/'canonical'),'--tests',*selected]
with (out/'tests.txt').open('wb') as log:
    result=subprocess.run(command,cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
final=list(ET.parse(out/'canonical/tests.xml').iter('testcase')) if (out/'canonical/tests.xml').exists() else []
summary={'exit':result.returncode,'command':command,'cases':len(final),'failures':[c.attrib for c in final if c.find('failure') is not None or c.find('error') is not None],'skips':[c.attrib for c in final if c.find('skipped') is not None]}
(out/'result.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary))
raise SystemExit(result.returncode)
