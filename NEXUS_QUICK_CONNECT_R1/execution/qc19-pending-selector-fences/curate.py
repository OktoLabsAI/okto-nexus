"""Curate exact pending-selector fences and genuine operator-boundary denial."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = Path(json.loads((HERE / 'allocation.json').read_text())['root'])
OUT = HERE / 'evidence'
OUT.mkdir(exist_ok=False)
result = json.loads((ROOT / 'result.json').read_text())
assert result['payload_files'] == 1027 and result['payload_drift'] == result['repository_input_drift'] == []
case = result['cases'][0]
assert case['exit_code'] == 0 and not case['signals']
assert all(not process['alive'] for process in case['processes_after'])
for name in ('result.json', 'source-pins.json', 'extra-test-pin.json', 'pytest.ini'):
    shutil.copyfile(ROOT / name, OUT / name)
for name in ('junit.xml', 'origins.json', 'raw.log', 'reports.jsonl', 'runner.json'):
    shutil.copyfile(ROOT / 'pending-selector-fences' / name, OUT / name)
test = ROOT / 'after/tests/quick_connect/test_pending_selector_fences.py'
shutil.copyfile(test, OUT / test.name)
pin = hashlib.sha256(test.read_bytes()).hexdigest()
assert pin == json.loads((ROOT / 'extra-test-pin.json').read_text())['sha256']
counts = dict(tests=0, failures=0, errors=0, skipped=0)
for suite in ET.parse(OUT / 'junit.xml').getroot().iter('testsuite'):
    for key in counts:
        counts[key] += int(suite.attrib.get(key, '0'))
assert counts == dict(tests=4, failures=0, errors=0, skipped=0)
origins = json.loads((OUT / 'origins.json').read_text())
prefix = Path(r'C:/Users/jpamb/AppData/Local/Temp/nexus-qc-r1-package-t24_dnfc/venv').resolve()
assert all(Path(value).resolve().is_relative_to(prefix) for value in origins['origins'].values())
assert origins['stdin_isatty'] is False
qualification = dict(at=datetime.now(timezone.utc).isoformat(), status='PASS_STRICT_INSTALLED_PENDING_SELECTOR_FENCES',
    counts=counts, source_commit='fa031697b37a1b879d855f7858f01320addf0df7',
    wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    prefix=str(prefix), own_root=str(ROOT), test_file=str(test), test_sha256=pin,
    installed_payload_files=1027, installed_payload_drift=[], source_drift=[],
    all_observed_owned_processes_exited=True, signals=[], provider_calls=0,
    proofs=[
        'After a real canonical Finish committed, the fixture drops only its HTTP response. The retained profile stays finish/OUTCOME_UNKNOWN with its original setup intent.',
        'Changing harness, selecting another owned root, or changing public ID on the same retained profile each yields explicit PROFILE_CONFLICT before another Test, reservation or Finish.',
        'Every refusal preserves the pending checkpoint byte-for-byte, including all request, reviewed hash, identity and private members.',
        'All non-telemetry SQLite table row hashes remain equal across refusal and exact-profile receipt recovery, excluding last_seen_at activity fields.',
        'Exact-profile recovery uses the same original setup intent and bound seven-field reference from the persisted public registry, with original reservation ref and receipt; Test/probe/reserve/Finish counts do not increase.',
        'A genuine non-operator agent-key GET receives PERMISSION_DENIED/403 and no namespace items, canonical references, occupant IDs, reservation ref or project/provider paths.',
    ],
    authorization_scope='HTTP operator boundary only. Managed CLI uses an operator context; operators share the server namespace. No per-workspace operator ACL or cross-human isolation is invented.',
    ruff='PASS default repository configuration; no source formatting after execution',
    limitations=['Three pending-selector variants plus one authorization denial: no aggregate claim beyond these four cases.',
        'Connection setup/version/Test and lifecycle use explicit synthetic fixtures; canonical HTTP/SQLite paths and installed application modules are real.',
        'No real harness, provider/account, personal configuration, service registration, Windows login/restart/suspend or paid campaign executed.',
        'Checkpoint/DB private data remain in owned temporary folders; curated artifacts contain code, hashes, process metadata and passing test reports.',
        'No repository source/tests/docs, installed prefix, earlier evidence, Core/protocol or Git/ledger was changed.'])
(HERE / 'qualification.json').write_text(json.dumps(qualification, indent=2), encoding='utf-8')
manifest = {p.relative_to(HERE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in OUT.rglob('*') if p.is_file()}
for name in ('qualification.json', 'prepare.py', 'run.py', 'curate.py'):
    manifest[name] = hashlib.sha256((HERE / name).read_bytes()).hexdigest()
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps(dict(counts=counts, qualification_sha256=manifest['qualification.json'],
    test_file=str(test), test_sha256=pin, cleanup='normal physical exits; zero signals')))
