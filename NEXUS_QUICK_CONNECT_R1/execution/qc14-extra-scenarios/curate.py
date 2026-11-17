"""Curate existing QC14 cuts; never invokes tests or changes the prefix."""
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
cuts = [('initial', 'allocation-antecedent.json'), ('cas-counterpart', 'allocation-f17-cas.json'),
        ('final-proof', 'allocation.json')]
reports = []
for label, allocation in cuts:
    value = json.loads((HERE / allocation).read_text())
    root = Path(value['root'])
    result = json.loads((root / 'result.json').read_text())
    destination = HERE / 'evidence' / label
    destination.mkdir(parents=True, exist_ok=True)
    for name in ('result.json', 'payload-start.json', 'payload-end.json', 'source-pins.json'):
        shutil.copyfile(root / name, destination / name)
    cases = []
    for row in result['cases']:
        case = row['label']
        target = destination / case
        target.mkdir(exist_ok=True)
        for name in ('junit.xml', 'raw.log', 'reports.jsonl', 'origins.json', 'origins-finish.json',
                     'runner.json', 'failed-call.json'):
            if (root / case / name).is_file():
                shutil.copyfile(root / case / name, target / name)
        xml = list(ET.parse(root / case / 'junit.xml').iter('testcase'))
        cases.append(dict(label=case, exit_code=row['exit_code'],
            passed=sum(x.find('failure') is None and x.find('error') is None and x.find('skipped') is None for x in xml),
            failed=sum(x.find('failure') is not None or x.find('error') is not None for x in xml),
            process_handles_exited=all(not p['alive'] for p in row['processes_after']), signals=row['signals']))
        assert json.loads((root / case / 'origins-finish.json').read_text())['bad'] == {}
    assert result['payload_files'] == 1027 and not result['payload_drift'] and not result['repository_input_drift']
    reports.append(dict(label=label, root=str(root), cases=cases, payload_files=1027, payload_drift=[],
                        source_drift=[], app_source_present=False))
    test = root / 'after/tests/quick_connect/test_quick_connect_extra_scenarios.py'
    shutil.copyfile(test, destination / 'test_quick_connect_extra_scenarios.py.txt')

final_test = Path(json.loads((HERE / 'allocation.json').read_text())['derivative'])
qualification = dict(status='PASS_FIVE_SCENARIOS_ACROSS_DECLARED_CUTS',
    source_candidate='fa031697b37a1b879d855f7858f01320addf0df7',
    wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    final_external_test=str(final_test), final_external_test_sha256=hashlib.sha256(final_test.read_bytes()).hexdigest(),
    coverage=dict(E03='PASS initial', H06_new='PASS initial', H06_existing='PASS initial', G13='PASS initial',
                  F17='PASS final-proof; exact project-CAS conflict, NOT isolated namespace uniqueness'),
    antecedent='Initial F17 expected HARNESS_ID_ALREADY_EXISTS but observed CONFLICT. Preserved FAIL; exact project-CAS counterpart and additional GET proof assertions run separately.',
    cuts=reports,
    safety=dict(provider_invocations=0, native_harness_invocations=0, prefix_modified=False,
        own_temporary_fixture_only=True, stdin_pipe_closed=True, child_python_flags=['-I', '-B'],
        timeout_per_cut_seconds=180, all_recorded_process_handles_exited=True,
        product_origins='All three families installed at session start and finish; no product src copied.'),
    limits=['Not a full installed regression suite.',
        'Five scenario coverage combines four initial passing cases and final F17 focal; not one five-pass final-file run.',
        'Only agents.last_seen_at is excluded from snapshots because authentication updates telemetry; all other agent columns and all other listed table columns remain compared.',
        'G13 historical own-fixture grant timestamps model expiry and do not prove expired execution is authorized.',
        'F17 winner changes canonical project proof; stale review fails before namespace INSERT. Database uniqueness in isolation is not exercised here.',
        'Fake version/Test peers are not real provider/harness qualification.',
        'No real user, Windows session events, build, installation or Git actions.'])
(HERE / 'qualification.json').write_text(json.dumps(qualification, indent=2) + '\n')
manifest = {str(p.relative_to(HERE)).replace('\\', '/'):dict(bytes=p.stat().st_size,
    sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in HERE.rglob('*')
    if p.is_file() and p.name != 'manifest.json' and '__pycache__' not in p.parts}
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(dict(qualification_sha256=hashlib.sha256((HERE / 'qualification.json').read_bytes()).hexdigest(),
                     manifest_sha256=hashlib.sha256((HERE / 'manifest.json').read_bytes()).hexdigest(),
                     manifest_files=len(manifest), final_test_sha256=qualification['final_external_test_sha256'])))
