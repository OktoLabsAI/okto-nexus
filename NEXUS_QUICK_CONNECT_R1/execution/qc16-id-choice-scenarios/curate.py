"""Curate the nine exact-ID choice scenarios and preserve their oracle antecedent."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
OUT = HERE / 'evidence'
OUT.mkdir(exist_ok=False)
summaries = []
for label, allocation in (('original-probe-oracle', 'allocation.json'), ('final-nine', 'derivative-allocation.json')):
    root = Path(json.loads((HERE / allocation).read_text())['root'])
    result = json.loads((root / 'result.json').read_text())
    assert result['payload_files'] == 1027 and result['payload_drift'] == result['repository_input_drift'] == []
    case = result['cases'][0]
    assert case['signals'] == [] and all(not process['alive'] for process in case['processes_after'])
    dest = OUT / label
    dest.mkdir()
    for name in ('result.json', 'source-pins.json', 'extra-test-pin.json', 'changes.patch', 'pytest.ini'):
        if (root / name).exists():
            shutil.copyfile(root / name, dest / name)
    for name in ('junit.xml', 'origins.json', 'runner.json'):
        shutil.copyfile(root / 'id-choice-scenarios' / name, dest / name)
    counts = dict(tests=0, failures=0, errors=0, skipped=0)
    for suite in ET.parse(dest / 'junit.xml').getroot().iter('testsuite'):
        for key in counts:
            counts[key] += int(suite.attrib.get(key, '0'))
    counts['passed'] = counts['tests'] - counts['failures'] - counts['errors'] - counts['skipped']
    original_reports = root / 'id-choice-scenarios/reports.jsonl'
    records = [json.loads(line) for line in original_reports.read_text().splitlines()]
    # A failed pytest object repr may contain protected ephemeral fixture members.
    # Retain the unabridged originals only in the owned temporary folder.
    sanitized = []
    for record in records:
        if 'failure' in record:
            record['failure'] = '\n'.join(record['failure'].splitlines()[:7])
        sanitized.append(record)
    (dest / 'reports.jsonl').write_text(''.join(json.dumps(record) + '\n' for record in sanitized), encoding='utf-8')
    (dest / 'raw-pins.json').write_text(json.dumps({name: hashlib.sha256((root / 'id-choice-scenarios' / name).read_bytes()).hexdigest()
        for name in ('raw.log', 'reports.jsonl')}, indent=2), encoding='utf-8')
    if label == 'final-nine':
        assert counts == dict(tests=9, failures=0, errors=0, skipped=0, passed=9), counts
        shutil.copyfile(root / 'id-choice-scenarios/raw.log', dest / 'raw.log')
        test = root / 'after/tests/quick_connect/test_id_choice_scenarios.py'
        shutil.copyfile(test, dest / test.name)
        assert hashlib.sha256(test.read_bytes()).hexdigest() == json.loads((root / 'extra-test-pin.json').read_text())['sha256']
    origins = json.loads((dest / 'origins.json').read_text())
    prefix = Path(r'C:/Users/jpamb/AppData/Local/Temp/nexus-qc-r1-package-t24_dnfc/venv').resolve()
    assert all(Path(value).resolve().is_relative_to(prefix) for value in origins['origins'].values())
    assert origins['stdin_isatty'] is False
    summaries.append(dict(label=label, counts=counts, own_root=str(root), exit_code=case['exit_code'],
        signals=[], all_observed_owned_processes_exited=True, installed_payload_files=1027,
        payload_drift=[], source_drift=[]))
final_root = Path(json.loads((HERE / 'derivative-allocation.json').read_text())['root'])
test = final_root / 'after/tests/quick_connect/test_id_choice_scenarios.py'
qualification = dict(at=datetime.now(timezone.utc).isoformat(), status='PASS_STRICT_INSTALLED_NINE_ID_CHOICES',
    source_commit='fa031697b37a1b879d855f7858f01320addf0df7',
    wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    cuts=summaries, test_file=str(test), test_sha256=hashlib.sha256(test.read_bytes()).hexdigest(),
    cases=['F03 same-family explicit r+y reuse', 'F04 requested Claude explicitly resumes actual Codex r+y',
        'F05 manual alternate ID review then exact-profile approval', 'F06 suggested alternate ID review then exact-profile approval',
        'F07 cancel truthfully reports lifecycle/canonical metadata and effects_started=None',
        'F08 explicit add never offers resume; r rejected then c', 'F11 JSON cross-family conflict without stdin',
        'F23 contradictory exact binding refused before collision menu',
        'F12 canonical reservation by another intent remains pending, with no owner/ref exposure or extra setup'],
    authority_proofs=['Seed connection full seven-field reference and effective adapter are preserved on resume.',
        'The first profile remains byte-identical in every case.',
        'Before explicit approval, all protected table rows and Test/probe counts stay unchanged.',
        'Approved alternate IDs produce distinct bindings in the same workspace while all original protected rows remain present.',
        'Pending reservation is created explicitly through the approved canonical endpoint before the refusal baseline; collision does not mutate it.',
        'Requests, setup/grant/binding/session/operation/public-ID state remain exact for refusal/cancel/reuse paths.'],
    oracle_antecedent='Original 2PASS/1FAIL is preserved: it wrongly required a second technical probe for the same already-qualified installation. The final oracle requires a second synthetic connection Test, version_check_required=False and exactly one cached technical probe.',
    ruff='PASS default repository configuration; no formatting after execution', provider_calls=0,
    all_observed_owned_processes_exited=True, signals=[],
    limitations=['Input/isatty are scripted TTY branches over a verified closed-PIPE parent; not real PTY or human acceptance.',
        'Discovery/version/Test/lifecycle boundaries are explicit synthetic fixtures; canonical HTTP/SQLite handlers and installed application modules are real.',
        'Only agents last_seen_at activity metadata is excluded from protected-row equality; all authority and identity fields remain exact.',
        'Raw failed namespace repr stays in owned Temp; curated failure reports contain only the short assertion and hashes.',
        'No repository source/tests/docs, installed prefix, personal account, provider or prior artifact was edited.'])
(HERE / 'qualification.json').write_text(json.dumps(qualification, indent=2), encoding='utf-8')
manifest = {p.relative_to(HERE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in OUT.rglob('*') if p.is_file()}
for name in ('qualification.json', 'prepare.py', 'prepare_derivative.py', 'run.py', 'run_derivative.py', 'curate.py'):
    manifest[name] = hashlib.sha256((HERE / name).read_bytes()).hexdigest()
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps(dict(counts=summaries[-1]['counts'], qualification_sha256=manifest['qualification.json'],
    test_file=str(test), test_sha256=qualification['test_sha256'], cleanup='physical exits; zero signals')))
