"""Check new evidence freezes without importing or running the application."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
checked, drift = 0, []
for name, base in (
    ('browser-hst/nextcuts-capture-manifest.json', HERE / 'browser-hst'),
    ('browser-hst/remaining-final-manifest.json', HERE / 'browser-hst'),
    ('performance-hst/large-dom-r7-final/manifest.json', HERE / 'performance-hst'),
):
    manifest = json.loads((HERE / name).read_text(encoding='utf-8'))
    for item in manifest.get('entries', manifest.get('files', [])):
        target = base / item['path']
        checked += 1
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != item['sha256']:
            drift.append(str(target.relative_to(HERE)))
assert not drift, drift
print(json.dumps(dict(scope='Evidence integrity only, no application execution', files=checked, drift=drift)))
