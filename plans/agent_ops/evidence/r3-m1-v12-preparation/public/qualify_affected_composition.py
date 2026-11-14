from pathlib import Path
import hashlib,json,subprocess,time
R=Path(__file__).resolve().parent;D=R/'draft';Q=R/'affected-composition';Q.mkdir()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
sources={str(f):sha(f) for f in [*D.glob('*.py'),*(D/'controller').glob('*.py'),*(D/'installation').glob('*.py'),R/'test_lifecycle_cleanup_pending.py']}
env=json.loads((D/'installation/environment.json').read_bytes());env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
reference=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v11-bundle-racan37z/draft/installation/venv')
code='''import sys,json,hashlib
from pathlib import Path
D=Path(sys.argv[1]);Q=Path(sys.argv[2]);R=D.parent
sys.path[:0]=[str(D/'controller'),str(D)]
import okto_nexus,nexus_connector_core
reference=Path(sys.prefix)
assert Path(okto_nexus.__file__).is_relative_to(reference) and Path(nexus_connector_core.__file__).is_relative_to(reference)
import pytest
raise SystemExit(pytest.main(['-q','-p','no:cacheprovider',str(D/'controller/test_v11_allocation.py'),str(D/'controller/test_setup_discovery_budget.py'),str(D/'controller/test_work_wrapper.py'),str(D/'installation/test_timed_install.py'),str(D/'test_remote_setup_composition.py'),str(D/'test_remote_transfer_monitor.py'),str(R/'test_lifecycle_cleanup_pending.py'),'--basetemp',str(Q/'pytest-tmp'),'--junitxml',str(Q/'results.xml')]))
'''
began=time.monotonic()
with (Q/'stdout.txt').open('xb') as out,(Q/'stderr.txt').open('xb') as err:
 child=subprocess.Popen([str(reference/'Scripts/python.exe'),'-I','-B','-X','utf8','-c',code,str(D),str(Q)],cwd=Q,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
 result=child.wait()
proof={'exit_code':result,'duration_seconds':time.monotonic()-began,'sources_before':sources,'sources_unchanged':all(sha(k)==v for k,v in sources.items()),'campaign_absent':not (R/'campaign').exists(),'scope':'Affected V12 identity/policy7+5=12 and setup discovery fixtures, fake installer/remote/lifecycle wrappers. No original64 full rerun. Allocation clocks deterministic; other tests retain documented clocks. No provider/service/credentials or product install.'}
(Q/'result.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode());print(json.dumps({k:v for k,v in proof.items() if k!='sources_before'}));raise SystemExit(result)
