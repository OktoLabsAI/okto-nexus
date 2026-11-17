"""Restore accidentally omitted fallback cases and assert collection cardinality."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
previous = Path(json.loads((HERE / 'git-final-allocation.json').read_text())['root'])
strict = Path(json.loads((HERE / 'git-derivative-allocation.json').read_text())['root'])
base = (previous / 'after/tests/quick_connect/test_git_cli_integration.py').read_text()
source = (strict / 'after/tests/quick_connect/test_git_cli_integration.py').read_text()
tree = ast.parse(source)
node = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
    and node.name == 'test_local_git_fallback_enters_canonical_review_without_implicit_test')
start = min(node.lineno, *(decorator.lineno for decorator in node.decorator_list))
block = '\n'.join(source.splitlines()[start - 1:node.end_lineno])
text = base.replace('def changed_paths(', block + '\n\n\ndef changed_paths(', 1)
scenarios = 0
for node in ast.parse(text).body:
    if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
        multiplier = 1
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == 'parametrize':
                multiplier *= len(ast.literal_eval(decorator.args[1]))
        scenarios += multiplier
assert scenarios == 10, scenarios
root = Path(tempfile.mkdtemp(prefix='nexus-qc-git-cli-complete-')).resolve()
shutil.copytree(previous / 'after', root / 'after', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for name in ('source-pins.json', 'pytest.ini'):
    shutil.copyfile(previous / name, root / name)
test = root / 'after/tests/quick_connect/test_git_cli_integration.py'
test.write_text(text, encoding='utf-8', newline='\n')
(root / 'extra-test-pin.json').write_text(json.dumps(dict(sha256=hashlib.sha256(test.read_bytes()).hexdigest(), scenarios=scenarios,
    restored_fallback_source=str(strict), authority_oracle='Exact six-path DONE metadata whitelist, all other checkpoint fields unchanged.'), indent=2), encoding='utf-8')
(HERE / 'git-complete-allocation.json').write_text(json.dumps(dict(root=str(root)), indent=2), encoding='utf-8')
runner = (HERE / 'run_git_final.py').read_text()
runner = runner.replace("HERE/'git-final-allocation.json'", "HERE/'git-complete-allocation.json'")
(HERE / 'run_git_complete.py').write_text(runner, encoding='utf-8')
print(json.dumps(dict(root=str(root), test_sha256=hashlib.sha256(test.read_bytes()).hexdigest(), ast_scenarios=scenarios)))
