"""Freeze the one reviewed PID/locale counterpart. No process/allocation."""
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(HERE/'prepared-bound.json')=='a42997692daa7030ee34efbd61ca876223abcf2eaa32bcd422e599dd14ca31ce'
manifest=json.loads((HERE/'prepared-bound.json').read_text())
ready=json.loads((REPO/manifest['ready']).read_text());prefix=Path(ready['python']).parent.parent
config=prefix/'pyvenv.cfg';values=dict(line.split('=',1)for line in config.read_text().splitlines()if'='in line);home=Path(values['home '].strip())
assert home.is_absolute();base=(home/'python.exe').resolve();assert base.is_file()
manifest['status']='PREPARED_IMMUTABLE_PID_LOCALE_COUNTERPART_NOT_EXECUTED'
manifest['probe_runtime']=dict(base_executable=str(base),base_executable_sha256=sha(base),venv_config_sha256=sha(config),venv_python_sha256=sha(Path(ready['python'])))
for name in ['run_v2.py','probe_server_v2.py','curate_v2.py','prepare_variant_v2.py','bind_variant_v2.py']:
    ast.parse((HERE/name).read_text())
for name in ['native-settings-guard-v2.js','run_v2.py','probe_server_v2.py','curate_v2.py','prepare_variant_v2.py','bind_variant_v2.py','prepared-bound.json']:
    manifest['input_pins'][str((HERE/name).relative_to(REPO)).replace('\\','/')]=sha(HERE/name)
manifest['changes_only']=['Optional literal colon in real Page zoom/Zoom da página accessible name','Actual observed ready worker PID/birth/executable/ancestor proof instead of equality to the Windows venv launcher PID','Worker self metadata for prefix/base executable/root/path/hash; curator includes the proof']
path=HERE/'prepared-bound-v2.json';assert not path.exists();path.write_text(json.dumps(manifest,indent=2)+'\n')
gate=dict(approved=False,scope='NATIVE_ZOOM_BROWSER_ONLY',start_nexus=False,cut_id='hst-native-zoom-r9-browser-only-2',deadline_seconds=180,allow_own_containment=True,manifest_sha256=sha(path))
(HERE/'GATE-v2.template.json').write_text(json.dumps(gate,indent=2)+'\n')
print(json.dumps(dict(manifest_sha256=sha(path),probe_runtime=manifest['probe_runtime'],input_files=len(manifest['input_pins']),files={n:sha(HERE/n)for n in ['native-settings-guard-v2.js','run_v2.py','probe_server_v2.py','curate_v2.py']},runtime_started=False),indent=2))
