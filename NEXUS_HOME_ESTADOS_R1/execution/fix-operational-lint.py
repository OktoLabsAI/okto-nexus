"""Apply only reviewed newly edited C408 sites, never legacy reducer cleanup."""
import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
selected = {
    'src/okto_nexus/adapters/outbound/sqlite/home_entries.py': {258},
    'src/okto_nexus/domain/home_harness_board.py': {324, 338, 403, 413},
    'src/okto_nexus/domain/home_entry_pages.py': {331},
}
diagnostics = json.loads((Path(__file__).parent / 'ruff-operational-remaining.json').read_text())


class DictionaryNormalization(ast.NodeTransformer):
    def visit_Call(self, node):
        self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id == 'dict' and not node.args:
            return ast.Dict(keys=[ast.Constant(k.arg) if k.arg else None for k in node.keywords],
                            values=[k.value for k in node.keywords])
        return node


proof = []
for relative, rows in selected.items():
    path = ROOT / relative
    raw = path.read_bytes()
    text = raw.decode('utf-8')
    lines = text.splitlines(keepends=True)
    edits = []
    found = set()
    for item in diagnostics:
        if Path(item['filename']).resolve() != path.resolve() or item['location']['row'] not in rows:
            continue
        if item['code'] != 'C408':
            raise RuntimeError('Unexpected lint transformation')
        found.add(item['location']['row'])
        for edit in item['fix']['edits']:
            start, end = edit['location'], edit['end_location']
            begin = sum(map(len, lines[:start['row'] - 1])) + start['column'] - 1
            finish = sum(map(len, lines[:end['row'] - 1])) + end['column'] - 1
            replacement = edit['content']
            if b'\r\n' in raw:
                replacement = replacement.replace('\n', '\r\n')
            edits.append((begin, finish, replacement))
    if found != rows:
        raise RuntimeError('Reviewed sites changed; refuse adaptive source rewrite')
    before = ast.dump(DictionaryNormalization().visit(ast.parse(text)), include_attributes=False)
    for begin, finish, replacement in sorted(edits, reverse=True):
        text = text[:begin] + replacement + text[finish:]
    after = ast.dump(DictionaryNormalization().visit(ast.parse(text)), include_attributes=False)
    if before != after:
        raise RuntimeError('AST changed beyond dictionary literal substitution')
    path.write_bytes(text.encode('utf-8'))
    proof.append(dict(path=relative, before_sha256=hashlib.sha256(raw).hexdigest(), after_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                      reviewed_rows=sorted(rows), dictionary_normalized_ast_equal=True))
(Path(__file__).parent / 'operational-lint-edits.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
print(json.dumps(proof, indent=2))
