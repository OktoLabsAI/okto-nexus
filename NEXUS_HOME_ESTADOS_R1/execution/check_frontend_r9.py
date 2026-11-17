"""Check original UI source and build for the canonical-card focus regression."""
import hashlib
import importlib.util
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'package-hst-r8'))
spec = importlib.util.spec_from_file_location('r9_frontend_builder', HERE / 'package-hst-r8/package.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
ROOT = HERE.parents[1]
out = HERE / 'frontend-r9-focus'
assert not out.exists(), 'Preserve every frontend cut'
out.mkdir()
owned = Path(tempfile.mkdtemp(prefix='nexus-hst-focus-build-'))


def pins():
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for folder in ('frontend/src', 'frontend/tests')
        for path in sorted((ROOT / folder).rglob('*')) if path.is_file()}


before, steps = pins(), {}
for name, argv in (
    ('node', ['rtk', 'proxy', 'npm.cmd', 'test']),
    ('build', ['rtk', 'proxy', 'npm.cmd', 'run', 'build']),
):
    with (out / (name + '.log')).open('w', encoding='utf-8') as log:
        result = builder.run_owned(argv, root=owned, cwd=ROOT / 'frontend',
            env=builder.environment(owned), log=log, timeout=180)
    steps[name] = result
    (out / 'progress.json').write_text(json.dumps(steps, indent=2) + '\n', encoding='utf-8')
    assert result['success'], name
assert before == pins(), 'UI/test inputs changed during check'
static = ROOT / 'src/okto_nexus/adapters/inbound/http/static'
assets = {path.relative_to(static).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(static.rglob('*')) if path.is_file()}
report = {'at': datetime.now(UTC).isoformat(), 'status': 'PASS', 'original_checkout': str(ROOT),
    'steps': steps, 'input_drift': [], 'input_pins': before, 'static_assets': assets,
    'scope': 'Original Node regression plus TypeScript/Vite build after Home close publishes cached display before scheduling focus',
    'limitations': ['Actual focus regression requires a fresh R9 installed browser replay; Node is not a browser.',
        'No Python behavior, provider or performance qualification.',
        'Vite chunk warning retained; timings are diagnostic on the shared machine.']}
(out / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': report['status'], 'steps': {key: value['exit_code'] for key, value in steps.items()},
    'assets': list(assets)}))
