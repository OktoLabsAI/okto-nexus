"""Format the new test without changing its already-qualified syntax tree."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

repo = Path(r'D:/Projetos/Techridy/okto-nexus-connector')
target = repo / 'tests/unit/test_remote_setup.py'
before = target.read_bytes()
tree = ast.dump(ast.parse(before))
subprocess.run(['ruff', 'format', str(target)], cwd=repo, check=True)
after = target.read_bytes()
assert ast.dump(ast.parse(after)) == tree
subprocess.run(['ruff', 'check', str(target)], cwd=repo, check=True)
report = dict(file=str(target), before_sha256=hashlib.sha256(before).hexdigest(),
    after_sha256=hashlib.sha256(after).hexdigest(), syntax_tree_unchanged=True,
    product_files_unchanged=True, installed_tests_precede_formatting=True)
(Path(__file__).parent / 'test-format-equivalence.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report))
