"""Read-only curation of five completed installed project cases."""
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
    label = record['label']
    target = out / label
    target.mkdir(exist_ok=True)
    for name in ('junit.xml', 'raw.log', 'reports.jsonl', 'origins.json', 'origins-finish.json', 'runner.json', 'failed-call.json'):
        if (root / label / name).exists():
            shutil.copyfile(root / label / name, target / name)
    assert all(not p['alive'] for p in record['processes_after'])
    assert json.loads((root / label / 'origins-finish.json').read_text())['bad'] == {}
    nodes = list(ET.parse(root / label / 'junit.xml').iter('testcase'))
    cases.append(dict(label=label, exit_code=record['exit_code'], signals=record['signals'],
        passed=sum(x.find('failure') is None and x.find('error') is None and x.find('skipped') is None for x in nodes),
        failed=sum(x.find('failure') is not None or x.find('error') is not None for x in nodes),
        skipped=sum(x.find('skipped') is not None for x in nodes)))
test = Path(allocation['external_test'])
shutil.copyfile(test, out / (test.name + '.txt'))
helper = root / 'after/tests/quick_connect/test_quick_connect_extra_scenarios.py'
shutil.copyfile(helper, out / (helper.name + '.txt'))
passed, failed, skipped = (sum(row[key] for row in cases) for key in ('passed', 'failed', 'skipped'))
report = dict(status='PASS_FIVE_INSTALLED_SCENARIOS' if passed == 5 and not failed else 'PARTIAL_OR_FAILED',
    passed=passed, failed=failed, skipped=skipped,
    source_candidate='fa031697b37a1b879d855f7858f01320addf0df7',
    wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    external_test=str(test), sha256=hashlib.sha256(test.read_bytes()).hexdigest(), cases=cases,
    coverage=dict(C05='Two equal canonical display names shown; explicit second choice selects second workspace, no implicit first.',
        C06='Exact workspace ID disambiguates equal names in JSON without prompt.',
        C07='Discordant exact workspace/name selectors refuse PROJECT_SELECTOR_CONFLICT without input or Test.',
        C08='Explicit physical root B inside A used in request/Finish; caller CWD A and root identity retained, exact seven-field reference survives resume.',
        C16='105 metadata workspaces; selected target absent first 100 and present second page; initial and final catalog read each follow real cursor with unchanged revision/exact total, zero Test/probes in plan.'),
    isolation=dict(python_flags=['-I', '-B'], stdin_pipe_closed=True, deadline_per_cut_seconds=180,
        pytest_failfast=True, copied_product_src=False, installed_origins_three_families_start_finish=True,
        payload_files=1027, payload_drift=[], source_drift=[], owned_process_handles_exited=True,
        native_provider_invocations=0, prefix_modified=False),
    limits=['Duplicate/paged empty projects are seeded through installed SqliteWorkspaceRepo metadata only, not fabricated HTTP DTOs or execution authority.',
        'C05 interactive input/isatty fixture is scripted, not native PTY or human usability evidence.',
        'C05/C06/C07/C16 qualify selection/review only; C08 additionally exercises synthetic Test/Finish and exact resume.',
        'No real harness/provider/account, fullsuite or platform-matrix claim.',
        'Only agents.last_seen_at authentication telemetry excluded from snapshots; all other compared columns retained.',
        'Physical B is precreated explicitly; logical labels are not directory creation instructions.'])
(HERE / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n')
manifest = {str(p.relative_to(HERE)).replace('\\', '/'):dict(bytes=p.stat().st_size,
    sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in HERE.rglob('*')
    if p.is_file() and p.name != 'manifest.json' and '__pycache__' not in p.parts}
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(dict(passed=passed, failed=failed, skipped=skipped,
    qualification_sha256=hashlib.sha256((HERE / 'qualification.json').read_bytes()).hexdigest(),
    manifest_sha256=hashlib.sha256((HERE / 'manifest.json').read_bytes()).hexdigest(), files=len(manifest))))
