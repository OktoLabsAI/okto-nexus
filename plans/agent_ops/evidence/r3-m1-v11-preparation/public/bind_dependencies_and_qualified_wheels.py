"""Bind verified dependency/wheel metadata only; never run the installer."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parent
D=ROOT/'draft'; I=D/'installation'
P=D/'m1-codex-campaign-proposal-v11.json'
Q=Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-recovery-diagnostics-installed-xtfm5o4x/public')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads(Path(p).read_bytes())
def write(path,value):path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())

assert sha(Q/'qualification.json')=='42435098b8cf73e04560935d21a300452961487b848095c986e2d6c248fa130f'
assert sha(Q/'artifact-manifest.json')=='74f12d15bf2d9463405d9da088fd0ead5ad02eab12870f9d29d3f20835e4ca10'
qualification=load(Q/'qualification.json');reference=load(Q/'package-proof-after.json')
assert qualification['status']=='INSTALLED_RECOVERY_DIAGNOSTICS_VERIFIED'
assert qualification['installed_unique_cases']==59 and qualification['errors']==qualification['failures']==qualification['skipped']==0
assert qualification['pip_check_before_after']=='PASS'
proof=load(D/'wheel-payload-pins.json')
expected={k:v for product in reference['products'].values() for k,v in product['files'].items()}
ours={str(Path(x['path']).relative_to(I/'venv/Lib/site-packages')).replace('\\','/'):x['sha256'] for x in proof['files']}
assert ours==expected
assert len(ours)==proof['product_payload_count']==reference['total_payloads']
deps=load(I/'dependency-preparation.json'); interpreter=load(I/'direct-interpreter-final.json')
assert deps['status']=='DEPENDENCIES_ONLY_READY' and not deps['products_installed']
assert interpreter['status']=='PASS' and interpreter['launcher_pid_matches_child']
assert sha(I/'venv/Scripts/python.exe')==interpreter['venv_python_sha256']==qualification['interpreter']['sha256']
history=D/'preparation-history';history.mkdir(exist_ok=True)
with (history/'pre-dependencies-proposal.json').open('xb') as f:f.write(P.read_bytes())
with (history/'timed-install-unbound.py').open('xb') as f:f.write((I/'timed_install.py').read_bytes())
source=(I/'timed_install.py').read_text(encoding='utf-8')
old='FINAL_PINS_BOUND = False  # Dependency-only target verification pending; no real approval.'
assert source.count(old)==1
source=source.replace(old,'FINAL_PINS_BOUND = True  # Qualified wheel/dependency pins only; exact real approval remains mandatory.')
(I/'timed_install.py').write_bytes(source.encode())
p=load(P)
p['package_pins']['status']='QUALIFIED_ARTIFACTS_INSTALL_REQUIRED'
python_pin={'path':str(I/'venv/Scripts/python.exe'),'sha256':interpreter['venv_python_sha256']}
assert not any(x['path']==python_pin['path'] for x in p['package_pins']['files'])
p['package_pins']['files'].append(python_pin)
p['package_pins']['expected_total_pin_count']=len(p['package_pins']['files'])
p['package_pins']['pin_count_semantics']={'product_payload_files':len(ours),'venv_interpreter_files':1,'total_entries':len(ours)+1}
p['package_pins']['qualified_reference_environment']=str(Q.parent/'venv')
for n,pin in p['package_pins']['packages'].items():
    pin['qualification_status']='QUALIFIED_ARTIFACT_NOT_INSTALLED_IN_TARGET'
    pin['qualified_reference_package']=str(Q.parent/'venv/Lib/site-packages'/n)
p['base06_installation'].update(status='ARTIFACTS_PREPARED_REQUIRES_FINAL_BUNDLE_REVIEW_AND_AUTHORIZATION',
    dependencies_prepared=True,script_sha256=sha(I/'timed_install.py'),requirements_sha256=sha(I/'products-requirements.txt'),
    dependency_manifest_sha256=sha(I/'dependency-manifest.json'),dependency_preparation=str(I/'dependency-preparation.json'),
    dependency_preparation_sha256=sha(I/'dependency-preparation.json'),
    direct_interpreter_qualification='PASS_OWN_BASE_PID_AND_VENV_PREFIX_PRODUCTS_ABSENT',
    installer_enabled=True,guard='Wheel pins qualified; no real receipt exists. Validate exact approval before any reservation, then refuse every existing/unknown reservation. No installation has executed.')
p['package_qualification_reference']={'qualification':str(Q/'qualification.json'),'sha256':sha(Q/'qualification.json'),
    'proof':str(Q/'package-proof-after.json'),'proof_sha256':sha(Q/'package-proof-after.json'),
    'installed_tests':59,'scope':'Separate reference environment only, not a product install in the campaign target.'}
p['execution_authorized']=False
p['qualification_status']='PENDING_CONTROLLER_AND_ROOT_REVIEW'
write(P,p)
sources=load(D/'entrypoint-source-map.json')
sources.setdefault('installation/timed_install.py',{'source_path':str(Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-v10-bundle-pscf18t5/draft/installation/timed_install.py'))})['sha256']=sha(I/'timed_install.py')
sources['installation/timed_install.py']['change']='fixed targets/revision10/policy/ancestry; manifest-derived qualified wheel pins; approval and replay guards unchanged'
write(D/'entrypoint-source-map.json',sources)
write(D/'dependency-and-wheel-binding.json',{'status':'REFERENCE_ARTIFACTS_BOUND_CAMPAIGN_NOT_AUTHORIZED',
    'product_payload_count':len(ours),'all_gate_entries':len(ours)+1,'wheel_map_equals_reference':True,
    'requirements_sha256':sha(I/'products-requirements.txt'),'requirements_lf_only':b'\r' not in (I/'products-requirements.txt').read_bytes(),
    'installation_script_sha256':sha(I/'timed_install.py'),'target_products_installed':False,
    'source_proposal_before':sha(history/'pre-dependencies-proposal.json'),'proposal_after':sha(P),
    'observer_pending':True,'execution_authorized':False})
print(json.dumps({'status':'REFERENCE_ARTIFACTS_BOUND','payloads':len(ours),'gate_entries':len(ours)+1,
                  'installer_sha256':sha(I/'timed_install.py')}))
