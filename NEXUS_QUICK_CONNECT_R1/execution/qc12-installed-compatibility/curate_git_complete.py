"""Curate final composed Git/CLI proof, keeping failed antecedents separate."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = Path(json.loads((HERE / 'git-complete-allocation.json').read_text())['root'])
OUT = HERE / 'git-complete-evidence'
OUT.mkdir(exist_ok=False)
result = json.loads((ROOT / 'result.json').read_text())
assert result['payload_files'] == 1027 and not result['payload_drift'] and not result['repository_input_drift']
case = result['cases'][0]
assert case['exit_code'] == 0 and not case['signals']
assert all(not process['alive'] for process in case['processes_after'])
for name in ('result.json', 'source-pins.json', 'extra-test-pin.json', 'changes.patch', 'pytest.ini'):
    if (ROOT / name).exists():
        shutil.copyfile(ROOT / name, OUT / name)
for name in ('junit.xml', 'origins.json', 'raw.log', 'reports.jsonl', 'runner.json'):
    shutil.copyfile(ROOT / 'git-cli-composed' / name, OUT / name)
test = ROOT / 'after/tests/quick_connect/test_git_cli_integration.py'
shutil.copyfile(test, OUT / test.name)
counts = dict(tests=0, failures=0, errors=0, skipped=0)
for suite in ET.parse(OUT / 'junit.xml').getroot().iter('testsuite'):
    for key in counts:
        counts[key] += int(suite.attrib.get(key, '0'))
assert counts == dict(tests=10, failures=0, errors=0, skipped=0)
origins = json.loads((OUT / 'origins.json').read_text())
prefix = Path(r'C:/Users/jpamb/AppData/Local/Temp/nexus-qc-r1-package-t24_dnfc/venv').resolve()
assert all(Path(value).resolve().is_relative_to(prefix) for value in origins['origins'].values())
assert origins['stdin_isatty'] is False
deltas = []
for path in sorted((ROOT / 'git-cli-composed/tmp').rglob('checkpoint-delta-*.json')):
    value = json.loads(path.read_text())
    if path.name == 'checkpoint-delta-profile.json':
        assert value['paths'] == []
    else:
        assert len(value['paths']) == 6 and value['original_operation'] == 'created' and value['observed_operation'] == 'reused'
    deltas.append(value)
assert len(deltas) == 14
(OUT / 'checkpoint-deltas.json').write_text(json.dumps(deltas, indent=2), encoding='utf-8')
qualification = dict(at=datetime.now(timezone.utc).isoformat(), status='PASS_STRICT_INSTALLED_COMPOSED_GIT_CLI',
    counts=counts, source_commit='fa031697b37a1b879d855f7858f01320addf0df7',
    wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    prefix=str(prefix), own_root=str(ROOT), test_file=str(test), test_sha256=hashlib.sha256(test.read_bytes()).hexdigest(),
    installed_payload_files=1027, installed_payload_drift=[], source_drift=[], all_observed_owned_processes_exited=True,
    signals=[], provider_calls=0, ruff='PASS (default repository configuration, no source formatting)',
    proofs=[
        'Seven real local Git origin formats, including fake private URL components, supply the logical name while the physical CWD/execution root stays distinct.',
        'First short connect codex --no-chat uses exactly one controlled y confirmation, creates a bound public ID and verifies the complete canonical seven-field reference.',
        'Changing Git metadata after Finish does not rediscover Git during exact profile or ID resume.',
        'All DB snapshot tables, binding/grants/setup Test/session counts and canonical references remain unchanged during resume.',
        'Exact-profile checkpoint JSON remains unchanged. DONE ID-resume allows precisely the six Root-approved observation metadata paths with exact expected values; all other request/review/intent/receipt/private fields remain equal.',
        'Missing and conflicting origins retain a canonical unapproved review; declining creates no synthetic Test or harness check.',
        'Monorepo ancestor origin supplies the name without expanding execution/workspace root beyond the nested CWD.',
    ],
    root_review_decision='DONE selection metadata may reflect current canonical lookup; original request/review/receipt and all authority remain exact. Pending checkpoints are not covered by this whitelist.',
    antecedents='git-integration-evidence preserves original interrupted byte-oracle run and strict one-path derivative FAIL; git-final-evidence retains the eight-case run whose curation rejected the missing two fallback cases. None is relabeled as this final ten-case result.',
    limitations=['Interactive input/isatty are fixture-controlled, not real PTY or human acceptance.',
        'Git runs only on owned local repositories with hooks/templates and system/global configuration disabled; no remote Git operation.',
        'Setup inventory/version/Test/lifecycle use explicit synthetic boundaries; this is not provider, credential or native protocol qualification.',
        'A linked Git worktree is not composed here; no D12 worktree claim.',
        'D25 is limited to the initial canonical stdout privacy assertions; persistence, resume JSON privacy and telemetry were not asserted in this composed cut.',
        'No repository source/tests, installed prefix, personal environment or earlier evidence changed.'])
(OUT / 'qualification.json').write_text(json.dumps(qualification, indent=2), encoding='utf-8')
manifest = {p.relative_to(OUT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in OUT.rglob('*') if p.is_file()}
for name in ('run_git_complete.py', 'prepare_git_complete.py', 'curate_git_complete.py'):
    manifest['../' + name] = hashlib.sha256((HERE / name).read_bytes()).hexdigest()
(OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps(dict(counts=counts, qualification_sha256=manifest['qualification.json'],
    test_file=str(test), test_sha256=qualification['test_sha256'], cleanup='normal physical exits; zero signals')))
