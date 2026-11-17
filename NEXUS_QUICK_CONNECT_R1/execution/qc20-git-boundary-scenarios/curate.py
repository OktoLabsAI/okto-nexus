"""Curate existing installed Git-boundary cuts only."""
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
    for name in ('junit.xml', 'raw.log', 'reports.jsonl', 'origins.json', 'origins-finish.json', 'runner.json', 'failed-call.json'):
        if (root / case / name).exists():
            shutil.copyfile(root / case / name, target / name)
    assert all(not p['alive'] for p in record['processes_after'])
    assert json.loads((root / case / 'origins-finish.json').read_text())['bad'] == {}
    tests = list(ET.parse(root / case / 'junit.xml').iter('testcase'))
    cases.append(dict(label=case, exit_code=record['exit_code'],
        passed=sum(x.find('failure') is None and x.find('error') is None and x.find('skipped') is None for x in tests),
        failed=sum(x.find('failure') is not None or x.find('error') is not None for x in tests),
        skipped=sum(x.find('skipped') is not None for x in tests), signals=record['signals']))
test = Path(allocation['external_test'])
shutil.copyfile(test, out / (test.name + '.txt'))
helper = root / 'after/tests/quick_connect/test_quick_connect_extra_scenarios.py'
shutil.copyfile(helper, out / (helper.name + '.txt'))
passed, failed, skipped = (sum(r[key] for r in cases) for key in ('passed', 'failed', 'skipped'))
report = dict(status='PASS_EIGHT_INSTALLED_SCENARIOS' if passed == 8 and not failed else 'PARTIAL_OR_FAILED',
    passed=passed, failed=failed, skipped=skipped,
    source_candidate='fa031697b37a1b879d855f7858f01320addf0df7',
    wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    external_test=str(test), sha256=hashlib.sha256(test.read_bytes()).hexdigest(), cases=cases,
    coverage=dict(D08='PATH empty: directory/git_unavailable fallback, no Test.',
        D09='Actual nonrepository: directory/not_a_repository fallback, no Test.',
        D11='Malformed origin containing synthetic PRIVATE marker: origin_invalid fallback without marker in CLI DTO; root retained.',
        D12='Real linked worktree: origin name and physical linked root retained through configure and exact seven-field resume.',
        D13='Actual extensions.worktreeConfig and worktree-specific origin with no shared origin; configure/resume exact reference.',
        D14='Nested actual repository uses inner origin; configure/resume exact root/reference.',
        D21='Own hostile GIT_DIR/GIT_WORK_TREE stripped by discovery; chosen repository wins, configure/resume unchanged.',
        D22='Project CWD and ancestor-repository PATH candidates rejected before Popen; tripwire marker absent, safe fallback.'),
    safety=dict(git_absolute_preparation='C:/Program Files/Git/cmd/git.exe', git_shell=False,
        git_command_timeout_seconds=5, git_hooks_templates='own empty directories',
        git_transport='protocol.allow=never; no remote commands', global_config_changed=False,
        safe_directory_changed=False, commits='Local allow-empty synthetic identity only for linked-worktree setup.',
        stdin_pipe_closed=True, python_flags=['-I', '-B'], copied_product_src=False,
        installed_origins_three_families_start_finish=True, payload_files=1027, payload_drift=[], source_drift=[],
        owned_process_handles_exited=True, native_provider_invocations=0, prefix_modified=False),
    limits=['D08/D09/D11/D22 qualify discovery/review only, not a configured seven-field connection.',
        'D13 covers sole worktree origin with shared origin absent; no override-precedence claim for conflicting origins.',
        'D22 uses inert non-executable bytes plus a Popen launch-attempt marker tripwire. No hostile executable was actually launched or compiled; marker absence proves no attempted launch of these candidates.',
        'Version/Test peers synthetic and inert; Git operations are real local metadata, not live provider qualification.',
        'Input environment and directories are owned temporary fixtures; no personal Git config, safe.directory, network, credentials or installation touched.',
        'Only agents.last_seen_at telemetry excluded from canonical snapshots; all other compared columns retained.',
        'No PTY, human usability, fullsuite or platform-matrix qualification.'])
(HERE / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n')
manifest = {str(p.relative_to(HERE)).replace('\\', '/'):dict(bytes=p.stat().st_size,
    sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in HERE.rglob('*')
    if p.is_file() and p.name != 'manifest.json' and '__pycache__' not in p.parts}
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(dict(passed=passed, failed=failed, skipped=skipped,
    qualification_sha256=hashlib.sha256((HERE / 'qualification.json').read_bytes()).hexdigest(),
    manifest_sha256=hashlib.sha256((HERE / 'manifest.json').read_bytes()).hexdigest(), files=len(manifest))))
