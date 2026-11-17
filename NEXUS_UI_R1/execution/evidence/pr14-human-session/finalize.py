"""Hash only this evidence directory after both human handoffs ended."""
from pathlib import Path
import json,hashlib
here=Path(__file__).resolve().parent
for section in ('first-run','technical','second-run'):
    pins=json.loads((here/section/'manifest.json').read_text());bad=[name for name,expected in pins.items() if hashlib.sha256((here/section/name).read_bytes()).hexdigest()!=expected]
    if bad:raise RuntimeError(section+': '+','.join(bad))
manifest={p.relative_to(here).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(here.rglob('*')) if p.is_file() and '__pycache__'not in p.parts and p!=here/'manifest.json'}
(here/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps({'entries':len(manifest),'manifest_sha256':hashlib.sha256((here/'manifest.json').read_bytes()).hexdigest(),'submanifests_validated':3}))
