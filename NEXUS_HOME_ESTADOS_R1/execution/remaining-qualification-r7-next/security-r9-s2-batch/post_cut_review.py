"""Read-only retained S2 evidence review; never starts application or browser."""
import hashlib
import importlib.util
import json
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
ROOT = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-hst-browser-71o8dx8l')
OUTPUT = HERE / 'runs/hst-security-r9-s2-observed-evidence/post-cut-review'
assert not OUTPUT.exists()
data = json.loads((ROOT / 'security-run.private.json').read_text())
assert data['case'] == 'S2' and data['cut_id'] == 'hst-security-r9-s2-observed-evidence'
assert data['failure']['type'] == 'JSONDecodeError'
survivors = []
for record in data['known_births']:
    try:
        process = psutil.Process(record['pid'])
        if abs(process.create_time() - record['birth']) < .02:
            survivors.append({'pid': process.pid, 'same_executable': process.exe() == record['exe']})
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        pass
assert not survivors
spec = importlib.util.spec_from_file_location('retained_s2_drift', HERE / 'drift.py')
drift = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drift)
idle = drift.classify(ROOT, 'before-obs', 'after-idle', allow_observations=True)
controls = json.loads((ROOT / 'control/controls.json').read_text())
report = {
    'status': 'FAILED_BROWSER_CUT_RETAINED_READ_ONLY_POST_REVIEW',
    'qualification_status_unchanged': 'FAIL_OR_INCONCLUSIVE_PRESERVED',
    'browser_assertion_phases_executed': 0,
    'publication_sequences_present': [1],
    'second_publication_not_performed': not (ROOT / 'control/security-private/expected-observation-2.json').exists(),
    'retained_idle_snapshot_comparison': idle,
    'runtime_drift_comparison_was_not_reached': data['diffs'] == [],
    'control_done_retained': controls['done'],
    'parsing_diagnosis': {
        'basis': 'Retained artifacts and frozen control flow, not a captured traceback or transient file bytes',
        'file_inferred_from_control_flow': 'control/controls.json',
        'reader': 'run.py control(): json.loads(path.read_text())',
        'writer': 'fixture.py write(): Path.write_text(json.dumps(...)); called after done.add(name)',
        'observations': [
            'Owner marker and idle marker both exist; idle marker is created only after owner control returns and owner JSON is parsed.',
            'After idle marker the next JSON parser before idle.js creation is control() reading controls.json.',
            'idle.js does not exist; control JSON is valid after shutdown and done includes idle.',
            'Failure reports line 1 column 1; no transient failing bytes or traceback were retained.',
        ],
        'concurrent_write_hypothesis_not_proven': True,
        'product_failure_or_partial_write_cause_claimed': False,
    },
    'physical_recheck': {'known_birth_records': len(data['known_births']), 'survivors': survivors},
    'cleanup': {'fixture_exit_code': data['fixture_cleanup']['exit_code'],
                'fixture_status': data['fixture_cleanup']['status'],
                'browser_close_exit_code': next(x['exit_code'] for x in data['commands'] if x['name'] == 'close'),
                'forced_births': data['browser_cleanup']['forced_births'],
                'listeners_at_cleanup': data['listeners'],
                'session_closed_flags': [x['closed'] for x in data['fixture_close_observations']['sessions']],
                'close_failures': data['fixture_close_observations']['close_failures']},
    'limits': ['E13 browser assertions NOT_RUN; no reported-completion observation was published.',
               'H08 active-claim clause remains unqualified: no occupied claim/slot baseline.',
               'Post-exit idle comparison is read-only evidence, not a successful browser phase or rerun.'],
}
OUTPUT.mkdir()
target = OUTPUT / 'review.json'
target.write_text(json.dumps(report, indent=2) + '\n')
pins = {x.name: hashlib.sha256(x.read_bytes()).hexdigest() for x in (target, Path(__file__))}
(OUTPUT / 'manifest.json').write_text(json.dumps(pins, indent=2) + '\n')
print(json.dumps({'report_sha256': pins['review.json'], 'known_birth_records': len(data['known_births']),
                  'remaining': len(survivors), 'idle_changes': len(idle['changes']),
                  'idle_expected_observation_errors': idle['expected_observation_errors']}))
