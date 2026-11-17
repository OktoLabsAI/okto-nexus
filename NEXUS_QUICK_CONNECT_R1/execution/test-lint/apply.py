"""Explicit pytest reexports and unused-import cleanup; verify normalized AST."""
import ast
import copy
import difflib
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tokenize

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
records = json.loads((HERE.parent / 'persistence-applied-final/report.json').read_text(encoding='utf-8'))['records']
paths = sorted({REPO / row['target'] for row in records})
assert len(paths) == 22
fixtures = {'quick_cli', 'terminal', 'checking', 'local_setup', 'isolated_provider_environment', 'cli', 'two_harnesses', 'remote', 'work', 'connected_local', 'qualified_contract'}
removed = {('test_posix_physical_paths.py', 'pathlib', 'Path'), ('test_qc15_cli_choices.py', 'pathlib', 'Path'), ('test_qc33_shared_service.py', '', 'asyncio'), ('test_qc33_shared_service.py', 'copy', 'deepcopy')}
baseline = {row['target']: row['persisted_sha256'] for row in records}
command = ['rtk', 'proxy', 'ruff', 'check', '--isolated', '--select', 'E4,E7,E9,F', *[str(p.relative_to(REPO)) for p in paths], '--output-format', 'json']
before_lint = subprocess.run(command, cwd=REPO, capture_output=True, text=True, timeout=30)
(HERE / 'ruff-before.json').write_text(before_lint.stdout)


def normalized(text, filename):
    tree = ast.parse(text)
    class Normalizer(ast.NodeTransformer):
        def visit_Import(self, node):
            node.names = [a for a in node.names if (filename, '', a.name) not in removed]
            for alias in node.names:
                if alias.asname == alias.name:
                    alias.asname = None
            return node if node.names else None

        def visit_ImportFrom(self, node):
            node.names = [a for a in node.names if (filename, node.module, a.name) not in removed]
            for alias in node.names:
                if alias.asname == alias.name:
                    alias.asname = None
            return node if node.names else None

        def visit_Name(self, node):
            if filename == 'test_posix_physical_paths.py' and node.id == 'l':
                node.id = 'lower_identity'
            return node
    return ast.dump(Normalizer().visit(copy.deepcopy(tree)), include_attributes=False)


output = []
for path in paths:
    original = path.read_bytes()
    key = path.relative_to(REPO).as_posix()
    assert hashlib.sha256(original).hexdigest() == baseline[key], key
    text = original.decode('utf-8')
    tree = ast.parse(text)
    edits = []
    lines = text.splitlines(keepends=True)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if any((path.name, node.module, a.name) in removed for a in node.names):
                assert all((path.name, node.module, a.name) in removed for a in node.names)
                edits.append((node.lineno, node.end_lineno, ''))
            elif node.module and node.module.startswith('test_'):
                source = ''.join(lines[node.lineno - 1:node.end_lineno])
                for alias in node.names:
                    if alias.name in fixtures and alias.asname is None:
                        source, count = re.subn(r'\b' + re.escape(alias.name) + r'\b', alias.name + ' as ' + alias.name, source)
                        assert count == 1
                if source != ''.join(lines[node.lineno - 1:node.end_lineno]):
                    edits.append((node.lineno, node.end_lineno, source))
        elif isinstance(node, ast.Import) and any((path.name, '', a.name) in removed for a in node.names):
            assert all((path.name, '', a.name) in removed for a in node.names)
            edits.append((node.lineno, node.end_lineno, ''))
    for start, end, replacement in reversed(edits):
        lines[start - 1:end] = [replacement]
    after = ''.join(lines)
    if path.name == 'test_posix_physical_paths.py':
        tokens = list(tokenize.generate_tokens(io.StringIO(after).readline))
        after = tokenize.untokenize([t._replace(string='lower_identity') if t.type == tokenize.NAME and t.string == 'l' else t for t in tokens])
    assert normalized(text, path.name) == normalized(after, path.name), key
    assert sum(isinstance(n, ast.Assert) for n in ast.walk(ast.parse(text))) == sum(isinstance(n, ast.Assert) for n in ast.walk(ast.parse(after)))
    if text != after:
        before = HERE / 'before' / path.name
        before.parent.mkdir(exist_ok=True)
        before.write_bytes(original)
        path.write_text(after, encoding='utf-8', newline='')
        (HERE / (path.stem + '.patch')).write_text(''.join(difflib.unified_diff(text.splitlines(True), after.splitlines(True), fromfile='persistence-applied-final/' + key, tofile=key)), encoding='utf-8')
    output.append({'path': key, 'before_sha256': hashlib.sha256(original).hexdigest(), 'after_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'changed': text != after, 'normalized_ast_equal': True, 'assertions_unchanged': True})
after_lint = subprocess.run(command, cwd=REPO, capture_output=True, text=True, timeout=30)
(HERE / 'ruff-after.json').write_text(after_lint.stdout)
assert after_lint.returncode == 0, after_lint.stdout
report = {'scope': 'Only 22 newly persisted quick_connect tests; no product, ledger or Git mutation.', 'baseline': 'persistence-applied-final/report.json persisted_sha256', 'files': output, 'ruff_argv': command, 'ruff_before_count': len(json.loads(before_lint.stdout)), 'ruff_after_count': len(json.loads(after_lint.stdout)), 'ruff_exit': after_lint.returncode, 'semantic_check': 'Full AST equal after normalizing same-name import aliases, removal of four verified unused imports, and one POSIX local variable rename. Assertion counts unchanged.', 'pytest_rerun': False}
(HERE / 'report.json').write_text(json.dumps(report, indent=2))
print(json.dumps({'files': len(paths), 'changed': sum(x['changed'] for x in output), 'ruff_before': report['ruff_before_count'], 'ruff_after': report['ruff_after_count'], 'normalized_ast_equal': True}))
