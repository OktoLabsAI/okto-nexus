"""Test/build the detached UI after the asynchronous focus-restoration race correction."""
from datetime import UTC, datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'package-hst-r5'))
spec = importlib.util.spec_from_file_location('g08_builder', HERE / 'package-hst-r5/package.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
tree = Path(json.loads((HERE / 'g08-ui-worktree-allocation.json').read_text())['root'])
out = HERE / 'frontend-r6-focus-worktree'
assert not out.exists()
out.mkdir()
owned = Path(tempfile.mkdtemp(prefix='nexus-hst-ui-intent-check-'))


def pins():
    files = [p for folder in ('frontend/src', 'frontend/tests') for p in (tree / folder).rglob('*') if p.is_file()]
    return {p.relative_to(tree).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


before = pins()
steps = {}
for name, argv in [('node', ['rtk', 'proxy', 'npm.cmd', 'test']),
                   ('build', ['rtk', 'proxy', 'npm.cmd', 'run', 'build'])]:
    with (out / (name + '.log')).open('w', encoding='utf-8') as log:
        result = builder.run_owned(argv, root=owned, cwd=tree / 'frontend',
                                   env=builder.environment(owned), log=log, timeout=180)
    steps[name] = result
    (out / 'progress.json').write_text(json.dumps(steps, indent=2) + '\n', encoding='utf-8')
    assert result['success'], name
after = pins()
assert before == after, 'UI/test inputs changed during verification'
static = tree / 'src/okto_nexus/adapters/inbound/http/static'
assets = {p.relative_to(static).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in sorted(static.rglob('*')) if p.is_file()}
report = dict(at=datetime.now(UTC).isoformat(), status='PASS', worktree=str(tree),
              steps=steps, input_drift=[], input_pins=before, static_assets=assets,
              scope='Detached UI Node regression and TypeScript/Vite build; Original and installed R5 remain unchanged.',
              limitations=['Not installed/browser/human or accessibility qualification.',
                           'Vite chunk-size warning retained; build success is not a performance result.'])
(out / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(status=report['status'], steps={k: v['exit_code'] for k, v in steps.items()}, assets=list(assets))))
