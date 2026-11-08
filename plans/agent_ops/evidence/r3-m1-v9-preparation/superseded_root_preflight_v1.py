from pathlib import Path
import json,hashlib,socket,datetime
from okto_nexus.adapters.outbound.service_manager.windows_tasks import WindowsTasks
R=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v9-preparation-t4xaqhca')
B=R/'draft';PFILE=B/'m1-codex-campaign-proposal-v9.json'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected='0a2fe640c690da3b9fc565c4a3e247df3ce26f2b6ba4b52a51aad33fad739419'
assert sha(PFILE)==expected
P=json.loads(PFILE.read_text());entry=P['execution_bundle']['commands']
assert sha(entry['path'])==entry['sha256']
C=json.loads(Path(entry['path']).read_text())
assert P['execution_authorized'] is False and not Path(P['paths']['campaign_root']).exists()
tasks={}
for component,value in C['tasks'].items():
    observed=WindowsTasks().read(value['name']);assert observed is None
    tasks[component]={'name':value['name'],'absent':True}
with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
    probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1);probe.bind(('127.0.0.1',54913))
for entry in P['execution_bundle']['files'].values():assert sha(entry['path'])==entry['sha256'],entry['path']
for entry in P['package_pins']['packages'].values():assert sha(entry['wheel'])==entry['sha256']
assert sha(P['paths']['codex_executable'])==P['native_selection']['fingerprint'].split(':',1)[1]
result={'status':'PASS_READ_ONLY_PREPARATION_PREFLIGHT','observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'proposal_sha256':expected,'commands_sha256':C and P['execution_bundle']['commands']['sha256'],
 'tasks':tasks,'exclusive_port_probe':54913,'port_reserved':False,'campaign_root_absent':True,
 'execution_module_pins_verified':len(P['execution_bundle']['files']),'wheel_pins_verified':3,'native_pin_verified_without_execution':True,
 'provider_calls':0,'service_mutations':0,'credentials_read':0,'execution_authorized':False,
 'limit':'Task absence, fresh root and port availability must be rechecked after approval immediately before effects; this observation does not reserve the port.'}
with (R/'root-preflight.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result))
