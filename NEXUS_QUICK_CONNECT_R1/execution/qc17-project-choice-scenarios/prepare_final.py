"""Keep literal no-provider-home resume grammar and explicit resume consent."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
old = Path(json.loads((HERE / 'allocation.json').read_text())['root'])
assert (old / 'result.json').exists()
shutil.copyfile(HERE / 'allocation.json', HERE / 'allocation-corrected.json')
root = Path(tempfile.mkdtemp(prefix='nexus-qc17-final-'))
shutil.copytree(old / 'after', root / 'after', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for name in ('pytest.ini', 'source-pins.json'):
    shutil.copyfile(old / name, root / name)
test = root / 'after/tests/quick_connect/test_quick_connect_project_scenarios.py'
text = test.read_text()
start = text.index("        if tokens == ['connect', '--json']:")
end = text.index("        assert result['quick_connect']['canonical_reference']", start)
text = text[:start] + """        from okto_nexus.adapters.inbound.cli import main
        # Both commands are literal public grammar, without the fixture's
        # additional explicit legacy provider-home selector.
        code = main.main([*tokens, '--home', str(c.home)])
        captured = capsys.readouterr()
        assert code == 0, captured.out + captured.err
        result = json.loads(captured.out)
""" + text[end:]
text = text.replace("        if prompt == 'Choice: ':\n            return 'r'",
                    "        if prompt == 'Choice: ':\n            return 'r'\n        if prompt == 'Confirm resume? [y/N] ':\n            return 'y'")
text = text.replace("assert prompts == ['Use approved folder: ', 'Choice: '] * 2",
                    "assert prompts == ['Use approved folder: ', 'Choice: '] * 2 + ['Confirm resume? [y/N] ']")
test.write_text(text, encoding='utf-8')
(HERE / 'allocation.json').write_text(json.dumps(dict(root=str(root), external_test=str(test),
    sha256=hashlib.sha256(test.read_bytes()).hexdigest(), executed=False,
    changes=['Both bare/harness main use literal selectors without injected provider-home.',
             'Explicit y to canonical resume confirmation after project/folder choice.']), indent=2) + '\n')
print(json.dumps(dict(root=str(root), sha256=hashlib.sha256(test.read_bytes()).hexdigest())))
