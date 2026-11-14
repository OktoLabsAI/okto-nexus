"""Final exact-path verifier and denied shell entries. No product installation."""
from pathlib import Path
import hashlib,json,subprocess,time
R=Path(__file__).resolve().parent;D=R/'draft';Q=R/'reviewed-final-entry-gates'
assert not Q.exists();Q.mkdir()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
proposal=D/'m1-codex-campaign-proposal-v11.json';p=json.loads(proposal.read_bytes())
files={v['path']:v['sha256'] for v in p['execution_bundle']['files'].values()}
files[str(proposal)]=sha(proposal)
files[str(D/'test_preparation_entries.py')]=sha(D/'test_preparation_entries.py')
for path,digest in files.items():assert sha(path)==digest
for path in D.rglob('*.py'):
    if 'venv' not in path.parts:compile(path.read_bytes(),str(path),'exec')
env=json.loads((D/'installation/environment.json').read_bytes());env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
code=r'''
import sys,json,hashlib,importlib.util
from pathlib import Path
D=Path(sys.argv[1]);Q=Path(sys.argv[2]);I=D/'installation'
names=('okto_nexus','okto_nexus_connector','nexus_connector_core')
def absent():
    assert all(importlib.util.find_spec(n) is None for n in names)
    assert not (D.parent/'campaign').exists()
    assert not any((I/n).exists() for n in ('installation-reserved.json','installation-result.json','installation-unknown.json'))
absent()
spec=importlib.util.spec_from_file_location('timed_install_final',I/'timed_install.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.verify_wheels();m.verify_dependencies();pins=m.artifact_pins()
p=json.loads((D/'m1-codex-campaign-proposal-v11.json').read_bytes())
assert all(p['base06_installation'][k]==v for k,v in pins.items())
assert b'\r' not in (I/'products-requirements.txt').read_bytes()
assert len(p['package_pins']['files'])==m.EXPECTED_PAYLOAD_COUNT+1==984
for entry in p['execution_bundle']['files'].values():
    assert hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest()==entry['sha256']
absent()
(Q/'actual-input-verification.json').write_bytes((json.dumps({
 'status':'PASS','proposal_sha256':hashlib.sha256((D/'m1-codex-campaign-proposal-v11.json').read_bytes()).hexdigest(),
 'product_payload_count':m.EXPECTED_PAYLOAD_COUNT,'all_module_pins':len(p['execution_bundle']['files']),
 'lf_requirements_verified':True,'products_find_spec':{n:None for n in names},
 'exact_verifiers':['verify_wheels','verify_dependencies','artifact_pins'],
 'approval_created_or_consumed':False,'installation_invoked':False},indent=2)+'\n').encode())
import pytest
code=pytest.main(['-q','-p','no:cacheprovider',str(D/'test_preparation_entries.py'),'--basetemp',str(Q/'pytest-tmp'),'--junitxml',str(Q/'results.xml')])
absent();raise SystemExit(code)
'''
argv=[p['package_pins']['python'],'-I','-B','-X','utf8','-c',code,str(D),str(Q)]
began=time.monotonic()
with (Q/'stdout.txt').open('xb') as out,(Q/'stderr.txt').open('xb') as err:
    child=subprocess.Popen(argv,cwd=Q,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    result=child.wait()
proof={'exit_code':result,'duration_seconds':time.monotonic()-began,'proposal_sha256':sha(proposal),
    'inputs_before':files,'inputs_unchanged':all(sha(path)==digest for path,digest in files.items()),
    'campaign_root_absent':not (R/'campaign').exists(),
    'installation_unreserved':not any((D/'installation'/n).exists() for n in ('installation-reserved.json','installation-result.json','installation-unknown.json')),
    'no_real_approval':True,'scope':'14 real Python entry refusals; actual pinned wheel/LF/dependency verification. No product installation, provider/service/task or credentials.'}
(Q/'result.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode())
print(json.dumps({k:proof[k] for k in ('exit_code','duration_seconds','proposal_sha256','inputs_unchanged','campaign_root_absent','installation_unreserved')}))
raise SystemExit(result)
