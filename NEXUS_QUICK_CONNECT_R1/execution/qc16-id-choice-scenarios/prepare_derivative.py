"""Correct only the technical-version-check oracle; keep product bytes fixed."""
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
previous = Path(json.loads((HERE / 'allocation.json').read_text())['root'])
root = Path(tempfile.mkdtemp(prefix='nexus-qc16-id-choices-final-')).resolve()
shutil.copytree(previous / 'after', root / 'after', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for name in ('source-pins.json', 'pytest.ini'):
    shutil.copyfile(previous / name, root / name)
test = root / 'after/tests/quick_connect/test_id_choice_scenarios.py'
before = test.read_text()
needle = '    assert len(c.t.turns) == len(c.t.probes) == 2'
assert before.count(needle) == 1
after = before.replace(needle, '''    assert len(c.t.turns) == 2
    assert pending['version_check_required'] is False
    assert len(c.t.probes) == 1  # The same installation is already technically qualified.''')
test.write_text(after, encoding='utf-8', newline='\n')
(root / 'changes.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
    fromfile='original/test_id_choice_scenarios.py', tofile='reviewed/test_id_choice_scenarios.py')), encoding='utf-8')
(root / 'extra-test-pin.json').write_text(json.dumps(dict(test_file=str(test),
    sha256=hashlib.sha256(test.read_bytes()).hexdigest(), scenarios=9), indent=2), encoding='utf-8')
(HERE / 'derivative-allocation.json').write_text(json.dumps(dict(root=str(root)), indent=2), encoding='utf-8')
runner = (HERE / 'run.py').read_text()
runner = runner.replace("HERE/'allocation.json'", "HERE/'derivative-allocation.json'")
(HERE / 'run_derivative.py').write_text(runner, encoding='utf-8')
print(json.dumps(dict(root=str(root), test_sha256=hashlib.sha256(test.read_bytes()).hexdigest())))
