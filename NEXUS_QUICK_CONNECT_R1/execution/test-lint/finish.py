"""Finish explicit reexport metadata and record the complete restricted delta."""
import ast
import copy
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
records = json.loads((HERE.parent / 'persistence-applied-final/report.json').read_text(encoding='utf-8'))['records']
paths = sorted({REPO / row['target'] for row in records})
failures = json.loads((HERE / 'ruff-after.json').read_text(encoding='utf-8'))
affected = {Path(row['filename']) for row in failures}
assert all(row['code'] == 'F811' for row in failures)
for path in affected:
    text = path.read_text(encoding='utf-8')
    assert '__all__' not in text
    tree = ast.parse(text)
    # Explicitly export the module's existing public bindings, including helpers
    # and test functions, so wildcard visibility is preserved as well.
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(alias.asname or (alias.name.split('.')[0] if isinstance(node, ast.Import) else alias.name) for alias in node.names)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update(child.id for target in targets for child in ast.walk(target) if isinstance(child, ast.Name))
    names = sorted(name for name in names if not name.startswith('_'))
    text += '\n\n# Explicit public exports include pytest fixtures used through injection.\n__all__ = ' + repr(names) + '\n'
    path.write_text(text, encoding='utf-8', newline='')


class Normalize(ast.NodeTransformer):
    def __init__(self, filename):
        self.filename = filename

    def visit_Assign(self, node):
        if any(isinstance(target, ast.Name) and target.id == '__all__' for target in node.targets):
            return None
        return self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module == 'pathlib' and self.filename in {'test_posix_physical_paths.py', 'test_qc15_cli_choices.py'}:
            return None
        if node.module == 'copy' and self.filename == 'test_qc33_shared_service.py':
            return None
        for alias in node.names:
            if alias.asname == alias.name:
                alias.asname = None
        return node

    def visit_Import(self, node):
        if self.filename == 'test_qc33_shared_service.py' and [alias.name for alias in node.names] == ['asyncio']:
            return None
        return node

    def visit_Name(self, node):
        if self.filename == 'test_posix_physical_paths.py' and node.id == 'l':
            node.id = 'lower_identity'
        return node


output = []
baseline = {row['target']: row['persisted_sha256'] for row in records}
for path in paths:
    backup = HERE / 'before' / path.name
    original = backup.read_bytes() if backup.exists() else path.read_bytes()
    key = path.relative_to(REPO).as_posix()
    assert hashlib.sha256(original).hexdigest() == baseline[key]
    before, after = original.decode(), path.read_text(encoding='utf-8')
    old_tree, new_tree = ast.parse(before), ast.parse(after)
    assert ast.dump(Normalize(path.name).visit(copy.deepcopy(old_tree))) == ast.dump(Normalize(path.name).visit(copy.deepcopy(new_tree))), key
    old_asserts = sum(isinstance(node, ast.Assert) for node in ast.walk(old_tree))
    new_asserts = sum(isinstance(node, ast.Assert) for node in ast.walk(new_tree))
    assert old_asserts == new_asserts
    if before != after:
        (HERE / (path.stem + '.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile='persistence-applied-final/' + key, tofile=key)))
    output.append({'path': key, 'before_sha256': hashlib.sha256(original).hexdigest(), 'after_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'changed': before != after, 'normalized_ast_equal': True, 'assertions_before': old_asserts, 'assertions_after': new_asserts})
command = ['rtk', 'proxy', 'ruff', 'check', '--isolated', '--select', 'E4,E7,E9,F', *[str(p.relative_to(REPO)) for p in paths], '--output-format', 'json']
result = subprocess.run(command, cwd=REPO, capture_output=True, text=True, timeout=30)
(HERE / 'ruff-final.json').write_text(result.stdout)
assert result.returncode == 0, result.stdout
report = {'scope': 'Only 22 newly persisted quick_connect tests; no product, ledger or Git mutation.', 'baseline': 'persistence-applied-final/report.json persisted_sha256', 'files': output, 'ruff_argv': command, 'ruff_before_count': len(json.loads((HERE / 'ruff-before.json').read_text(encoding='utf-8'))), 'ruff_final_count': len(json.loads(result.stdout)), 'ruff_exit': result.returncode, 'changes': ['Explicit same-name fixture import aliases.', 'Explicit __all__ of existing public bindings resolves F811 under this Ruff version while preserving public wildcard exports.', 'Four truly unused imports removed: pathlib.Path twice, asyncio and copy.deepcopy.', 'POSIX local l renamed lower_identity.'], 'semantic_check': 'Full AST equal after normalizing precisely these import/export metadata changes and local rename; all assertions retained.', 'pytest_rerun': False, 'initial_attempt': 'Same-name aliases alone left F811; preserved ruff-after.json before adding explicit exports.'}
(HERE / 'report.json').write_text(json.dumps(report, indent=2))
print(json.dumps({'files': len(paths), 'changed': sum(row['changed'] for row in output), 'ruff_before': report['ruff_before_count'], 'ruff_final': report['ruff_final_count'], 'assertions': sum(row['assertions_after'] for row in output), 'report_sha256': hashlib.sha256((HERE / 'report.json').read_bytes()).hexdigest()}))
