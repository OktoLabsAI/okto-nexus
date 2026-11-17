import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-qc36-installed-rilplc1y')
OUT = HERE / 'installed-shard-1-final-observer'
OUT.mkdir(exist_ok=True)
before = json.loads((ROOT / 'copied-tests.json').read_text(encoding='utf-8'))
before = {key.replace('\\', '/'): value for key, value in before.items()}
after = {path.relative_to(ROOT / 'tree').as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in (ROOT / 'tree/tests').rglob('*') if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.pyo')}
assert before == after
assert not (ROOT / 'tree/src').exists()
observations = [json.loads(line) for line in (ROOT / 'reports/git-hint-observation.jsonl').read_text(encoding='utf-8').splitlines()]
assert len(observations) == 2
assert [row['name'] for row in observations] == ['first', 'second']
assert all(row['source'] == row['reason'] == 'git_origin' and row['status'] == 'discovered' for row in observations)
env = json.loads((ROOT / 'reports/runner-env-precondition.json').read_text(encoding='utf-8'))
assert env['CLAUDE_CONFIG_DIR']['exists'] is False
report = {'final_core_report': '../installed-shard-1-final/qualification.json',
    'final_core_report_sha256': hashlib.sha256((HERE / 'installed-shard-1-final/qualification.json').read_bytes()).hexdigest(),
    'copied_test_files': len(before), 'copied_test_drift': [], 'copied_application_source_present': False,
    'claude_env_precondition': env, 'git_observations': observations,
    'observer_contract': 'One selected node only; calls original discover_project_name unchanged, records public result fields and duration after return, returns identical result object, restores original function in finally. No Git budget or subprocess argument changed.',
    'child_provenance': [
        {'file': 'tests/quick_connect/test_qc25_concurrency_locks.py:178', 'scope': 'App-importing lock probe uses sys.executable with -I -B, copied original unchanged. Parent executable is the exact qualified installed prefix.'},
        {'file': 'tests/quick_connect/test_git_project_hint.py', 'scope': 'Reader boundary probes run Python stdlib snippets and owned local Git, not a checkout application or provider.'}
    ],
    'limitations': ['Previous metadata-hint failure did not record its reason; these successful observations do not establish that historical cause.', 'Earlier failed/incomplete cuts stay separate and are not retroactively promoted.', 'Finite descendant sampling is not an inventory of every short-lived process; final birth/root/listener absence is scoped as documented in the core report.']}
(OUT / 'addendum.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
(OUT / 'observer-source.py').write_text((ROOT / 'guard/qc36_origin_guard.py').read_text(encoding='utf-8'), encoding='utf-8')
print(json.dumps({'copied_tests': len(before), 'drift': 0, 'addendum_sha256': hashlib.sha256((OUT / 'addendum.json').read_bytes()).hexdigest()}))
