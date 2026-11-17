"""Pin curated public evidence, excluding synthetic-secret databases/profiles."""
import hashlib
import json
from pathlib import Path
import re
import shutil

here=Path(__file__).resolve().parent
root=Path(json.loads((here/'allocation.json').read_text())['root'])
for name in ['payload-before.json','payload-after.json','source-before.json','fixture.log']:
    shutil.copyfile(root/name,here/'evidence'/name)
shutil.copyfile(root/'helpers/protocol_fixture.py',here/'evidence/protocol_fixture.py.txt')
patterns=[r'Bearer [A-Za-z0-9_.-]{15,}',r'''(?i)(?:api[_-]?key|access[_-]?token|secret|cookie)\s*[:=]\s*["'][A-Za-z0-9_.-]{20,}''']
findings=[]
for path in here.rglob('*'):
    if path.is_file() and path.suffix in ['.json','.log','.md','.txt','.py','.js']:
        text=path.read_text(encoding='utf-8',errors='replace')
        if any(re.search(pattern,text) for pattern in patterns):
            findings.append(str(path.relative_to(here)))
assert not findings, findings
entries=[]
for path in sorted(here.rglob('*')):
    if path.is_file() and path.name!='manifest.json' and '__pycache__' not in path.parts:
        entries.append(dict(path=path.relative_to(here).as_posix(),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
manifest=dict(files=entries,secret_value_pattern_hits=findings)
(here/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
mismatches=[entry['path'] for entry in entries if hashlib.sha256((here/entry['path']).read_bytes()).hexdigest()!=entry['sha256']]
assert not mismatches
print(json.dumps(dict(entries=len(entries),mismatches=mismatches,qualification_sha256=hashlib.sha256((here/'qualification.json').read_bytes()).hexdigest(),manifest_sha256=hashlib.sha256((here/'manifest.json').read_bytes()).hexdigest())))
