from pathlib import Path
import argparse
import hashlib
import json

parser=argparse.ArgumentParser()
parser.add_argument('--bundle',required=True)
parser.add_argument('--sha256',required=True)
parser.add_argument('--html-sha256',required=True)
args=parser.parse_args()
here=Path(__file__).resolve().parent
root=here.parents[3]
out=root/'output/playwright/r3-harness-board'
control=Path(json.loads((out/'control.json').read_text())['control'])
ready=json.loads((control/'ready.json').read_text())
static=root/'src/okto_nexus/adapters/inbound/http/static'
expected={'index.html':args.html_sha256,'assets/'+args.bundle:args.sha256,'assets/index-Ds-MK2FR.css':'f761e905e0d9642c4c7d0f96d9e0f73404012f0d69d4fead8509e6fd9130b7b7'}
assert all(hashlib.sha256((static/p).read_bytes()).hexdigest()==h for p,h in expected.items())
sources=['frontend/src/App.tsx','frontend/src/components/home/OperationalHome.tsx','frontend/src/components/home/HomeHarnessCard.tsx','frontend/src/components/home/HomeBoardCards.tsx','frontend/src/components/home/HomeContextCards.tsx','frontend/src/components/onboarding/ProjectConnectFlow.tsx','frontend/src/projectConnectFlowModel.ts','frontend/src/homeController.ts','frontend/src/homeTypes.ts','frontend/src/homeApi.ts','src/okto_nexus/application/home_entries.py','src/okto_nexus/domain/home_harness_board.py','src/okto_nexus/domain/home_harness_blocking.py','src/okto_nexus/adapters/outbound/sqlite/home_entries.py','tests/ui_simplification/test_harness_board.py']
pins={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in sources}
pins.update({'src/okto_nexus/adapters/inbound/http/static/'+p:h for p,h in expected.items()})
(out/'runtime-pins.json').write_text(json.dumps(pins,indent=2),encoding='utf-8')
cfg={'url':ready['url'],'out':out.as_posix(),'bundle':args.bundle}
for phase in ('phase1','phase2'):
    (out/(phase+'.js')).write_text((here/(phase+'.template.js')).read_text().replace('__CFG__',json.dumps(cfg)),encoding='utf-8')
print(json.dumps({'url':ready['url'],'fixture_pid':ready['fixture_pid'],'source_pins':len(pins),'control':str(control)}))
