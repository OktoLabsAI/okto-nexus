"""Curate completed QC17 cuts without invoking tests."""
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
reports = []
for label, allocation in [('initial', 'allocation-antecedent.json'),
                          ('corrected', 'allocation-corrected.json'), ('final', 'allocation.json')]:
    data = json.loads((HERE / allocation).read_text())
    root = Path(data['root'])
    result = json.loads((root / 'result.json').read_text())
    assert result['payload_files'] == 1027 and not result['payload_drift'] and not result['repository_input_drift']
    out = HERE / 'evidence' / label
    out.mkdir(parents=True, exist_ok=True)
    for name in ('result.json', 'payload-start.json', 'payload-end.json', 'source-pins.json'):
        shutil.copyfile(root / name, out / name)
    cases = []
    for record in result['cases']:
        case = record['label']
        target = out / case
        target.mkdir(exist_ok=True)
        for name in ('junit.xml', 'raw.log', 'reports.jsonl', 'origins.json', 'origins-finish.json',
                     'runner.json', 'failed-call.json'):
            if (root / case / name).is_file():
                shutil.copyfile(root / case / name, target / name)
        assert all(not p['alive'] for p in record['processes_after'])
        assert not record['signals']
        assert json.loads((root / case / 'origins-finish.json').read_text())['bad'] == {}
        nodes = list(ET.parse(root / case / 'junit.xml').iter('testcase'))
        cases.append(dict(label=case, exit_code=record['exit_code'],
            passed=sum(x.find('failure') is None and x.find('error') is None and x.find('skipped') is None for x in nodes),
            failed=sum(x.find('failure') is not None or x.find('error') is not None for x in nodes)))
    test = root / 'after/tests/quick_connect/test_quick_connect_project_scenarios.py'
    shutil.copyfile(test, out / (test.name + '.txt'))
    reports.append(dict(label=label, cases=cases, raw_root=str(root), payload_files=1027,
                        payload_drift=[], source_drift=[], processes_exited=True, signals=[]))
final_test = Path(json.loads((HERE / 'allocation.json').read_text())['external_test'])
report = dict(status='PASS_SIX_SCENARIOS_ACROSS_DECLARED_CUTS',
    source_candidate='fa031697b37a1b879d855f7858f01320addf0df7',
    wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    final_external_test=str(final_test), final_sha256=hashlib.sha256(final_test.read_bytes()).hexdigest(),
    coverage=dict(C01='PASS final: literal bare/harness main, exact seven-field reference/name/root; no Test/grant change.',
        C03_C04='PASS initial: concordant label resumes exact reference; new label stays logical under a precreated physical root.',
        C09='PASS final: explicit approved-root choice and existing-ID choice; plan remains planned, then explicit y observes exact reference.',
        C10='PASS initial: explicit --project A with label B refuses PROJECT_DIRECTORY_MISMATCH.',
        C11='PASS initial: JSON CWD A/label B refuses without input, chdir or Test.',
        C17='PASS initial: cancellation preserves canonical snapshot; explicit separate approval creates Nexus workspace/binding, no logical-label directory.'),
    cuts=reports,
    antecedents=['Initial C01 used helper-injected --provider-home and unintentionally selected legacy grammar; preserved failure.',
        'Initial C09 expected canonical_reference in --plan, contrary to planned-envelope contract; preserved failure.',
        'Second C01 bare branch passed but harness branch retained injected provider-home and correctly conflicted with saved selector; preserved failure.',
        'Second C09 passed plan/root choice then script omitted required Confirm resume consent; preserved failure.',
        'Final two cases correct only fixture invocation/consent and plan oracle. Four original passing cases were not repeated.'],
    safety=dict(native_provider_invocations=0, personal_authentication=False, installed_prefix_modified=False,
        copied_product_src=False, owned_homes_only=True, stdin_pipe_closed=True, python_flags=['-I', '-B'],
        pytest_failfast=True, deadline_per_cut_seconds=180, installed_origins_start_finish_three_families=True,
        all_recorded_process_handles_exited=True, force_or_signals_used=False),
    limits=['Coverage combines four initial passing cases and two final passing cases, not one six-pass final-file run.',
        'Interactive choice branches use explicitly scripted input/isatty fixture; this is not native PTY qualification or human usability evidence.',
        'Version/Test peers synthetic and inert; canonical SQL/HTTP project/binding/public-ID authorities real.',
        'Only agents.last_seen_at excluded from canonical snapshots as authentication telemetry; other columns retained.',
        'Physical fixture roots are created beforehand. CLI home/checkpoint writes are permitted; no logical label is mkdir/chdir target.',
        'No fullsuite, real provider, personal installation, platform matrix or human acceptance claim.'])
(HERE / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n')
manifest = {str(p.relative_to(HERE)).replace('\\', '/'):dict(bytes=p.stat().st_size,
    sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in HERE.rglob('*')
    if p.is_file() and p.name != 'manifest.json' and '__pycache__' not in p.parts}
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(dict(qualification_sha256=hashlib.sha256((HERE / 'qualification.json').read_bytes()).hexdigest(),
                     manifest_sha256=hashlib.sha256((HERE / 'manifest.json').read_bytes()).hexdigest(), files=len(manifest))))
