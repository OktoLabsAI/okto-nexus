"""Curate G02 existing installed cut, no additional execution."""
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
allocation = json.loads((HERE / 'allocation.json').read_text())
root = Path(allocation['root'])
result = json.loads((root / 'result.json').read_text())
assert result['payload_files'] == 1027 and not result['payload_drift'] and not result['repository_input_drift']
record = result['cases'][0]
assert record['exit_code'] == 0 and not record['signals']
assert all(not p['alive'] for p in record['processes_after'])
assert json.loads((root / 'g02/origins-finish.json').read_text())['bad'] == {}
tests = list(ET.parse(root / 'g02/junit.xml').iter('testcase'))
assert len(tests) == 1 and all(x.find('failure') is None and x.find('error') is None for x in tests)
evidence = HERE / 'evidence'
evidence.mkdir(exist_ok=True)
for name in ('result.json', 'payload-start.json', 'payload-end.json', 'source-pins.json'):
    shutil.copyfile(root / name, evidence / name)
for name in ('junit.xml', 'raw.log', 'reports.jsonl', 'origins.json', 'origins-finish.json', 'runner.json'):
    shutil.copyfile(root / 'g02' / name, evidence / name)
test = Path(allocation['external_test'])
shutil.copyfile(test, evidence / (test.name + '.txt'))
helper = root / 'after/tests/quick_connect/test_quick_connect_extra_scenarios.py'
shutil.copyfile(helper, evidence / (helper.name + '.txt'))
qualification = dict(status='PASS_ONE_INSTALLED_G02_SCENARIO', passed=1, failed=0,
    source_candidate='fa031697b37a1b879d855f7858f01320addf0df7',
    wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    external_test=str(test), sha256=hashlib.sha256(test.read_bytes()).hexdigest(),
    helper_sha256=hashlib.sha256(helper.read_bytes()).hexdigest(),
    proof=['Two distinct explicit auto-add reviews propose codex-2.',
        'Winner binds codex-2; old loser review rejects exact project-CAS before any new Test/Finish/identity/grant.',
        'Explicit NEW profile/intent replans codex-3; old loser hash receives REVIEW_REQUIRED with no canonical mutation/Test.',
        'Only new review hash binds codex-3; first/winner exact public references/profiles and old losing checkpoint remain unchanged.'],
    payload_files=1027, payload_drift=[], source_drift=[], installed_origins_three_families=True,
    all_owned_process_handles_exited=True, signals_used=[], stdin_pipe_closed=True,
    limits=['Synthetic inert version/Test peers only; no provider/native harness execution.',
        'Project-CAS rejection occurs before isolated namespace uniqueness; not a standalone database race proof.',
        'New intent is explicitly requested; uncertain old intent is not silently retried or superseded.',
        'Only agents.last_seen_at telemetry excluded; all other compared canonical columns retained.',
        'Five prior QC14 cases were not repeated; their artifacts remain unchanged.'])
(HERE / 'qualification.json').write_text(json.dumps(qualification, indent=2) + '\n')
manifest = {str(p.relative_to(HERE)).replace('\\', '/'):dict(bytes=p.stat().st_size,
    sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in HERE.rglob('*')
    if p.is_file() and p.name != 'manifest.json' and '__pycache__' not in p.parts}
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(dict(qualification_sha256=hashlib.sha256((HERE / 'qualification.json').read_bytes()).hexdigest(),
                     manifest_sha256=hashlib.sha256((HERE / 'manifest.json').read_bytes()).hexdigest(),
                     files=len(manifest))))
