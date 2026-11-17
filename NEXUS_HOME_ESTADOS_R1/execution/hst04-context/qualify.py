"""Focused context milestone, no asset build or backend inference."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
files=['frontend/src/homeController.ts','frontend/src/hooks/useHomeOverview.ts','frontend/src/homeEntryInspection.ts',
 'frontend/src/components/home/OperationalHome.tsx','frontend/src/components/home/HomeEntryInspection.tsx',
 'frontend/tests/uiHarnessController.test.mjs','frontend/tests/uiEntryInspection.test.mjs']
deps=['frontend/src/homeTypes.ts','frontend/src/homeApi.ts','frontend/src/homeStateContracts.ts','frontend/src/homeStatePresentation.ts',
 'frontend/src/components/home/HomeHarnessCard.tsx','frontend/src/components/home/HomeContextCards.tsx','frontend/tests/homeR1Support.mjs']
def pins():return {n:dict(bytes=(REPO/n).stat().st_size,sha256=hashlib.sha256((REPO/n).read_bytes()).hexdigest()) for n in files+deps}
before=pins();records=[]
tests=['uiHarnessController','uiEntryInspection','homeR1Controller','uiBoardController','uiEntriesController']
commands=[('node',[shutil.which('rtk'),'proxy',shutil.which('node'),'--test','--test-reporter=tap',*[str(REPO/'frontend/tests'/(n+'.test.mjs')) for n in tests]],REPO),
 ('tsc',[shutil.which('rtk'),'proxy',shutil.which('npx.cmd'),'tsc','--noEmit'],REPO/'frontend')]
for label,argv,cwd in commands:
 with (HERE/(label+'.log')).open('w',encoding='utf-8') as log:
  result=subprocess.run(argv,cwd=cwd,input='',text=True,stdout=log,stderr=subprocess.STDOUT,timeout=60)
 records.append(dict(label=label,argv=argv,cwd=str(cwd),exit_code=result.returncode))
 assert result.returncode==0,(label,result.returncode)
after=pins();assert before==after
text=(HERE/'node.log').read_text();passed=int(re.search(r'# pass (\d+)',text)[1]);failed=int(re.search(r'# fail (\d+)',text)[1])
assert failed==0
report=dict(status='IMPLEMENTED_NODE_SCOPED',at=datetime.now(timezone.utc).isoformat(),tasks=['HST-020','HST-021','HST-023'],
 node_pass=passed,node_fail=failed,tsc_exit=0,commands=records,pins=before,source_files=files,dependencies=deps,source_drift=[],
 limits=['No browser, real AT or human qualification; no full-task VERIFIED claim.',
 'HTTP DTOs are controlled Node fixtures, not a real provider/backend qualification.',
 'No frontend build, App/default opt-in, paid/native or personal state changed.',
 'Browser history/focus/dirty transitions require real browser qualification.',
 'Native session/requests backend and Results rollout owned separately.'],
 behavior=['Only complete binding catalog can auto-open one known readable session; otherwise explicit choice.',
 'Full connection identity is revalidated before read-only existing viewer; display metadata excluded from target URL.',
 'Session/action pages share existing scheduler and generation fences.',
 'Related v2 pages preserve negotiated version; old cursors do not cross contracts.',
 'Root badge/summary/project components wired without new menus.'])
(HERE/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
entries=[dict(path=p.relative_to(HERE).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='manifest.json']
(HERE/'manifest.json').write_text(json.dumps(dict(files=entries),indent=2)+'\n')
print(json.dumps(dict(passed=passed,tsc=0,qualification_sha256=hashlib.sha256((HERE/'qualification.json').read_bytes()).hexdigest(),manifest_sha256=hashlib.sha256((HERE/'manifest.json').read_bytes()).hexdigest())))
