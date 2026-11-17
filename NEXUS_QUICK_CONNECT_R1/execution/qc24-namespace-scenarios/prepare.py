"""Prepare two focused installed HTTP/SQLite tests outside checkout."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
old=Path('C:/Users/jpamb/AppData/Local/Temp/nexus-qc15-choice-b1fr23qm')
root=Path(tempfile.mkdtemp(prefix='nexus-qc24-namespace-')).resolve()
shutil.copytree(old/'after',root/'after',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copyfile(old/'pytest.ini',root/'pytest.ini')
shutil.copyfile(HERE/'test_namespace_http.py',root/'after/tests/execution_r4/test_qc24_namespace_http.py')
pins={p.relative_to(REPO).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for directory in ('src','tests','docs') for p in (REPO/directory).rglob('*')
    if p.is_file() and '__pycache__' not in p.parts}
(root/'source-pins.json').write_text(json.dumps(pins,indent=2),encoding='utf-8')
(HERE/'allocation.json').write_text(json.dumps(dict(root=str(root)),indent=2),encoding='utf-8')
runner=(HERE.parent/'qc15-cli-choice-scenarios/run.py').read_text(encoding='utf-8')
runner=runner.replace("nodes=[('choices','tests/execution_r4/test_qc15_cli_choices.py')]",
    "nodes=[('namespace','tests/execution_r4/test_qc24_namespace_http.py')]")
runner=runner.replace("record['processes_after']=[item.facts() for item in known.values()]",
    "for item in known.values():\n        if item.alive():\n            kernel.WaitForSingleObject(item.handle,5000)\n    record['processes_after']=[item.facts() for item in known.values()]\n    (out/'runner.json').write_text(json.dumps(record,indent=2))")
(HERE/'run.py').write_text(runner,encoding='utf-8')
assert not (root/'after/src').exists()
print(json.dumps(dict(root=str(root),cases=2)))
