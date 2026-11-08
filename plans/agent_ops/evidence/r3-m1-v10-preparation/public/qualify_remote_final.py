"""Fake remote transfer composition; no helper/process/service/provider execution."""
from pathlib import Path
import hashlib,json,subprocess,time
R=Path(__file__).resolve().parent;D=R/'draft';Q=R/'remote-composition-final'
assert not Q.exists();Q.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
names=['remote_transfer_monitor.py','remote_stop_order.py','m1_v10_remote_setup.py','test_remote_transfer_monitor.py','test_remote_setup_composition.py']
before={n:sha(D/n) for n in names}
for n in names:(Q/n).write_bytes((D/n).read_bytes())
env=json.loads((D/'installation/environment.json').read_bytes());env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
code="import sys;sys.path.insert(0,sys.argv[1]);import pytest;raise SystemExit(pytest.main(sys.argv[2:]))"
argv=[str(D/'installation/venv/Scripts/python.exe'),'-I','-B','-X','utf8','-c',code,str(D),'-q','-p','no:cacheprovider',str(D/'test_remote_setup_composition.py'),'--basetemp',str(Q/'pytest-tmp'),'--junitxml',str(Q/'results.xml')]
began=time.monotonic()
with (Q/'stdout.txt').open('xb') as out,(Q/'stderr.txt').open('xb') as err:
    child=subprocess.Popen(argv,cwd=Q,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    code=child.wait()
result={'exit_code':code,'duration_seconds':time.monotonic()-began,'source_before':before,
    'source_unchanged':all(sha(D/n)==h for n,h in before.items()),'campaign_root_absent':not (R/'campaign').exists(),
    'scope':'Synthetic callbacks/threads and own test files only. Product Popen/helper transfer are substituted, no real HTTP/provider/credential/native service.'}
(Q/'result.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result));raise SystemExit(code)
