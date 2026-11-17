from pathlib import Path
import hashlib
import json
import urllib.request

here=Path(__file__).resolve().parent
root=here.parents[3]
out=root/'output/playwright/ui043-fourth-human'
control=Path(json.loads((out/'control.json').read_text())['control'])
ready=json.loads((control/'ready.json').read_text())
static=root/'src/okto_nexus/adapters/inbound/http/static'
expected={'assets/index-DXslPEEE.js':'c9c8537f3c411cbf5182e6db1f486d72247cc4943d67f969f24f84001456157e','assets/index-Ds-MK2FR.css':'f761e905e0d9642c4c7d0f96d9e0f73404012f0d69d4fead8509e6fd9130b7b7','index.html':'6c2dd0f7744b123a80e5d725055d97b422459a4e6acc24198f5afa7b0a468f56'}
assert all(hashlib.sha256((static/p).read_bytes()).hexdigest()==h for p,h in expected.items())
with urllib.request.urlopen(ready['url']+'/api/v1/home/board?workspace_id=ws&limit=10&preview=3') as r:
    board=json.load(r)['data'];status=r.status
assert status==200 and board['status']=='ready' and set(board['columns'])=={'active','needs_you','results'}
paths=['frontend/src/components/home/OperationalHome.tsx','frontend/src/components/home/HomeBoardCards.tsx','frontend/src/components/onboarding/ProjectConnectFlow.tsx','frontend/src/components/ConnectionWorkflow.tsx','frontend/src/homeController.ts','src/okto_nexus/application/home_entries.py','src/okto_nexus/adapters/outbound/sqlite/home_entries.py','src/okto_nexus/domain/home_board.py']
pins={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}
record={'status':'TECHNICAL_READINESS_ONLY_NO_HUMAN_TASK_PERFORMED','root_reported_head':'7491b691','url':ready['url'],'fixture_pid':ready['fixture_pid'],'board_http_status':status,'source_status':board['source_status'],'column_totals':{n:v['total'] for n,v in board['columns'].items()},'bundle_sha256':expected,'source_sha256':pins,'workspace_id':'ws','project_label':'Sample project','project_root':ready['identities']['project_root'],'original_authority_expiries':ready['decision_authority_times'],'original_grants':ready['original_grants'],'read_window_seconds':3600,'control':str(control),'provider_calls':0,'native_binary_calls':0}
(here/'readiness.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
cfg={'url':ready['url'],'out':out.as_posix()}
(out/'open.js').write_text((here/'open.template.js').read_text().replace('__CFG__',json.dumps(cfg)),encoding='utf-8')
print(json.dumps(record,indent=2))
