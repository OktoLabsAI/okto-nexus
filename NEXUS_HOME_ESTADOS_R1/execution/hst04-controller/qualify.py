"""Capture focused Node milestone without building or changing product files."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
files=['frontend/src/homeController.ts','frontend/src/hooks/useHomeOverview.ts',
 'frontend/src/homeEntryInspection.ts','frontend/src/components/home/OperationalHome.tsx',
 'frontend/src/components/home/HomeEntryInspection.tsx','frontend/tests/homeR1Support.mjs',
 'frontend/tests/uiHarnessController.test.mjs','frontend/tests/uiEntryInspection.test.mjs',
 'frontend/tests/homeR1Controller.test.mjs']
dependencies=['frontend/src/homeStateContracts.ts','frontend/src/homeTypes.ts','frontend/src/homeApi.ts']
def pins():return {n:dict(bytes=(REPO/n).stat().st_size,sha256=hashlib.sha256((REPO/n).read_bytes()).hexdigest()) for n in files+dependencies}
before=pins()
tests=['uiHarnessController','uiEntryInspection','homeR1Controller','uiBoardController','uiEntriesController']
argv=[shutil.which('rtk'),'proxy',shutil.which('node'),'--test','--test-reporter=tap',*[str(REPO/'frontend/tests'/(n+'.test.mjs')) for n in tests]]
with (HERE/'node.tap').open('w',encoding='utf-8') as log:
 result=subprocess.run(argv,cwd=REPO,input='',text=True,stdout=log,stderr=subprocess.STDOUT,timeout=30)
after=pins();assert before==after
text=(HERE/'node.tap').read_text()
assert result.returncode==0 and '# pass 67' in text and '# fail 0' in text
report=dict(status='IMPLEMENTED_NODE_SCOPED',created_at=datetime.now(timezone.utc).isoformat(),
 tasks=['HST-018','HST-019'],not_verified=['browser','F/G/J full scenarios','HST-004 J1-J8 fixtures','AT'],
 command=argv,exit_code=result.returncode,node_pass=67,node_fail=0,node_skip=0,
 tsc=dict(command='rtk proxy npx tsc --noEmit',exit_code=0,tool_output='ea98c2',scope='Recorded prior TSC after final production edits; test-only additions followed. Root will run integration TSC/build.'),
 source_files=files,dependencies=dependencies,pins=before,source_drift=[],
 changes=['semantic snapshots ignore observation metadata without ignoring facts/validity',
 'pause/order retention no longer disables exact reads',
 'context reads remain serialized and 409 rereads in place without mixed pages',
 'normal updates are notice, authentication clears all state',
 'v1 fallback and v2 typed guards/negotiation fence'],
 limits=['No browser, user, provider or real runtime execution.','No build/assets/default rollout changes.','No claim HST tasks fully VERIFIED; metadata selection work remains.'])
(HERE/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
entries=[dict(path=p.relative_to(HERE).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='manifest.json']
(HERE/'manifest.json').write_text(json.dumps(dict(files=entries),indent=2)+'\n')
print(json.dumps(dict(status=report['status'],passes=67,qualification_sha256=hashlib.sha256((HERE/'qualification.json').read_bytes()).hexdigest(),manifest_sha256=hashlib.sha256((HERE/'manifest.json').read_bytes()).hexdigest())))
