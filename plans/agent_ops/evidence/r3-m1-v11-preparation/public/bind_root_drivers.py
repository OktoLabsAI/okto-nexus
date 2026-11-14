"""Bind frozen offline root drivers and cleanup wrapper; no campaign dispatch."""
from pathlib import Path
import json,hashlib,difflib
R=Path(__file__).resolve().parent;D=R/'draft';S=Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-v11-driver-candidate-r3pnub4c')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(S/'runtime-pins.json')=='73e9408b6bf06cdd1ee1d4f3139a52594a00c04958c993dd92f118f26c7c7292'
assert sha(S/'qualification.json')=='3a113dd8417324dfedf7e3548be7b57cff756f30065334c32adc1a21b320a963'
pins=json.loads((S/'runtime-pins.json').read_bytes());assert len(pins)==7
assert all(sha(item['path'])==item['sha256'] for item in pins.values())
P=D/'m1-codex-campaign-proposal-v11.json';p=json.loads(P.read_bytes())
assert not any(key in p['execution_bundle']['files'] for key in pins)
with (D/'preparation-history/pre-root-drivers-proposal.json').open('xb') as f:f.write(P.read_bytes())
p['execution_bundle']['files'].update(pins)
p['execution_bundle']['files']['lifecycle']['sha256']=sha(D/'m1_v11_lifecycle.py')
p['root_driver_preparation']={'status':'FROZEN_OFFLINE_COMPONENT_BOUND_NOT_EXECUTED',
    'pins':str(S/'runtime-pins.json'),'pins_sha256':sha(S/'runtime-pins.json'),
    'qualification':str(S/'qualification.json'),'qualification_sha256':sha(S/'qualification.json'),
    'actual_driver_launches':0,'cleanup_contract':'Physical owner exit proof remains required after start. A never-started installed owner requires exact NEVER_STARTED_OWNER_ABSENT plus the pinned validator re-reading invocation ledger, canonical absence, idle never-run task and unchanged install/control receipts. Both uninstall action and result bind cleanup proof bytes by SHA256.'}
P.write_bytes((json.dumps(p,indent=2,ensure_ascii=False)+'\n').encode())
before=(R/'observer-composition-initial/sources').parent.parent/'draft/preparation-history/pre-cli-runtime-manifest.json'
source=Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-v10-bundle-pscf18t5/draft/m1_v10_lifecycle.py')
(D/'diffs/lifecycle-cleanup-v11.diff').write_bytes(''.join(difflib.unified_diff(source.read_text().splitlines(True),
    (D/'m1_v11_lifecycle.py').read_text().splitlines(True),fromfile='v10/lifecycle.py',tofile='v11/lifecycle.py')).encode())
print(json.dumps({'runtime_pins':len(p['execution_bundle']['files']),'driver_pins':7,'lifecycle_sha256':sha(D/'m1_v11_lifecycle.py')}))
