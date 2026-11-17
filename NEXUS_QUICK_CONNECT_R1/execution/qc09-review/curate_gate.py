"""Keep the route compatibility derivative separate from I02 and shipped bytes."""
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = Path(json.loads((HERE / 'gate-allocation.json').read_text())['root'])
OUT = HERE / 'legacy-gate-derivative'
OUT.mkdir(exist_ok=False)
for name in ('result.json', 'changes.patch', 'source-pins.json', 'pytest.ini'):
    shutil.copyfile(ROOT / name, OUT / name)
shutil.copyfile(ROOT / 'after/tests/test_gate_derivative.py', OUT / 'test_gate_derivative.py')
for label in ('gate-matrix', 'canonical-shortcut', 'single-harness', 'two-harnesses'):
    (OUT / label).mkdir()
    for name in ('junit.xml', 'origins.json', 'raw.log', 'reports.jsonl', 'runner.json'):
        shutil.copyfile(ROOT / label / name, OUT / label / name)
report = json.loads((OUT / 'result.json').read_text())
assert len(report['cases']) == 4 and report['payload_files'] == 1027
assert report['payload_drift'] == report['repository_input_drift'] == []
assert all(case['exit_code'] == 0 and not case['signals']
    and all(not process['alive'] for process in case['processes_after']) for case in report['cases'])
manifest = {p.relative_to(OUT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in OUT.rglob('*') if p.is_file()}
(OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps(dict(result_sha256=manifest['result.json'], patch_sha256=manifest['changes.patch'])))
