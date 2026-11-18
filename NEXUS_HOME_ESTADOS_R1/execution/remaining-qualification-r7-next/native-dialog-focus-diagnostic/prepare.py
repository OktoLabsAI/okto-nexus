"""Static browser-only diagnostic assembly; no process or allocation."""
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3];SOURCE=HERE.parent/'native-zoom-batch'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(SOURCE/'run_v2.py')=='1a95f07cd6627b71095ce324a51c3a649dd4be8ca10344314d553568416c8c9b'
runner=(SOURCE/'run_v2.py').read_text()
runner=runner.replace('Gated browser-only native zoom proof. Never starts or imports Nexus.','Gated browser-only native dialog diagnostic. Never starts or imports Nexus.')
runner=runner.replace("HERE/'prepared-bound-v2.json'","HERE/'prepared.json'").replace("gate['scope']=='NATIVE_ZOOM_BROWSER_ONLY'","gate['scope']=='NATIVE_DIALOG_FOCUS_BROWSER_ONLY'")
runner=runner.replace("'chrome://settings/appearance'","'about:blank'")
runner=runner.replace('ROOT_NATIVE_ZOOM_BROWSER_GUARD','ROOT_NATIVE_DIALOG_FOCUS')
runner=runner.replace("'native-settings-guard-v2.js'","'diagnostic.js'")
runner=runner.replace("cli('appearance-before','snapshot')","cli('before-diagnostic','snapshot')")
runner=runner.replace("result['status']=='PASS_NATIVE_200_ZOOM_GUARD'","result['status']=='DIAGNOSTIC_COMPLETED_NATIVE_DIALOG'")
runner=runner.replace('Native UI/effect did not qualify; no fallback or Nexus startup','Native dialog diagnostic incomplete; no rerun/fallback/Nexus startup')
runner=runner.replace("'NATIVE_BROWSER_ONLY_NO_NEXUS'","'NATIVE_DIALOG_FOCUS_BROWSER_ONLY'")
ast.parse(runner);(HERE/'run.py').write_text(runner)
worker=(SOURCE/'probe_server_v2.py').read_text()
start=worker.index('HTML=');end=worker.index('\ndef main',start)
worker=worker[:start]+'HTML='+repr((HERE/'probe.html').read_bytes())+'\n'+worker[end:]
worker=worker.replace('ROOT_NATIVE_ZOOM_BROWSER_GUARD','ROOT_NATIVE_DIALOG_FOCUS').replace('Static geometry calibration only; no Nexus import/process','Static native dialog focus diagnostic; no Nexus import/process')
ast.parse(worker);(HERE/'probe_server_v2.py').write_text(worker)
(HERE/'playwright-cli.json').write_bytes((SOURCE/'playwright-cli.json').read_bytes())
curator=(SOURCE/'curate_v2.py').read_text().replace("result['status']=='PASS_NATIVE_200_ZOOM_GUARD'","result['status']=='DIAGNOSTIC_COMPLETED_NATIVE_DIALOG'")
curator=curator.replace('PASS_NATIVE_BROWSER_ONLY','DIAGNOSTIC_COMPLETED_BROWSER_ONLY').replace('Native Chrome Settings zoom only; I05 application scenario NOT_RUN','Native dialog focus only; no Nexus or original-I01 cause claim')
ast.parse(curator);(HERE/'curate.py').write_text(curator)
manifest=json.loads((SOURCE/'prepared-bound-v2.json').read_text())
manifest['input_pins']={k:v for k,v in manifest['input_pins'].items()if not k.startswith(SOURCE.relative_to(REPO).as_posix())}
for name in ['run.py','probe_server_v2.py','probe.html','playwright-cli.json','diagnostic.js','curate.py','prepare.py','plan.md']:
    p=HERE/name;manifest['input_pins'][p.relative_to(REPO).as_posix()]=sha(p)
manifest['status']='NATIVE_DIALOG_FOCUS_PREPARED_NOT_EXECUTED'
manifest['scope']='Browser-only synthetic native dialog; record document focus versus browser interface; no original-I01 causal assertion'
manifest['antecedent_manifest']=dict(path=(SOURCE/'prepared-bound-v2.json').relative_to(REPO).as_posix(),sha256=sha(SOURCE/'prepared-bound-v2.json'))
(HERE/'prepared.json').write_text(json.dumps(manifest,indent=2)+'\n')
gate=dict(approved=False,approved_by=None,scope='NATIVE_DIALOG_FOCUS_BROWSER_ONLY',start_nexus=False,cut_id='hst-native-zoom-r9-dialog-focus-1',deadline_seconds=180,allow_own_containment=True,manifest_sha256=sha(HERE/'prepared.json'))
(HERE/'GATE.template.json').write_text(json.dumps(gate,indent=2)+'\n')
print(json.dumps(dict(status='PREPARED_NOT_EXECUTED',manifest_sha256=sha(HERE/'prepared.json'),files={n:sha(HERE/n)for n in ['run.py','diagnostic.js','probe_server_v2.py','curate.py']}),indent=2))
