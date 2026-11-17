"""Preserve both Git/CLI oracle antecedents without pretending full coverage."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
OUT = HERE / 'git-integration-evidence'
OUT.mkdir(exist_ok=False)
cuts = []
for label, allocation in (('original-nine-interrupted', 'git-integration-allocation.json'),
        ('strict-derivative-ten-first-case', 'git-derivative-allocation.json')):
    root = Path(json.loads((HERE / allocation).read_text())['root'])
    result = json.loads((root / 'result.json').read_text())
    assert result['payload_files'] == 1027 and not result['payload_drift'] and not result['repository_input_drift']
    case = result['cases'][0]
    assert all(not process['alive'] for process in case['processes_after'])
    dest = OUT / label
    dest.mkdir()
    for filename in ('result.json', 'source-pins.json', 'extra-test-pin.json', 'changes.patch'):
        if (root / filename).exists():
            shutil.copyfile(root / filename, dest / filename)
    for filename in ('junit.xml', 'origins.json', 'raw.log', 'reports.jsonl', 'runner.json', 'failed-call.json'):
        if (root / 'git-cli-composed' / filename).exists():
            shutil.copyfile(root / 'git-cli-composed' / filename, dest / filename)
    shutil.copyfile(root / 'after/tests/quick_connect/test_git_cli_integration.py', dest / 'test_git_cli_integration.py')
    counts = None
    if (dest / 'junit.xml').exists():
        counts = dict(tests=0, failures=0, errors=0, skipped=0)
        for suite in ET.parse(dest / 'junit.xml').getroot().iter('testsuite'):
            for key in counts:
                counts[key] += int(suite.attrib.get(key, '0'))
    for index, path in enumerate(sorted((root / 'git-cli-composed/tmp').rglob('checkpoint-delta-*.json'))):
        shutil.copyfile(path, dest / (str(index) + '-' + path.name))
    cuts.append(dict(label=label, own_root=str(root), exit_code=case['exit_code'],
        signals=case['signals'], junit_counts=counts, all_owned_processes_exited=True,
        payload_files=1027, payload_drift=[], source_drift=[]))
report = dict(at=datetime.now(timezone.utc).isoformat(), status='FAILED_STRICT_CHECKPOINT_ORACLE_REVIEW_REQUIRED',
    wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    cuts=cuts, provider_calls=0,
    findings=[
        'The first composed case proves one-confirmation short entry with real local Git, logical origin name, unchanged physical root, bound public ID and full canonical seven-field reference.',
        'Changing local origin metadata did not invoke Git during exact profile or ID resume. Canonical binding, grants, setup Test count, session count and all DB snapshot assertions passed before the checkpoint assertion.',
        'Exact profile resume changed no checkpoint JSON fields.',
        'Exact ID resume changed selection.public_connection.project_revision and reservation_ref; selection.quick_connect.name_discovery.reason/status, operation and project_name_source.',
        'The derivative allowed only created-to-reused operation metadata and correctly failed on the other five paths. No further relaxation or product change was made.',
        'The original runner interrupted active progress after a failed-call watchdog; that was not proof of a teardown hang. The derivative used pytest -x plus a whole-cut deadline and exited normally on its first failed assertion.',
    ],
    limitations=['The remaining derivative cases, including the added monorepo case, were NOT_RUN after -x.',
        'These cuts do not qualify all nine/ten scenarios or close the proposed requirement mapping.',
        'Input/isatty are controlled by fixtures; no real PTY or human acceptance claim.',
        'Private request/review/identity/authority fields were not whitelisted for mutation; full deep comparison remains strict.',
        'No repository source/tests or installed prefix was changed. Temporary data retained outside checkout.'])
(OUT / 'qualification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
manifest = {p.relative_to(OUT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in OUT.rglob('*') if p.is_file()}
(OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps(dict(qualification_sha256=manifest['qualification.json'], cuts=cuts)))
