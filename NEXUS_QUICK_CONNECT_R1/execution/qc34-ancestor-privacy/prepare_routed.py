"""Keep the inconclusive crash; use finite prompt-routed callbacks in new cuts."""
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
previous = Path(json.loads((HERE / 'allocation.json').read_text())['root'])
root = Path(tempfile.mkdtemp(prefix='nexus-qc34-routed-focals-')).resolve()
shutil.copytree(previous / 'after', root / 'after', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for name in ('source-pins.json', 'pytest.ini'):
    shutil.copyfile(previous / name, root / name)
test = root / 'after/tests/quick_connect/test_ancestor_privacy.py'
before = test.read_text()
old = '''def scripted(c, monkeypatch, answers):
    values, prompts = iter(answers), []
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    def read(prompt):
        prompts.append(prompt)
        return next(values)
    monkeypatch.setattr('builtins.input', read)
    return prompts'''
new = '''def scripted(c, monkeypatch, expected):
    values, prompts = list(expected), []
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    def read(prompt):
        assert len(prompts) < len(values), 'Prompt budget exhausted; refusing another action'
        expected_prompt, response = values[len(prompts)]
        assert prompt == expected_prompt, ('Unexpected prompt', prompt, expected_prompt)
        prompts.append(prompt)
        return response
    monkeypatch.setattr('builtins.input', read)
    return prompts'''
assert old in before
after = before.replace(old, new)
consent = 'Confirm this review, including the model connection test? [y/customize/cancel] '
after = after.replace("prompts = scripted(c, monkeypatch, ['y'])", "prompts = scripted(c, monkeypatch, [(" + repr(consent) + ", 'y')])", 1)
after = after.replace("prompts = scripted(c, monkeypatch, ['n', 'n'])", "prompts = scripted(c, monkeypatch, [('Project: ', 'n'), (" + repr(consent) + ", 'n')])", 1)
after = after.replace("scripted(c, monkeypatch, ['y'])", "scripted(c, monkeypatch, [('Confirm resume? [y/N] ', 'y')])", 1)
test.write_text(after, encoding='utf-8', newline='\n')
(root / 'changes.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
    fromfile='inconclusive-original/test_ancestor_privacy.py', tofile='prompt-routed/test_ancestor_privacy.py')), encoding='utf-8')
(root / 'extra-test-pin.json').write_text(json.dumps(dict(test_file=str(test), sha256=hashlib.sha256(test.read_bytes()).hexdigest(),
    scenarios=2, instrumentation='faulthandler_timeout=0; external180s; finite exact-prompt callbacks'), indent=2))
(HERE / 'routed-allocation.json').write_text(json.dumps(dict(root=str(root)), indent=2))
runner = (HERE / 'run_separate.py').read_text()
runner = runner.replace("HERE/'allocation.json'", "HERE/'routed-allocation.json'")
(HERE / 'run_routed.py').write_text(runner, encoding='utf-8')
print(json.dumps(dict(root=str(root), test_sha256=hashlib.sha256(test.read_bytes()).hexdigest(),
    original_raw_bytes=(previous / 'ancestor-privacy/raw.log').stat().st_size, pytest_started=False)))
