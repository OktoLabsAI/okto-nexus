"""Retain the current Node regression with exact UI/static input hashes."""
from datetime import UTC, datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('r5_builder', HERE / 'package-hst-r5/package.py')
builder = importlib.util.module_from_spec(spec)
import sys
sys.path.insert(0, str(HERE / 'package-hst-r5'))
spec.loader.exec_module(builder)
out = HERE / 'frontend-r5'
assert not out.exists(), 'Retain antecedent runs.'
out.mkdir()
owned = Path(tempfile.mkdtemp(prefix='nexus-hst-node-'))


def pins():
    files = [p for folder in ('frontend/src', 'frontend/tests', 'src/okto_nexus/adapters/inbound/http/static')
             for p in (ROOT / folder).rglob('*') if p.is_file()]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


before = pins()
with (out / 'node.log').open('w', encoding='utf-8') as log:
    result = builder.run_owned(['rtk', 'proxy', 'npm.cmd', 'test'], root=owned,
                               cwd=ROOT / 'frontend', env=builder.environment(owned),
                               log=log, timeout=180)
after = pins()
drift = [key for key in before.keys() | after.keys() if before.get(key) != after.get(key)]
report = dict(at=datetime.now(UTC).isoformat(), result=result, input_drift=drift,
              status='PASS' if result['success'] and not drift else 'FAIL',
              scope='Current frontend Node contracts only; no browser, reader or provider claim.',
              input_pins=before, current_static_bundle='assets/index-DjtzLUDc.js')
(out / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps({key: report[key] for key in ('status', 'result', 'input_drift', 'scope')}))
assert report['status'] == 'PASS'
