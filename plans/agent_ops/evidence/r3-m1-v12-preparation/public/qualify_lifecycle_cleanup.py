"""Run only synthetic lifecycle cleanup dispatch gates, never product commands."""
from pathlib import Path
import json,hashlib,subprocess,time
R=Path(__file__).resolve().parent;I=R/'draft/installation';Q=R/'lifecycle-cleanup-checks'
assert not Q.exists();Q.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
sources={str(p):sha(p) for p in (R/'test_lifecycle_cleanup_pending.py',R/'draft/m1_v12_lifecycle.py')}
env=json.loads((I/'environment.json').read_bytes());env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
argv=[str(I/'venv/Scripts/python.exe'),'-I','-B','-X','utf8','-m','pytest','-q','-p','no:cacheprovider',str(R/'test_lifecycle_cleanup_pending.py'),'--basetemp',str(Q/'pytest-tmp'),'--junitxml',str(Q/'results.xml')]
started=time.monotonic()
with (Q/'stdout.txt').open('xb') as out,(Q/'stderr.txt').open('xb') as err:
    child=subprocess.Popen(argv,cwd=Q,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    result=child.wait()
proof={'exit_code':result,'duration_seconds':time.monotonic()-started,'source_before':sources,
    'sources_unchanged':all(sha(Path(p))==v for p,v in sources.items()),'campaign_absent':not (R/'campaign').exists(),
    'scope':'Actual lifecycle wrapper via runpy, fake isolated Context, fake validator and fake subprocess only. Production helper semantics qualified separately; no real approval/product install/provider/service.'}
(Q/'result.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode())
print(json.dumps(proof));raise SystemExit(result)
