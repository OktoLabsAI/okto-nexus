from pathlib import Path
import hashlib,json,subprocess,time
S=Path(__file__).resolve().parent;B=S.parent;D=S/'draft';Q=S/'affected-001';Q.mkdir()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
sources={str(f):sha(f) for f in [*D.glob('*.py'),*(D/'controller').glob('*.py'),S/'test_lifecycle_cleanup.py']}
env=json.loads((B/'draft/installation/environment.json').read_bytes());env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
code='''import sys
from pathlib import Path
D=Path(sys.argv[1]);Q=Path(sys.argv[2]);S=D.parent
sys.path[:0]=[str(D/'controller'),str(D)]
import okto_nexus,nexus_connector_core,pytest
assert Path(okto_nexus.__file__).is_relative_to(Path(sys.prefix))
assert Path(nexus_connector_core.__file__).is_relative_to(Path(sys.prefix))
raise SystemExit(pytest.main(['-q','-p','no:cacheprovider',str(D/'controller/test_v11_allocation.py'),str(D/'controller/test_independent.py'),str(D/'controller/test_work_wrapper.py'),str(D/'test_remote_setup_composition.py'),str(D/'test_remote_transfer_monitor.py'),str(S/'test_lifecycle_cleanup.py'),'--basetemp',str(Q/'pytest-tmp'),'--junitxml',str(Q/'results.xml')]))
'''
started=time.monotonic()
with (Q/'stdout.txt').open('xb') as out,(Q/'stderr.txt').open('xb') as err:
    p=subprocess.Popen([str(B/'draft/installation/venv/Scripts/python.exe'),'-I','-B','-X','utf8','-c',code,str(D),str(Q)],cwd=Q,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    rc=p.wait()
proof={'exit_code':rc,'duration_seconds':time.monotonic()-started,'sources_before':sources,'sources_unchanged':all(sha(k)==v for k,v in sources.items()),'scope':'Affected successor policy8+4=12, ignored predecessor setup usage, independent controller, wrapper local/remote and lifecycle synthetic effects. No real campaign/provider/service/credential/installation. Deterministic allocation clocks only as documented; nominal timing remains real.'}
(Q/'result.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({k:v for k,v in proof.items() if k!='sources_before'}));raise SystemExit(rc)
