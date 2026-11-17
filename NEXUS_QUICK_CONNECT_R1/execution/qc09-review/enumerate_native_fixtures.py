"""Read-only inventory of test-local native factories and their call sites."""
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
rows, users, pins = [], [], {}
for path in sorted((REPO / 'tests').rglob('*.py')):
    text = path.read_text(encoding='utf-8-sig')
    tree = ast.parse(text)
    relative = path.relative_to(REPO).as_posix()
    matches = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for method in node.body:
                if isinstance(method, (ast.AsyncFunctionDef, ast.FunctionDef)) and method.name == 'open':
                    snippet = ast.get_source_segment(text, node) or ''
                    direct_peer = any(token in snippet for token in ('Connector', 'CopiedAdapterSession', 'peer.start'))
                    if node.name == 'Factory' or direct_peer:
                        args = [arg.arg for arg in method.args.posonlyargs + method.args.args + method.args.kwonlyargs]
                        hooks = ('opening_guard', 'process_birth_recorder', 'process_launch')
                        matches.append(dict(path=relative, line=method.lineno, factory=node.name,
                            args=args, accepts_kwargs=method.args.kwarg is not None,
                            direct_native_peer=direct_peer,
                            explicit_hooks={hook: hook in args for hook in hooks},
                            uses_shared_install_native='install_native(' in snippet,
                            account_read_literal='account/read' in text,
                            source_is_legacy='_FAKE_SERVER_SOURCE' in snippet))
        if isinstance(node, ast.ImportFrom) and node.module == 'test_canonical_structured_work':
            if any(name.name == 'native_work' for name in node.names):
                users.append(dict(path=relative, line=node.lineno))
    if matches or any(row['path'] == relative for row in users):
        pins[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    rows.extend(matches)
report = dict(factories=rows, native_work_importers=users, source_pins=pins,
    limitations=['Static inventory is not a failure classification.',
        'Core negotiates optional hooks by signature; missing hooks alone do not prove TypeError.',
        'Factory-named classes include intentional negatives and non-native doubles; direct_native_peer is lexical only.',
        'Do not mass-replace targeted failure/adaptor factories without their exact trace.',
        'No product, fixture, prefix, Core or protocol changes made.'])
(HERE / 'native-fixture-inventory.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(dict(factories=len(rows), native_work_importers=len(users))))
