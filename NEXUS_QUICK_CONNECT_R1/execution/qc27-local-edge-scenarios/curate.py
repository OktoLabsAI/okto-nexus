"""Curate four local edge checks, keeping fixture-mechanics antecedents distinct."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
OUT = HERE / 'evidence'
OUT.mkdir(exist_ok=False)
cuts = []
for label, allocation in (('original-fixture-mechanics', 'allocation.json'), ('final-four', 'derivative-allocation.json')):
    root = Path(json.loads((HERE / allocation).read_text())['root'])
    result = json.loads((root / 'result.json').read_text())
    case = result['cases'][0]
    assert not case['signals'] and all(not process['alive'] for process in case['processes_after'])
    assert result['payload_files'] == 1027 and result['payload_drift'] == result['repository_input_drift'] == []
    dest = OUT / label
    dest.mkdir()
    for name in ('result.json', 'source-pins.json', 'extra-test-pin.json', 'pytest.ini', 'changes.patch'):
        if (root / name).exists():
            shutil.copyfile(root / name, dest / name)
    for name in ('junit.xml', 'origins.json', 'raw.log', 'reports.jsonl', 'runner.json', 'failed-call.json'):
        if (root / 'local-edge-scenarios' / name).exists():
            shutil.copyfile(root / 'local-edge-scenarios' / name, dest / name)
    test = root / 'after/tests/quick_connect/test_local_edge_scenarios.py'
    shutil.copyfile(test, dest / test.name)
    counts = dict(tests=0, failures=0, errors=0, skipped=0)
    for suite in ET.parse(dest / 'junit.xml').getroot().iter('testsuite'):
        for key in counts:
            counts[key] += int(suite.attrib.get(key, '0'))
    counts['passed'] = counts['tests'] - counts['failures'] - counts['errors'] - counts['skipped']
    origins = json.loads((dest / 'origins.json').read_text())
    prefix = Path(r'C:/Users/jpamb/AppData/Local/Temp/nexus-qc-r1-package-t24_dnfc/venv').resolve()
    assert all(Path(value).resolve().is_relative_to(prefix) for value in origins['origins'].values())
    assert origins['stdin_isatty'] is False
    cuts.append(dict(label=label, own_root=str(root), counts=counts, exit_code=case['exit_code'],
        signals=[], all_observed_owned_processes_exited=True, payload_files=1027, payload_drift=[], source_drift=[]))
assert cuts[-1]['counts'] == dict(tests=4, failures=0, errors=0, skipped=0, passed=4)
root = Path(json.loads((HERE / 'derivative-allocation.json').read_text())['root'])
raw = (root / 'local-edge-scenarios/raw.log').read_text(encoding='utf-8')
diagnostic = json.loads(next(line.split('C12_DIAGNOSTIC ', 1)[1] for line in raw.splitlines() if 'C12_DIAGNOSTIC ' in line))
assert diagnostic['code'] == 'CONFIG_ERROR'
cases = {path.resolve() for path in (root / 'local-edge-scenarios/tmp').glob('pytest-of-*/pytest-*/test_c14*')}
assert len(cases) == 1
case_root = cases.pop()
target_a, target_b, link = case_root / 'workspace', case_root / 'target-b', case_root / 'project-link'
assert target_a.resolve().is_relative_to(case_root) and target_b.resolve().is_relative_to(case_root)
assert link.is_junction() and link.resolve(strict=True) == target_b.resolve(strict=True)
assert (target_a / 'keep-a.txt').read_bytes() == b'owned A data'
assert (target_b / 'keep-b.txt').read_bytes() == b'owned B data'
marker_proof = dict(case_root=str(case_root), target_a=str(target_a), target_b=str(target_b), link=str(link),
    link_is_junction=True, final_link_target=str(link.resolve()),
    target_a_marker_sha256=hashlib.sha256((target_a / 'keep-a.txt').read_bytes()).hexdigest(),
    target_b_marker_sha256=hashlib.sha256((target_b / 'keep-b.txt').read_bytes()).hexdigest(), targets_preserved=True)
(OUT / 'junction-data-preservation.json').write_text(json.dumps(marker_proof, indent=2))
test = root / 'after/tests/quick_connect/test_local_edge_scenarios.py'
pin = hashlib.sha256(test.read_bytes()).hexdigest()
assert pin == json.loads((root / 'extra-test-pin.json').read_text())['sha256']
qualification = dict(at=datetime.now(timezone.utc).isoformat(), status='PASS_STRICT_INSTALLED_FOUR_LOCAL_EDGES',
    cuts=cuts, source_commit='fa031697b37a1b879d855f7858f01320addf0df7',
    wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    test_file=str(test), test_sha256=pin, provider_calls=0,
    c12=dict(diagnostic=diagnostic, diagnostic_specificity='generic', structured_refusal=True,
        resolver_or_daemon_called=False, home_fallback=False,
        scope='Controlled Path.cwd port returns an owned directory removed before validation. The active Windows CWD was never removed.'),
    c14='A real Windows junction changed from owned A to owned B after review; old approval with --project link was refused before reserve/Test/Finish, pending review bytes stayed exact and both target markers remain intact.',
    f13='Canonical CAS disabled the endpoint and revoked its existing grants. Explicit addition with its occupied ID was refused; exact-profile resume did not report connected, and ID/full reference/disabled state/grants stayed unchanged.',
    h09='An actual installed Python -I -B echo child returned the product resume_argv JSON byte-for-byte, including spaces/Unicode/metacharacters, with shell=False. The injected-looking marker was absent and no application/harness executable was called.',
    antecedents=['Original cut: C12 and F13 PASS; C14 SKIP was caused by a fixture cmd.exe forward-slash argv0 spelling, not host incapability.',
        'Separate owned junction probes preserve syntax failure and normalized-native-path success, without deleting target data.',
        'Original H09 failed before echo process creation because subprocess.run was incorrectly given both stdin and input; derivative uses input=b\'\' (implicit closed PIPE).',
        'Only those fixture mechanics and hidden-window creation flags changed; product/source/test expectations did not weaken.'],
    ruff='PASS default repository configuration', all_observed_owned_processes_exited=True, signals=[],
    installed_payload_files=1027, installed_payload_drift=[], source_drift=[],
    limitations=['C12 is a controlled captured-path race, not removal of a live Windows process CWD. Its generic message is recorded without inventing a runtime bug.',
        'Fixture setup/version/Test/lifecycle are synthetic; canonical HTTP/SQLite and installed application code are real.',
        'The junction command uses only structural own paths; metacharacter data is passed exclusively to Python as argv with shell=False, never to a renderer or shell.',
        'No repository source/tests/docs, installed prefix, Core/protocol, personal account/provider, Git/ledger, Windows session or earlier evidence changed.'])
(HERE / 'qualification.json').write_text(json.dumps(qualification, indent=2), encoding='utf-8')
manifest = {p.relative_to(HERE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.rglob('*') if p.is_file()}
for name in ('qualification.json', 'prepare.py', 'run.py', 'prepare_derivative.py', 'run_derivative.py',
        'junction-probe.json', 'junction-probe-normalized.json', 'junction_probe.py', 'junction_probe_normalized.py', 'curate.py'):
    manifest[name] = hashlib.sha256((HERE / name).read_bytes()).hexdigest()
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2))
print(json.dumps(dict(counts=cuts[-1]['counts'], qualification_sha256=manifest['qualification.json'],
    test_file=str(test), test_sha256=pin, c12_code=diagnostic['code'], cleanup='normal physical exits; zero signals')))
