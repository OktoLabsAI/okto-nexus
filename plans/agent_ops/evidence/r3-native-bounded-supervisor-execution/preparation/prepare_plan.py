"""Concrete offline plan only; no native scheduler, service, socket or provider."""
from pathlib import Path
import base64
import csv
import hashlib
import io
import json
import sys
import zipfile

ROOT=Path(__file__).resolve().parent
BASE=Path('C:/Users/jpamb/AppData/Local/Temp/r3-native-t19-t20-39ycaumc/plan.json')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(BASE)=='a0029067431029c8caa7b28632b2c77f8bb564efb41cfe63332e126912478d50'
old=json.loads(BASE.read_bytes());python=str(ROOT/'venv/Scripts/python.exe')
assert Path(sys.executable).resolve()==Path(python).resolve() and sys.flags.isolated
def replace(value):
    if isinstance(value,str):return value.replace(old['root'],str(ROOT)).replace(old['python'],python).replace('58973','59083')
    if isinstance(value,list):return [replace(v) for v in value]
    if isinstance(value,dict):return {k:replace(v) for k,v in value.items()}
    return value
plan=replace(old)
plan.update(revision=2,status='PREPARED_FOR_REVIEW_NOT_EXECUTED',port=59083,
    observation_timeout_seconds=180,package_reference=None,root_review_pending=True)
for phases in plan['commands'].values():
    for step in phases.values():
        assert step['argv'][:5]==[python,'-I','-B','-X','utf8']
        assert '--force' not in step['argv']
from okto_nexus.adapters.outbound.service_manager.identity import server_instance_id
from okto_nexus_connector.platform.service_identity import service_instance_id
plan['instance_ids']={'nexus':server_instance_id(Path(plan['homes']['nexus']),Path(plan['homes']['nexus'])/'nexus.db'),
    'connector':service_instance_id(Path(plan['homes']['connector']))}
plan['tasks']={name:'OktoNexus-'+('server' if name=='nexus' else name)+'-'+value.removeprefix('svc_') for name,value in plan['instance_ids'].items()}
installation=json.loads((ROOT/'final-build/installation.json').read_bytes())
pins=[]
for wheel in sorted((ROOT/'final-build/wheels').glob('*.whl')):
    pins.append({'path':str(wheel),'sha256':sha(wheel)})
    with zipfile.ZipFile(wheel) as archive:
        record=next(n for n in archive.namelist() if n.endswith('.dist-info/RECORD'))
        for rel,digest,size in csv.reader(io.StringIO(archive.read(record).decode())):
            if not digest:continue
            assert digest.startswith('sha256=') and not rel.startswith('/') and '..' not in Path(rel).parts and '.data/' not in rel
            raw=base64.urlsafe_b64decode(digest.split('=',1)[1]+'==')
            path=ROOT/'venv/Lib/site-packages'/rel
            assert sha(path)==raw.hex()
            pins.append({'path':str(path),'sha256':raw.hex()})
images=[Path(python),Path(python).with_name('pythonw.exe'),Path(sys.base_prefix)/'python.exe',Path(sys.base_prefix)/'pythonw.exe']
plan['python_images']={str(p.resolve()):sha(p) for p in images}
pins.extend({'path':p,'sha256':h} for p,h in plan['python_images'].items())
pins.extend({'path':str(ROOT/name),'sha256':sha(ROOT/name)} for name in ('run.py','runtime_support.py','final-build/installation.json','environment.json','dependency-manifest.json'))
plan['pins']=pins
plan['scope']={
    'scenarios':['SVC-T19','SVC-T20'],
    'supervision':'One native task launches one foreground parent. Native RestartOnFailure absent; parent owns one runtime through a possible Python redirector, acknowledges identity before bootstrap and retains both handles.',
    'T19':'Per host: one READY runtime initial attempt and three automatic replacements in the same parent/cycle; reserve each runtime-only fault injection, verify exact PID/birth/generation/image and unchanged native digest before TerminateProcess(retained_handle,3). Parent/launcher have query/synchronize rights only. Require actual runtime and launcher exit before next READY, backoff at least59s (1s measurement tolerance), counter1..4 without reset, then exact exhausted receipt and parent physical exit. Observe190s with no fifth attempt.',
    'T20':'Healthy normal stop must report drained plus runtime/launcher/parent physical exits, draining latch and190s without resurrection. Nexus next connect may start service but configured successful connect is not asserted; Connector missing-identity connect must refuse without start, followed by explicitly selected start for T19.',
    'cleanup':'After exhaustion normal stop must state stopped with supervisor_only/unconfirmed/not_asserted; never infer runtime work drained. Canonical uninstall must leave exact task absent and data fingerprints unchanged. Keep all runtime data. Uncertainty halts progression without force or extra start.',
    'timeouts':{'readiness_seconds':180,'lifecycle_command_timeout_seconds':45,'cli_wrapper_wait_seconds':180,
        'physical_exit_seconds':30,'quiet_seconds':190,'failure_handle_observer_seconds':7200},
    'limits':['Known injected runtime exit3 only, not arbitrary NTSTATUS','No active work/provider/login/model turn','No M1/shared installed environment mutation','No service or crash before root concrete review','Startup timeout preserved as failure, not retried or increased'],
    'product_commits':{name:value['commit'] for name,value in installation['products'].items()},
    'prior_campaign':{'plan_path':str(BASE),'plan_sha256':sha(BASE),'outcome':'Failed180s after first crash; native retries not established; preserved separately'},
    'os_matrix':'Four disposable cases each had one physical exit and no native replacement; host evidence motivated parent policy. No global Windows claim.'}
plan['selection_limits']={'canonical_cli_commands':13,'maximum_injected_ready_crashes':8,
    'maximum_automatic_replacements_expected':6,'manual_launches_between_crashes':0,'model_turns':0}
with (ROOT/'plan.json').open('x',encoding='utf-8') as f:json.dump(plan,f,indent=2);f.write('\n')
print(json.dumps({'status':plan['status'],'pins':len(pins),'tasks':plan['tasks'],'port':plan['port']}))
