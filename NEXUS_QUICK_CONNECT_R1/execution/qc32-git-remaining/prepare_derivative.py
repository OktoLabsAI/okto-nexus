"""Correct detailed-help spelling only; rerun just the unfinished two cases."""
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
previous = Path(json.loads((HERE / 'allocation.json').read_text())['root'])
root = Path(tempfile.mkdtemp(prefix='nexus-qc32-help-bare-')).resolve()
shutil.copytree(previous / 'after', root / 'after', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for name in ('source-pins.json', 'pytest.ini'):
    shutil.copyfile(previous / name, root / name)
test = root / 'after/tests/quick_connect/test_git_remaining.py'
before = test.read_text()
old = "    assert 'project-name' in capsys.readouterr().out"
new = "    help_text = capsys.readouterr().out\n    assert '[harness] [project_name]' in help_text\n    assert 'logical project name; never a directory path' in help_text"
assert before.count(old) == 1
test.write_text(before.replace(old, new), encoding='utf-8', newline='\n')
(root / 'changes.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True), test.read_text().splitlines(True),
    fromfile='original/test_git_remaining.py', tofile='reviewed/test_git_remaining.py')), encoding='utf-8')
(root / 'extra-test-pin.json').write_text(json.dumps(dict(test_file=str(test), sha256=hashlib.sha256(test.read_bytes()).hexdigest(),
    file_scenarios=8, selected_focals=2), indent=2))
(HERE / 'derivative-allocation.json').write_text(json.dumps(dict(root=str(root)), indent=2))
runner = (HERE / 'run.py').read_text()
runner = runner.replace("HERE/'allocation.json'", "HERE/'derivative-allocation.json'")
runner = runner.replace("'-v','-s','-x'", "'-v','-s','-x','-k','test_real_repository_help_and_plan_never_execute_git or test_bare_repository_uses_explicit_fallback_not_its_origin_identity'")
(HERE / 'run_derivative.py').write_text(runner, encoding='utf-8')
print(json.dumps(dict(root=str(root), test_sha256=hashlib.sha256(test.read_bytes()).hexdigest(), selected_focals=2)))
