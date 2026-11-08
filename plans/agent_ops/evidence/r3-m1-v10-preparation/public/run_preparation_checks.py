"""Run only fake installer transitions and real Python entrypoint refusals."""
from pathlib import Path
import hashlib,json,subprocess,time

ROOT=Path(__file__).resolve().parent
D=ROOT/'draft'
R=ROOT/'checks-initial'
assert not R.exists()
R.mkdir()
sources=[D/'campaign_context.py',D/'m1_v10_lifecycle.py',D/'m1_v10_setup.py',D/'m1_v10_remote_setup.py',
         D/'test_preparation_entries.py',D/'installation/timed_install.py',D/'installation/test_timed_install.py']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before={str(p):sha(p) for p in sources}
for p in sources:
    (R/p.name).write_bytes(p.read_bytes())
environment=json.loads((D/'installation/environment.json').read_bytes())
environment['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
argv=[str(D/'installation/venv/Scripts/python.exe'),'-I','-B','-X','utf8','-m','pytest','-q','-p','no:cacheprovider',
      str(D/'installation/test_timed_install.py'),str(D/'test_preparation_entries.py'),
      '--basetemp',str(R/'pytest-tmp'),'--junitxml',str(R/'results.xml')]
start=time.monotonic()
with (R/'stdout.txt').open('xb') as out,(R/'stderr.txt').open('xb') as err:
    child=subprocess.Popen(argv,cwd=R,env=environment,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    code=child.wait()
result={'exit_code':code,'duration_seconds':time.monotonic()-start,'argv':argv,
        'source_before':before,'source_unchanged':all(sha(p)==before[str(p)] for p in sources),
        'campaign_root_absent':not (ROOT/'campaign').exists(),
        'installation_unreserved':not any((D/'installation'/n).exists() for n in ('installation-reserved.json','installation-result.json','installation-unknown.json')),
        'scope':'Fake installer subprocess transitions and denied Python script entries only; no product installation/provider/service.'}
(R/'result.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
print(json.dumps({k:result[k] for k in ('exit_code','duration_seconds','source_unchanged','campaign_root_absent','installation_unreserved')}))
raise SystemExit(code)
