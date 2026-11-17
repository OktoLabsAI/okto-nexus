"""Curate the released source-only compatibility qualification."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ROOT = Path(json.loads((HERE / 'source-validation-allocation.json').read_text())['root'])
OUT = HERE / 'source-validation'
OUT.mkdir(exist_ok=False)
for name in ('result.json', 'source-pins.json', 'pytest.ini'):
    shutil.copyfile(ROOT / name, OUT / name)
report = json.loads((ROOT / 'result.json').read_text())
counts = dict(tests=0, failures=0, errors=0, skipped=0)
for case in report['cases']:
    label = case['label']
    (OUT / label).mkdir()
    for name in ('junit.xml', 'origins.json', 'raw.log', 'reports.jsonl', 'runner.json'):
        shutil.copyfile(ROOT / label / name, OUT / label / name)
    suites = ET.parse(ROOT / label / 'junit.xml').getroot()
    for suite in suites.iter('testsuite'):
        for key in counts:
            counts[key] += int(suite.attrib.get(key, '0'))
assert counts == dict(tests=53, failures=0, errors=0, skipped=0), counts
assert report['payload_drift'] == report['repository_input_drift'] == []
assert all(case['exit_code'] == 0 and not case['signals']
    and all(not proc['alive'] for proc in case['processes_after']) for case in report['cases'])
expected = {}
i02 = Path(json.loads((HERE / 'i02-allocation.json').read_text())['root'])
gate = Path(json.loads((HERE / 'gate-allocation.json').read_text())['root'])
for relative in ('application/terminal_connection.py', 'adapters/outbound/terminal_http.py',
        'adapters/outbound/operator_client.py', 'adapters/inbound/cli/quick_connect_ids.py',
        'adapters/inbound/cli/connect.py'):
    current = REPO / 'src/okto_nexus' / relative
    reference = (gate if relative.endswith('/connect.py') else i02) / 'overlay/okto_nexus' / relative
    assert current.read_bytes() == reference.read_bytes(), relative
    expected['src/okto_nexus/' + relative] = hashlib.sha256(current.read_bytes()).hexdigest()
test = REPO / 'tests/quick_connect/test_entry_compatibility.py'
expected[test.relative_to(REPO).as_posix()] = hashlib.sha256(test.read_bytes()).hexdigest()
qualification = dict(at=datetime.now(timezone.utc).isoformat(), status='PASS_SOURCE_ONLY',
    tests=counts, scope='Five approved compatibility source files plus one new regression file.',
    source_files=expected, current_source_pin_count=741, source_drift=[],
    dependency_prefix=r'C:/Users/jpamb/AppData/Local/Temp/nexus-ui-r3-harness-pr27-gsg_twh1/venv',
    prefix_payload_files=report['payload_files'], prefix_payload_drift=[],
    owned_root=str(ROOT), all_owned_processes_exited=True, forced=False, provider_calls=0,
    limitations=['Nexus imported from current checkout/src; this is not an installed new-wheel qualification.',
        'Core and Connector imported from unchanged PR27 prefix; no personal environment or prior prefix reinstalled.',
        'Existing three HTTP/SQLite fixtures use explicit synthetic candidate/provider/lifecycle boundaries.',
        'Original legacy test files and unrelated fixtures were not edited.',
        'The earlier real old-Server proof remains a separate derivative antecedent.'])
(OUT / 'qualification.json').write_text(json.dumps(qualification, indent=2), encoding='utf-8')
manifest = {p.relative_to(OUT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in OUT.rglob('*') if p.is_file()}
(OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps(dict(tests=counts, qualification_sha256=manifest['qualification.json'],
    forced=False, prefix_drift=[])))
