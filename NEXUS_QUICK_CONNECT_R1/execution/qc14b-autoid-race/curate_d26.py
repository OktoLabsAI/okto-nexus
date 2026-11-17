"""Append D26 evidence to preserved G02 cut, no tests or installed mutations."""
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
assert json.loads((root / 'd26/origins-finish.json').read_text())['bad'] == {}
tests = list(ET.parse(root / 'd26/junit.xml').iter('testcase'))
assert len(tests) == 1 and tests[0].find('skipped') is None
assert tests[0].find('failure') is None and tests[0].find('error') is None
out = HERE / 'evidence/d26'
out.mkdir(parents=True, exist_ok=True)
for name in ('result.json', 'payload-start.json', 'payload-end.json', 'source-pins.json'):
    shutil.copyfile(root / name, out / name)
for name in ('junit.xml', 'raw.log', 'reports.jsonl', 'origins.json', 'origins-finish.json', 'runner.json'):
    shutil.copyfile(root / 'd26' / name, out / name)
test = Path(allocation['external_test'])
shutil.copyfile(test, out / (test.name + '.txt'))
report = json.loads((HERE / 'qualification-g02.json').read_text())
report.update(status='PASS_TWO_ADDITIONAL_INSTALLED_SCENARIOS', passed=2, failed=0,
    G02_antecedent='qualification-g02.json',
    D26=dict(status='PASS', external_test=str(test), sha256=hashlib.sha256(test.read_bytes()).hexdigest(),
        variant='Explicit frozen project name; no automatic Git-name inference claim.',
        proof=['Own local Git origin/HEAD changed after lost Finish response.',
            'discover_project_name forbidden during exact-profile recovery.',
            'Same request/intent/ID/name/root/selection/review/7-field reference recovered.',
            'Exact canonical commit/grants/bindings/public-ID snapshot unchanged, no repeated Test/version probe.'],
        git='Allowlisted absolute Git; shell=False/5s per command; empty hooks/templates, no system/global config, protocol.allow=never; no network/commit/hook execution.',
        source_of_git_argv_evidence='External test source and passing assertions; separate subprocess stdout transcript not recorded.',
        payload_files=1027, payload_drift=[], source_drift=[], all_recorded_processes_exited=True, signals_used=[]))
report['limits'].append('D26 explicit-name recovery variant does not qualify automatic Git-name discovery or Git network behavior.')
(HERE / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n')
manifest = {str(p.relative_to(HERE)).replace('\\', '/'):dict(bytes=p.stat().st_size,
    sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in HERE.rglob('*')
    if p.is_file() and p.name != 'manifest.json' and '__pycache__' not in p.parts}
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(dict(qualification_sha256=hashlib.sha256((HERE / 'qualification.json').read_bytes()).hexdigest(),
                     manifest_sha256=hashlib.sha256((HERE / 'manifest.json').read_bytes()).hexdigest(), files=len(manifest))))
