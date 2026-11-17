"""Curate one completed installed shard, preserving literal skips/remainders."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

import psutil

HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('root',type=Path)
parser.add_argument('destination',choices=['installed-shard-0','installed-shard-1','installed-legacy'])
args=parser.parse_args()
root=args.root.resolve()
assert root.parent==Path(__import__('tempfile').gettempdir()).resolve() and root.name.startswith('nexus-qc36-installed-')
result=json.loads((root/'result.json').read_text())
out=HERE/args.destination
out.mkdir(exist_ok=True)
assert not (out/'qualification.json').exists(),'Preserve existing cuts; never overwrite a published result.'
evidence=out/'evidence';evidence.mkdir(exist_ok=True)
for name in ['copied-tests.json','source-before.json','payload-before.json','payload-after.json','result.json']:
    shutil.copyfile(root/name,evidence/name)
for path in (root/'reports').iterdir():
    if path.is_file() and path.suffix in ['.json','.jsonl','.xml','.log']:
        text=path.read_text(encoding='utf-8',errors='replace')
        text=re.sub(r'(?:nxs_|nxsept_|nxc4_|nxt4_)[A-Za-z0-9_-]+','[ephemeral-token-redacted]',text)
        (evidence/path.name).write_text(text,encoding='utf-8')
cases=ET.parse(root/'reports/tests.xml').findall('.//testcase')
counts=dict(passed=sum(not any(c.find(k) is not None for k in ['failure','error','skipped']) for c in cases),failed=sum(c.find('failure') is not None for c in cases),errors=sum(c.find('error') is not None for c in cases),skipped=sum(c.find('skipped') is not None for c in cases))
inventory=json.loads((root/'reports/inventory.json').read_text())
remaining=[]
for record in result['known_processes']:
    try:
        process=psutil.Process(record['pid'])
        if abs(process.create_time()-record['birth'])<.01:remaining.append(record)
    except psutil.NoSuchProcess:pass
root_processes=[]
curator_tree={__import__('os').getpid(),*[p.pid for p in psutil.Process().parents()]}
for process in psutil.process_iter(['pid','name','cmdline','create_time']):
    if process.pid in curator_tree:continue
    if any(str(root).lower() in str(a).lower() for a in process.info['cmdline'] or []):
        root_processes.append(dict(pid=process.pid,name=process.info['name'],birth=process.info['create_time']))
owned_pids={p['pid'] for p in remaining+root_processes}
listeners=[dict(pid=c.pid,address=list(c.laddr)) for c in psutil.net_connections(kind='tcp') if c.status=='LISTEN' and c.pid in owned_pids]
cleanup=dict(at=datetime.now(timezone.utc).isoformat(),recorded_births_remaining=remaining,own_root_processes=root_processes,owned_listeners=listeners,note='Process-tree sampling every 0.25s cannot inventory every short-lived child; only recorded births and current own-root processes/listeners are claimed absent.')
(evidence/'physical-cleanup.json').write_text(json.dumps(cleanup,indent=2)+'\n')
report=dict(status='PASS_SCOPED_INSTALLED' if result['exit_code']==0 and not inventory['not_run'] and not counts['failed'] and not counts['errors'] else 'INCOMPLETE_OR_FAIL',source_candidate='9bc4034663ca63cfee43790b4bc03c38f8bdebcc',counts=counts,selected_files=result['selected'],collected=len(inventory['collected']),finished=len(inventory['finished']),not_run=inventory['not_run'],exit_code=result['exit_code'],payload_files=result['payload_files'],payload_drift=result['payload_drift'],source_drift=result['source_drift'],cleanup=cleanup,limits=['No provider or real harness qualification.','Closed stdin PIPE; PTY tests may skip and are never promoted.','Origin guard covers parent pytest and all its loaded application/Core/Connector modules. Nested subprocess argv are unchanged; child provenance is separate, not implicitly proven by parent origins.','Test helpers copied verbatim without src; copied-tests.json pins all bytes.','Fixture data and original raw logs remain in own Temp; public text redacts ephemeral API-key token prefixes.'])
assert not remaining and not root_processes and not listeners
assert not result['payload_drift'] and not result['source_drift']
(out/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
entries=[dict(path=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='manifest.json']
(out/'manifest.json').write_text(json.dumps(dict(files=entries),indent=2)+'\n')
print(json.dumps(dict(report=str(out/'qualification.json'),status=report['status'],counts=counts,not_run=len(report['not_run']),sha256=hashlib.sha256((out/'qualification.json').read_bytes()).hexdigest(),manifest_sha256=hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest())))
