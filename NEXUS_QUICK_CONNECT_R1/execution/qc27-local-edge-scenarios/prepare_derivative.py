"""Correct only local fixture subprocess mechanics, preserving original outcomes."""
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
previous = Path(json.loads((HERE / 'allocation.json').read_text())['root'])
root = Path(tempfile.mkdtemp(prefix='nexus-qc27-local-edges-final-')).resolve()
shutil.copytree(previous / 'after', root / 'after', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for name in ('source-pins.json', 'pytest.ini'):
    shutil.copyfile(previous / name, root / name)
test = root / 'after/tests/quick_connect/test_local_edge_scenarios.py'
before = test.read_text()
after = before.replace("[r'C:/Windows/System32/cmd.exe', '/d'", "[str(Path('C:/Windows/System32/cmd.exe')), '/d'")
after = after.replace('cwd=own, stdin=subprocess.DEVNULL, capture_output=True, timeout=5)',
    'cwd=own, stdin=subprocess.DEVNULL, capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)')
after = after.replace("stdin=subprocess.PIPE, input=b'', capture_output=True, shell=False, timeout=10)",
    "input=b'', capture_output=True, shell=False, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)")
assert after != before
test.write_text(after, encoding='utf-8', newline='\n')
(root / 'changes.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
    fromfile='original/test_local_edge_scenarios.py', tofile='reviewed/test_local_edge_scenarios.py')), encoding='utf-8')
(root / 'extra-test-pin.json').write_text(json.dumps(dict(test_file=str(test), sha256=hashlib.sha256(test.read_bytes()).hexdigest(), scenarios=4), indent=2))
(HERE / 'derivative-allocation.json').write_text(json.dumps(dict(root=str(root)), indent=2))
runner = (HERE / 'run.py').read_text()
runner = runner.replace("HERE/'allocation.json'", "HERE/'derivative-allocation.json'")
(HERE / 'run_derivative.py').write_text(runner, encoding='utf-8')
print(json.dumps(dict(root=str(root), test_sha256=hashlib.sha256(test.read_bytes()).hexdigest(), scenarios=4)))
