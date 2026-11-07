import ast
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

root = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
output = Path(__file__).parent
rows = json.loads((output/'inputs.json').read_text(encoding='utf-8'))
paths = {root/p for row in rows for p in row['ledger']['files'] if p.endswith('.py')}
for directory in (root/'tests', root.parent/'okto-nexus-connector/tests', root.parent/'okto-nexus-connector-core/tests'):
    paths.update(directory.rglob('*.py'))
index = {}
for path in sorted(paths):
    if not path.exists():
        continue
    try:
        text = path.read_text(encoding='utf-8-sig')
        tree = ast.parse(text)
    except (SyntaxError,UnicodeError):
        continue
    entries = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            entry = dict(name=node.name,line=node.lineno,end=node.end_lineno)
            if node.name.startswith('test_'):
                entry['assertions'] = [ast.unparse(n.test) for n in ast.walk(node) if isinstance(n,ast.Assert)]
            entries.append(entry)
    index[str(path.resolve())] = dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), symbols=entries)
(output/'source-index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding='utf-8')
evidence = {}
evidence_paths = list((root/'plans/agent_ops/evidence').rglob('*.xml'))
evidence_paths += list((root.parent/'okto-nexus-connector/docs/evidence/diagnostics-v1').rglob('*.xml'))
for path in evidence_paths:
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        continue
    for case in tree.iter('testcase'):
        name = case.get('name','')
        relative = path.relative_to(root).as_posix() if path.is_relative_to(root) else '../okto-nexus-connector/'+path.relative_to(root.parent/'okto-nexus-connector').as_posix()
        record = dict(path=relative,name=name,classname=case.get('classname'),
            result=next((tag.upper() for tag in ('failure','error','skipped') if case.find(tag) is not None),'PASS'))
        evidence.setdefault(name.split('[')[0],[]).append(record)
(output/'xml-index.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(source_files=len(index),unique_test_names=len(evidence))))
