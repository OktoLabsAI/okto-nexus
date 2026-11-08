"""Synthetic v10 composition, using qualified installed products read-only."""
from pathlib import Path
import hashlib,json,subprocess,time

R=Path(__file__).resolve().parent;D=R/'draft';Q=R/'observer-composition-initial'
assert not Q.exists();Q.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
files=list((D/'controller').glob('*.py'))+[D/'m1_v10_work.py',D/'response_loss.py',D/'publication.py']
before={str(p):sha(p) for p in files}
for p in files:
    target=Q/'sources'/p.relative_to(D);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
env=json.loads((D/'installation/environment.json').read_bytes());env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
reference=Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-recovery-diagnostics-installed-xtfm5o4x/venv')
code=r'''
import sys,json,hashlib,importlib
from pathlib import Path
D=Path(sys.argv[1]);Q=Path(sys.argv[2]);REF=Path(sys.argv[3])
sys.path[:0]=[str(D/'controller'),str(D)]
origins={}
for name in ('controller','legacy_controller','independent_controller','api_worker','independent_journal','history_observers','serial_flow','setup_journal','token_collector','observation_guard','publication','response_loss','okto_nexus','nexus_connector_core'):
    m=importlib.import_module(name);p=Path(m.__file__).resolve()
    expected=REF/'Lib/site-packages' if name in ('okto_nexus','nexus_connector_core') else D
    assert p.is_relative_to(expected.resolve()),(name,str(p))
    origins[name]={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
from controller import POLICY,ANCESTRY
assert POLICY['revision']==10 and POLICY['carry_in_admissions']==5 and POLICY['carry_in_tokens']==67658
assert POLICY['max_new_admissions']==6 and POLICY['max_cumulative_admissions']==11
(Q/'module-origins.json').write_bytes((json.dumps({'modules':origins,'policy':POLICY,'ancestry':ANCESTRY},indent=2)+'\n').encode())
import pytest
raise SystemExit(pytest.main(['-q','-p','no:cacheprovider',str(D/'controller/test_independent.py'),str(D/'controller/test_work_wrapper.py'),'--basetemp',str(Q/'pytest-tmp'),'--junitxml',str(Q/'results.xml')]))
'''
argv=[str(reference/'Scripts/python.exe'),'-I','-B','-X','utf8','-c',code,str(D),str(Q),str(reference)]
start=time.monotonic()
with (Q/'stdout.txt').open('xb') as out,(Q/'stderr.txt').open('xb') as err:
    child=subprocess.Popen(argv,cwd=Q,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    code=child.wait()
proof={'exit_code':code,'duration_seconds':time.monotonic()-start,'source_before':before,
       'source_unchanged':all(sha(Path(p))==h for p,h in before.items()),
       'campaign_root_absent':not (R/'campaign').exists(),
       'installation_unreserved':not any((D/'installation'/n).exists() for n in ('installation-reserved.json','installation-result.json','installation-unknown.json')),
       'scope':'Actual v10 rebased modules and synthetic Core journals. Installed products are imported from qualified reference environment; no campaign product install, provider, vault or service.'}
(Q/'result.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode())
print(json.dumps({k:proof[k] for k in ('exit_code','duration_seconds','source_unchanged','campaign_root_absent','installation_unreserved')}))
raise SystemExit(code)
