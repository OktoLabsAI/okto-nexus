from pathlib import Path
import json,time,socket,hashlib
from okto_nexus.adapters.outbound.service_manager.windows_tasks import WindowsTasks
R=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v9-preparation-t4xaqhca/campaign')
C=json.loads((R.parent/'draft/proposed-commands.json').read_text())
tasks={}
for component,v in C['tasks'].items():
    assert WindowsTasks().read(v['name']) is None
    tasks[component]={'name':v['name'],'absent':True}
with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
    s.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1);s.bind(('127.0.0.1',54913))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
v={'status':'NORMAL_CLEANUP_CONFIRMED','tasks':tasks,'exclusive_port_probe_passed_not_reserved':54913,'time':time.time(),'data_preserved':R.exists(),'force_used':False,'replayed':False,'connector_started':False,'service_actions':4,'proof_sha256':sha(R/'public/cleanup-nexus.json'),'controller_sha256':sha(R/'private/controller.json'),'report_exists':(R/'deliverables/local/report.json').exists()}
with (R/'public/final-presence.json').open('x',encoding='utf-8') as f:json.dump(v,f,indent=2)
print(json.dumps(v))
