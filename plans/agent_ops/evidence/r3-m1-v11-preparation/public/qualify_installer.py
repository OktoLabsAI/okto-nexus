"""Fake installer transitions only; exact campaign target remains untouched."""
from pathlib import Path
import json,hashlib,subprocess,time
R=Path(__file__).resolve().parent;I=R/'draft/installation';Q=R/'installer-checks'
assert not Q.exists();Q.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
sources={str(p):sha(p) for p in (I/'test_timed_install.py',I/'timed_install.py')}
env=json.loads((I/'environment.json').read_bytes());env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
argv=[str(I/'venv/Scripts/python.exe'),'-I','-B','-X','utf8','-m','pytest','-q','-p','no:cacheprovider',str(I/'test_timed_install.py'),'--basetemp',str(Q/'pytest-tmp'),'--junitxml',str(Q/'results.xml')]
started=time.monotonic()
with (Q/'stdout.txt').open('xb') as out,(Q/'stderr.txt').open('xb') as err:
    child=subprocess.Popen(argv,cwd=Q,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    result=child.wait()
proof={'exit_code':result,'duration_seconds':time.monotonic()-started,'source_before':sources,
    'sources_unchanged':all(sha(Path(p))==v for p,v in sources.items()),
    'campaign_absent':not (R/'campaign').exists(),
    'installation_unreserved':not any((I/n).exists() for n in ('installation-reserved.json','installation-result.json','installation-unknown.json')),
    'scope':'Fake subprocesses, isolated synthetic approval fixtures only; no real receipt, product installation, provider or service.'}
(Q/'result.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode())
print(json.dumps(proof));raise SystemExit(result)
