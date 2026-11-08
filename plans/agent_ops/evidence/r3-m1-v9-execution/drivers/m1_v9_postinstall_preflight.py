from pathlib import Path
import json,socket,time
from okto_nexus.adapters.outbound.service_manager.windows_tasks import WindowsTasks
B=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v9-preparation-t4xaqhca/draft')
P=json.loads((B/'m1-codex-campaign-proposal-v9-lf.json').read_text())
C=json.loads((B/'proposed-commands.json').read_text())
I=json.loads((B/'installation/installation-result.json').read_text())
assert I['status']=='INSTALLED_VERIFIED' and I['payload_count']==982 and I['pip_check']['returncode']==0
assert I['proposal_sha256']=='099215c658e4b16cfb69456ea1ad9a21875b45a090c439a6504b05912491d204'
assert not Path(P['paths']['campaign_root']).exists()
tasks={}
for component,v in C['tasks'].items():
    assert WindowsTasks().read(v['name']) is None
    tasks[component]={'name':v['name'],'absent':True}
with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
    s.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
    s.bind(('127.0.0.1',54913))
result={'status':'PASS','tasks':tasks,'campaign_root_absent':True,'port_probe':54913,'time':time.time()}
out=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v9-approved-execution/requirements-lf-correction/preflight-after-install.json')
with out.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
print(json.dumps(result))
