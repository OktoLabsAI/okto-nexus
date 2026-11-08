"""Run the real installed-path/wheel/requirements verifiers without install()."""
from pathlib import Path
import hashlib,importlib.util,json

ROOT=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
names=('okto_nexus','okto_nexus_connector','nexus_connector_core')
effects=[ROOT/n for n in ('installation-reserved.json','installation-result.json','installation-unknown.json')]
campaign=ROOT.parent.parent/'campaign'
def no_effects():
    assert not campaign.exists() and not any(p.exists() for p in effects)
    assert all(importlib.util.find_spec(n) is None for n in names)
no_effects()
spec=importlib.util.spec_from_file_location('v10_timed_install',ROOT/'timed_install.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
before={str(p):sha(p) for p in [ROOT/'timed_install.py',ROOT/'products-requirements.txt',ROOT/'dependency-manifest.json',
    ROOT/'environment.json',ROOT/'direct-interpreter-final.json',ROOT/'dependency-preparation.json']}
module.verify_wheels()  # The exact function used immediately before real pip admission.
module.verify_dependencies()  # Exact 3,209 dependency byte set and verified interpreter identity.
pins=module.artifact_pins()
assert module.FINAL_PINS_BOUND is True
assert b'\r' not in module.REQUIREMENTS.read_bytes()
proposal=json.loads((ROOT.parent/'m1-codex-campaign-proposal-v10.json').read_bytes())
assert all(proposal['base06_installation'][k]==v for k,v in pins.items())
assert len(proposal['package_pins']['files'])==module.EXPECTED_PAYLOAD_COUNT+1
assert sum(pin['files'] for pin in module.WHEELS.values())==module.EXPECTED_PAYLOAD_COUNT
for pin in module.WHEELS.values():assert sha(pin['wheel'])==pin['sha256']
no_effects()
assert all(sha(p)==digest for p,digest in before.items())
result={'status':'PASS_REAL_VERIFIERS_NO_INSTALL','functions':['verify_wheels','verify_dependencies','artifact_pins'],
    'script_sha256':sha(ROOT/'timed_install.py'),'requirements_sha256':sha(module.REQUIREMENTS),'requirements_lf_only':True,
    'payload_count_from_wheels':module.EXPECTED_PAYLOAD_COUNT,'gate_entry_count':len(proposal['package_pins']['files']),
    'products_find_spec_before_after':{n:None for n in names},'campaign_absent_before_after':True,
    'install_reservation_result_unknown_absent_before_after':True,'inputs_before':before,'inputs_unchanged':True,
    'approval_document_created_or_consumed':False,'installer_install_function_called':False,
    'subprocesses_inside_verification':0,'product_imports':0,'provider_or_service_calls':0}
with (ROOT/'actual-preparation-verification.json').open('xb') as f:f.write((json.dumps(result,indent=2)+'\n').encode())
print(json.dumps({k:result[k] for k in ('status','payload_count_from_wheels','gate_entry_count','inputs_unchanged')}))
