"""Copy only sanitized derivative evidence into the review directory."""
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = Path(json.loads((HERE / 'i02-allocation.json').read_text())['root'])
OUT = HERE / 'i02-derivative'
OUT.mkdir(exist_ok=False)
for name in ('qualification.json', 'changes.patch', 'installed-before.json', 'stop.stdout.json', 'stop.stderr.txt'):
    shutil.copyfile(ROOT / name, OUT / name)
report = json.loads((OUT / 'qualification.json').read_text())
assert report['status'] == 'PASS_DERIVATIVE_ONLY' and len(report['checks']) == 22
assert report['installed_drift'] == []
assert report['cleanup']['physical_exit'] == report['cleanup']['canonical_exit'] == 0
manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file()}
(OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps(dict(report_sha256=manifest['qualification.json'], patch_sha256=manifest['changes.patch'])))
