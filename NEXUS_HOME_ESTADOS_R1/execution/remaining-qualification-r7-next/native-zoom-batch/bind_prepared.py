"""Bind static source/tool hashes only. No process, browser or app allocation."""
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
for name in ['run.py','curate.py','probe_server.py','bind_prepared.py']:ast.parse((HERE/name).read_text())
ready_path=REPO/'NEXUS_HOME_ESTADOS_R1/execution/package-hst-r9/READY.json';ready=json.loads(ready_path.read_text())
assert ready['source_commit']=='f07163ab7fd618b2ff4247ba6cdb2547b5d4e038'and ready['wheel_sha256']=='e870ea400435d5b736093990af9b56544661e205ad657bbff83f830421a3e628'
security=REPO/'NEXUS_HOME_ESTADOS_R1/execution/remaining-qualification-r7-next/security-r9-batch'
tooling=json.loads((security/'prepared-manifest.json').read_text())['browser_tooling']
assert json.loads((Path(tooling['node_modules'])/'@playwright/cli/package.json').read_text())['version']=='0.1.24'
assert json.loads((HERE/'playwright-cli.json').read_text())==tooling['browser_config']
inputs=[HERE/name for name in ['native-settings-guard.js','probe_server.py','plan.md','PREPARED.json','run.py','curate.py','playwright-cli.json','OUTER.md','bind_prepared.py']]
inputs += [security/'run.py',security/'browser_driver.py',security/'prepared-manifest.json']
inputs += [REPO/'NEXUS_HOME_ESTADOS_R1/execution/browser-hst'/name for name in ['prepare_runtime.py','containment.py']]
manifest=dict(status='PREPARED_BROWSER_ONLY_NOT_EXECUTED',source_commit=ready['source_commit'],wheel_sha256=ready['wheel_sha256'],ready=str(ready_path.relative_to(REPO)),ready_sha256=sha(ready_path),payload_manifest_sha256=sha(ready_path.parent/'evidence/payload-manifest.json'),source_pin_manifest_sha256=sha(ready_path.parent/'evidence/source-pins-after.json'),tooling=tooling,input_pins={str(path.relative_to(REPO)).replace('\\','/'):sha(path)for path in inputs},validation=dict(python_ast='PASS',node_syntax='PASS_STATIC_ONLY',runtime='NOT_RUN'))
path=HERE/'prepared-bound.json';assert not path.exists();path.write_text(json.dumps(manifest,indent=2)+'\n')
gate=dict(approved=False,scope='NATIVE_ZOOM_BROWSER_ONLY',start_nexus=False,cut_id='hst-native-zoom-r9-browser-only-1',deadline_seconds=180,allow_own_containment=True,manifest_sha256=sha(path))
(HERE/'GATE.template.json').write_text(json.dumps(gate,indent=2)+'\n')
print(json.dumps(dict(manifest_sha256=sha(path),input_files=len(inputs),tool_files=len(tooling['cli_payload_pins']),runtime_started=False),indent=2))
