"""Freeze new I05 app preparation only; no runtime or fixture allocation."""
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
NATIVE=HERE.parent/'native-zoom-batch'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(NATIVE/'prepared-bound-v2.json')=='ec8e7cf995a348a2085f57796e8fa10ca1493b79dfb2d174f9c060bd6d3226a8'
manifest=json.loads((NATIVE/'prepared-bound-v2.json').read_text())
for name in ['prepare.py','run.py','curate.py','bind.py']:ast.parse((HERE/name).read_text())
manifest['status']='I05_APP_PREPARED_NOT_EXECUTED'
manifest['changes_only']=['New separately gated native-zoom application phase in a new own root/profile','Qualified native14 proof runs before Nexus and fresh question admission','Two small native200/CSS360 and native100/CSS360 app cases; no other scenario expansion']
for path in [HERE/name for name in ['prepare.py','run.py','curate.py','app-display.js','native100.js','plan.md','bind.py']]+[NATIVE/'prepared-bound-v2.json',NATIVE/'run_v2.py',HERE.parent/'experience-batch/builder.py',REPO/'NEXUS_HOME_ESTADOS_R1/execution/browser-hst/fixture.py',REPO/'NEXUS_HOME_ESTADOS_R1/execution/browser-hst/canonical_controls.py',REPO/'NEXUS_HOME_ESTADOS_R1/execution/browser-hst/browser_surface.py',REPO/'NEXUS_HOME_ESTADOS_R1/execution/browser-hst/peer_source.py',REPO/'NEXUS_HOME_ESTADOS_R1/execution/browser-hst/protocol_fixture.py.txt',REPO/'NEXUS_HOME_ESTADOS_R1/execution/browser-hst/curation_privacy.py']:
    manifest['input_pins'][str(path.relative_to(REPO)).replace('\\','/')]=sha(path)
manifest['scope']=dict(native_proof_before_nexus=True,cases=['native200 requested720 measuredCSS360','native100 requested360 measuredCSS360'],supervisor_seconds=300,action_seconds=180,cleanup_reserved_seconds=120,question_lease_seconds=120,peer_seconds=150,renewal=False,provider=False,browser_writes=False)
path=HERE/'prepared-app.json';assert not path.exists();path.write_text(json.dumps(manifest,indent=2)+'\n')
gate=dict(approved=False,scope='I05_APP_NATIVE_ZOOM',start_nexus=True,allow_fixture_canonical_admissions=True,cut_id='hst-native-zoom-r9-app-1',deadline_seconds=300,allow_own_containment=True,manifest_sha256=sha(path))
(HERE/'GATE.template.json').write_text(json.dumps(gate,indent=2)+'\n')
print(json.dumps(dict(status='PREPARED_NOT_EXECUTED',manifest_sha256=sha(path),input_files=len(manifest['input_pins']),files={name:sha(HERE/name)for name in ['run.py','curate.py','app-display.js','native100.js']},runtime_started=False),indent=2))
