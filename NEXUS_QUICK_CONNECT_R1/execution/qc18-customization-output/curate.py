"""Curate four completed installed CLI cuts; no further execution."""
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
out = HERE / 'evidence'
out.mkdir(exist_ok=True)
for name in ('result.json', 'payload-start.json', 'payload-end.json', 'source-pins.json'):
    shutil.copyfile(root / name, out / name)
cases = []
for record in result['cases']:
    case = record['label']
    target = out / case
    target.mkdir(exist_ok=True)
    for name in ('junit.xml', 'raw.log', 'reports.jsonl', 'origins.json', 'origins-finish.json', 'runner.json'):
        shutil.copyfile(root / case / name, target / name)
    assert record['exit_code'] == 0 and not record['signals']
    assert all(not p['alive'] for p in record['processes_after'])
    assert json.loads((root / case / 'origins-finish.json').read_text())['bad'] == {}
    tests = list(ET.parse(root / case / 'junit.xml').iter('testcase'))
    assert len(tests) == 1 and all(x.find('failure') is None and x.find('error') is None and x.find('skipped') is None for x in tests)
    cases.append(dict(label=case, passed=1, failed=0, exit_code=0, processes_exited=True))
assert len(cases) == 4
test = Path(allocation['external_test'])
shutil.copyfile(test, out / (test.name + '.txt'))
helper = root / 'after/tests/quick_connect/test_quick_connect_extra_scenarios.py'
shutil.copyfile(helper, out / (helper.name + '.txt'))
report = dict(status='PASS_FOUR_INSTALLED_SCENARIOS', passed=4, failed=0, skipped=0,
    source_candidate='fa031697b37a1b879d855f7858f01320addf0df7',
    wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    external_test=str(test), sha256=hashlib.sha256(test.read_bytes()).hexdigest(),
    helper_sha256=hashlib.sha256(helper.read_bytes()).hexdigest(), cases=cases,
    F21=['Effective name/harness/root customization via real main/CLI trampoline, with synthetic scripted inputs.',
        'Each produces a distinct profile, intent, review hash and reservation reference.',
        'Old request/review preserved; old profile superseded and old approval returns REVIEW_SUPERSEDED.',
        'No Test/version probe or canonical setup mutation before the only final y; one fake Test/probe and one new binding/grant/public row after.',
        'Root change uses precreated root B, retains invocation CWD A and never chdirs the caller.',
        'Two candidate families are inert own files from the existing two_harnesses fixture and published through canonical inventory refresh, not invented response DTOs.'],
    H01=['Actual human-readable stdout already contains configured bound ID and project before interactive_work callback.',
        'Technical profile name/Connection shortcut text absent at callback boundary.',
        'Callback is a spy returning sentinel 37; it never executes or submits project work.'],
    isolation=dict(python_flags=['-I', '-B'], copied_product_src=False, installed_origins_three_families_start_finish=True,
        stdin_pipe_closed=True, timeout_per_cut_seconds=180, pytest_failfast=True,
        payload_files=1027, payload_drift=[], repository_source_drift=[], owned_process_handles_exited=True,
        force_or_signals_used=False, prefix_mutated=False, provider_native_invocations=0),
    limits=['Scripted input/isatty fixture is not real PTY or human usability evidence.',
        'Synthetic version/Test peers are not live provider qualification.',
        'Only agents.last_seen_at authentication telemetry excluded from snapshots; all other compared columns retained.',
        'No fullsuite, platform matrix, installation, Git action or product/repository-test modification.',
        'Chat output ordering is observed at callback entry; no actual chat work was performed.'])
(HERE / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n')
manifest = {str(p.relative_to(HERE)).replace('\\', '/'):dict(bytes=p.stat().st_size,
    sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in HERE.rglob('*')
    if p.is_file() and p.name != 'manifest.json' and '__pycache__' not in p.parts}
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(dict(qualification_sha256=hashlib.sha256((HERE / 'qualification.json').read_bytes()).hexdigest(),
                     manifest_sha256=hashlib.sha256((HERE / 'manifest.json').read_bytes()).hexdigest(), files=len(manifest))))
