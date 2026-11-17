"""Run only the explicitly authorized R7 diagnostic in a fenced own process."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile

parser=argparse.ArgumentParser(allow_abbrev=False)
parser.add_argument('--window',required=True,choices=['DIAG_WINDOW_OPEN'])
parser.parse_args()

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
evidence=HERE/'profile-r7-launch.json'
assert not evidence.exists(),'Preserve every prior attempt'
ready_path=REPO/'NEXUS_HOME_ESTADOS_R1/execution/package-hst-r7/READY.json'
ready=json.loads(ready_path.read_text())
assert ready['ready'] and ready['prefix_frozen']
assert hashlib.sha256(Path(ready['wheel']).read_bytes()).hexdigest()==ready['wheel_sha256']
own=Path(tempfile.mkdtemp(prefix='nexus-hst-performance-profile-r7-driver-')).resolve()
for name in ('cwd','tmp','user','roaming','local'):(own/name).mkdir()
helper_path=REPO/'NEXUS_HOME_ESTADOS_R1/execution/package-hst-r3/owned_commands.py'
spec=importlib.util.spec_from_file_location('hst_r7_profile_owned',helper_path)
owned=importlib.util.module_from_spec(spec);spec.loader.exec_module(owned)
env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','COMSPEC','SYSTEMDRIVE','PATHEXT'}}
system=Path(env.get('SYSTEMROOT','C:/Windows'))
env.update(PATH=os.pathsep.join((str(system/'System32'),str(system),str(Path(ready['python']).parent))),
    HOME=str(own/'user'),USERPROFILE=str(own/'user'),APPDATA=str(own/'roaming'),LOCALAPPDATA=str(own/'local'),
    TMP=str(own/'tmp'),TEMP=str(own/'tmp'))
command=[ready['python'],'-I','-B','-X','utf8',str(HERE/'profile-r7-worker.py')]
pins={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(ready['python']),helper_path,HERE/'profile-r7-worker.py',HERE/'guard-depth.py',HERE/'benchmark.py',ready_path]}
report=dict(command=command,own_driver=str(own),pins_before=pins,deadline_seconds=180,
    layer='DIAGNOSTIC_ONLY_NOT_P95',source_commit=ready['source_commit'],wheel_sha256=ready['wheel_sha256'])
print(json.dumps(dict(phase='DISPATCHING',own_root=str(own),command=command)),flush=True)
with (own/'profile.log').open('w',encoding='utf-8') as log:
    report['owned_command']=owned.run_owned(command,root=own,cwd=own/'cwd',env=env,log=log,timeout=180,allow_canonical=False)
report['pins_drift']=[p for p,value in pins.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=value]
report['exit_code']=report['owned_command']['exit_code']
evidence.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(report=str(evidence),result=report['owned_command'],pins_drift=report['pins_drift'])),flush=True)
print((own/'profile.log').read_text(encoding='utf-8')[-12000:],flush=True)
raise SystemExit(0 if report['owned_command']['success'] and not report['pins_drift'] else 1)
