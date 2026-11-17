"""Own copies only; no app source is placed on the import path."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
root=Path(tempfile.mkdtemp(prefix='nexus-qc25-concurrency-')).resolve()
previous=Path('C:/Users/jpamb/AppData/Local/Temp/nexus-qc24-namespace-h8li_lxe')
shutil.copytree(previous/'after',root/'after',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copyfile(previous/'pytest.ini',root/'pytest.ini')
shutil.copyfile(HERE/'test_concurrency_locks.py',root/'after/tests/quick_connect/test_qc25_concurrency_locks.py')
pins={p.relative_to(REPO).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for directory in ('src','tests','docs') for p in (REPO/directory).rglob('*')
    if p.is_file() and '__pycache__' not in p.parts}
(root/'source-pins.json').write_text(json.dumps(pins,indent=2))
(HERE/'allocation.json').write_text(json.dumps(dict(root=str(root)),indent=2))
runner=(HERE.parent/'qc24-namespace-scenarios/run.py').read_text()
runner=runner.replace("nodes=[('namespace','tests/execution_r4/test_qc24_namespace_http.py')]",
    "nodes=[('race','tests/quick_connect/test_qc25_concurrency_locks.py::test_c18_g15_two_initial_reviews_compete_at_canonical_reserve_only_one_finishes')]")
(HERE/'run.py').write_text(runner)
assert not (root/'after/src').exists()
print(json.dumps(dict(root=str(root),cases=1)))
