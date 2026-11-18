"""Retained failed-cut review only: no application/browser/process launches."""
import hashlib
import importlib.util
import json
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-hst-browser-ep6xkztn')
OUTPUT = BASE / 'runs/hst-security-r9-s2-observed-reader-v2/post-cut-review'
assert not OUTPUT.exists()
data = json.loads((ROOT / 'security-run.private.json').read_text())
variant = json.loads((ROOT / 'reader-variant-after.json').read_text())
assert variant['unchanged'] is True
survivors = []
for record in data['known_births']:
    try:
        process = psutil.Process(record['pid'])
        if abs(process.create_time() - record['birth']) < .02:
            survivors.append({'pid': process.pid, 'same_executable': process.exe() == record['exe']})
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        pass
assert not survivors
spec = importlib.util.spec_from_file_location('s2_retained_completion_drift', BASE / 'drift.py')
drift = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drift)
comparison = drift.classify(ROOT, 'before-obs', 'after-completion', allow_observations=True)
audit_path = ROOT / 'security-control-invalid-reads.jsonl'
audit = [json.loads(line) for line in audit_path.read_text().splitlines()]
snapshot = (ROOT / 'command-completion-snapshot.private.txt').read_text(encoding='utf-8')
assert 'dialog "Canonical attention record"' in snapshot
assert 'region "Selected external completion"' in snapshot
assert 'hst-security-reported-completion' in snapshot
assert 'dialog "Activity detail"' not in snapshot
results = {name: json.loads((ROOT / (name + '-result.private.json')).read_text())
           for name in ('idle', 'completion')}
report = {
    'status': 'FAILED_BROWSER_CUT_RETAINED_READ_ONLY_DIAGNOSIS',
    'qualification_status_unchanged': 'FAIL_OR_INCONCLUSIVE_PRESERVED',
    'checks': {name: [{'id': row['id'], 'ok': row['ok']} for row in value['checks']]
               for name, value in results.items()},
    'browser_requests': {name: value['requests'] for name, value in results.items()},
    'locator_diagnosis': {
        'assertion': 'exact-observed-completion-open',
        'expected_by_test': 'dialog Activity detail',
        'actual_retained_snapshot': 'dialog Canonical attention record',
        'selected_completion_region_and_exact_reference_visible_after_failure': True,
        'cause_proven': 'Wrong dialog-name scope in the assertion; actual external inspector exists.',
        'fetch_timing_or_product_defect_claimed': False,
        'proposed_derivative': 'Use actual canonical dialog, wait for exact reference inside selected completion episode, then assert full safe source/instance/generation/workspace/sequence identity; retain failure DOM/HTTP metadata privately.',
    },
    'reader_audit': audit,
    'reader_audit_note': 'Two missing-file reads only; no invalid-JSON reads in this cut. Does not prove previous transient-write cause.',
    'variant_guard': variant,
    'source_payload_helper_guard': data['before'] == data['after'] and data['runtime_helper_guarded'],
    'retained_completion_snapshot_comparison': comparison,
    'comparison_scope': 'Read-only after-exit comparison; live run did not reach completion comparator because the browser assertion failed.',
    'physical_recheck': {'known_birth_records': len(data['known_births']), 'survivors': survivors},
    'cleanup': {'fixture': data['fixture_cleanup'], 'browser': data['browser_cleanup'],
                'listeners': data['listeners'],
                'browser_close_exit_code': next(x['exit_code'] for x in data['commands'] if x['name'] == 'close'),
                'session_closed_flags': [x['closed'] for x in data['fixture_close_observations']['sessions']],
                'close_failures': data['fixture_close_observations']['close_failures']},
    'limits': ['E13 cut remains failed despite five completion checks passing; no automatic rerun.',
               'H08 occupied-claim/slot clause remains partial.',
               'Raw rows, browser snapshot, cookie and publisher token are not copied.'],
}
OUTPUT.mkdir()
target = OUTPUT / 'review.json'
target.write_text(json.dumps(report, indent=2) + '\n')
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
(OUTPUT / 'manifest.json').write_text(json.dumps({
    'review.json': sha(target), 'curator_source_sha256': sha(Path(__file__)),
    'retained_snapshot_sha256': sha(ROOT / 'command-completion-snapshot.private.txt'),
    'reader_audit_sha256': sha(audit_path),
}, indent=2) + '\n')
print(json.dumps({'review_sha256': sha(target), 'known_birth_records': len(data['known_births']),
                  'remaining': len(survivors), 'completion_changes': len(comparison['changes']),
                  'expected_observation_errors': comparison['expected_observation_errors']}))
