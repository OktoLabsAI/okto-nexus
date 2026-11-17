"""Copy real remote fixture dependencies byte-identically; never copy src."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
root=Path(tempfile.mkdtemp(prefix='nexus-qc30-remote-id-')).resolve()
previous=Path('C:/Users/jpamb/AppData/Local/Temp/nexus-qc24-namespace-h8li_lxe')
shutil.copytree(previous/'after',root/'after',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copyfile(previous/'pytest.ini',root/'pytest.ini')
index={p.stem:p for directory in ('tests','tests/execution_r4','tests/quick_connect') for p in (REPO/directory).glob('*.py')}
queue=[REPO/'tests/execution_r4/test_remote_operator_terminal.py']
seen=set()
fixtures={}
while queue:
    source=queue.pop()
    if source in seen:
        continue
    seen.add(source)
    target=root/'after'/source.relative_to(REPO)
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
    fixtures[source.relative_to(REPO).as_posix()]=hashlib.sha256(source.read_bytes()).hexdigest()
    for node in ast.walk(ast.parse(source.read_text(encoding='utf-8-sig'))):
        names=[v.name.split('.')[0] for v in node.names] if isinstance(node,ast.Import) else (
            [node.module.split('.')[0]] if isinstance(node,ast.ImportFrom) and node.module else [])
        queue.extend(index[name] for name in names if name in index and index[name] not in seen)
shutil.copyfile(HERE/'test_remote_public_id.py',root/'after/tests/execution_r4/test_qc30_remote_public_id.py')
pins={p.relative_to(REPO).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for directory in ('src','tests','docs') for p in (REPO/directory).rglob('*')
    if p.is_file() and '__pycache__' not in p.parts}
(root/'source-pins.json').write_text(json.dumps(pins,indent=2))
(HERE/'allocation.json').write_text(json.dumps(dict(root=str(root),fixture_pins=fixtures),indent=2))
runner=(HERE.parent/'qc24-namespace-scenarios/run.py').read_text()
runner=runner.replace("nodes=[('namespace','tests/execution_r4/test_qc24_namespace_http.py')]",
    "nodes=[('remote','tests/execution_r4/test_qc30_remote_public_id.py')]")
(HERE/'run.py').write_text(runner)
assert not (root/'after/src').exists()
print(json.dumps(dict(root=str(root),cases=1,fixture_files=len(fixtures))))
