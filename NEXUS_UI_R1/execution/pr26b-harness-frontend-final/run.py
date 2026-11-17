from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess

repo = Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus')
out = repo/'NEXUS_UI_R1/execution/pr26b-harness-frontend-final'
out.mkdir(exist_ok=True)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
sources = {str(p.relative_to(repo)).replace('\\','/'):sha(p) for folder in ('frontend/src','frontend/tests') for p in (repo/folder).rglob('*') if p.is_file()}
report = {'at':datetime.now(timezone.utc).isoformat(), 'status':'IN_PROGRESS', 'source_sha256':sources, 'commands':[]}
for name, command in [('node', ['rtk','proxy','npm','test']), ('build',['rtk','proxy','npm','run','build'])]:
    started = datetime.now(timezone.utc)
    result = subprocess.run(command,cwd=repo/'frontend',stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
    (out/(name+'.log')).write_text(result.stdout,encoding='utf-8')
    value={'name':name,'command':command,'exit_code':result.returncode,'seconds':(datetime.now(timezone.utc)-started).total_seconds()}
    if name=='node':
        value['totals']={key:int(number) for key,number in re.findall(r'^.*?\b(tests|suites|pass|fail|cancelled|skipped|todo) (\d+)\s*$',result.stdout,re.M)}
    report['commands'].append(value)
    (out/'qualification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(value),flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)
drift=[name for name,value in sources.items() if not (repo/name).is_file() or sha(repo/name)!=value]
assert not drift,drift
static=repo/'src/okto_nexus/adapters/inbound/http/static'
report.update(status='PASS',source_drift=drift,static_sha256={str(p.relative_to(repo)).replace('\\','/'):sha(p) for p in static.rglob('*') if p.is_file()},limitations=['Node/SSR and TypeScript/Vite only; not browser, installed package, human usability or screen reader qualification.','Existing bundle size and SSR useLayoutEffect warnings remain in logs.'])
(out/'qualification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS','static_sha256':report['static_sha256']}),flush=True)
