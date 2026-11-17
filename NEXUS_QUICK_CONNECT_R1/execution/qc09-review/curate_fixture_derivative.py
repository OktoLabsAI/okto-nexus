"""Retain the two authorized test-only derivative cuts and literal commands."""
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = Path(json.loads((HERE / 'derivative-allocation.json').read_text())['root'])
OUT = HERE / 'fixture-derivative'
OUT.mkdir(exist_ok=False)
for name in ('result.json', 'changes.patch', 'source-pins.json', 'pytest.ini'):
    shutil.copyfile(ROOT / name, OUT / name)
for case in ('mutable-feature', 'structured-late'):
    (OUT / case).mkdir()
    for name in ('junit.xml', 'origins.json', 'raw.log', 'reports.jsonl', 'runner.json'):
        shutil.copyfile(ROOT / case / name, OUT / case / name)
report = json.loads((OUT / 'result.json').read_text())
assert len(report['cases']) == 2 and report['payload_files'] == 1027
assert report['payload_drift'] == report['repository_input_drift'] == []
assert all(row['exit_code'] == 0 and not row['signals']
    and all(not proc['alive'] for proc in row['processes_after']) for row in report['cases'])
manifest = {p.relative_to(OUT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in OUT.rglob('*') if p.is_file()}
(OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps(dict(result_sha256=manifest['result.json'], patch_sha256=manifest['changes.patch'])))
