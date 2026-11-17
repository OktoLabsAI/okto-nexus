"""Third focal only, preserving the completed two-case cut."""
import json
from pathlib import Path
import shutil
import tempfile

HERE=Path(__file__).resolve().parent
previous=Path(json.loads((HERE/'allocation.json').read_text())['root'])
root=Path(tempfile.mkdtemp(prefix='nexus-qc24-executor-')).resolve()
shutil.copytree(previous/'after',root/'after',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for name in ('pytest.ini','source-pins.json'):
    shutil.copyfile(previous/name,root/name)
shutil.copyfile(HERE/'test_namespace_executor_http.py',root/'after/tests/execution_r4/test_qc24_namespace_executor_http.py')
(HERE/'executor-allocation.json').write_text(json.dumps(dict(root=str(root)),indent=2))
runner=(HERE/'run.py').read_text()
runner=runner.replace("HERE/'allocation.json'","HERE/'executor-allocation.json'")
runner=runner.replace("nodes=[('namespace','tests/execution_r4/test_qc24_namespace_http.py')]",
    "nodes=[('executor','tests/execution_r4/test_qc24_namespace_executor_http.py')]")
(HERE/'run_executor.py').write_text(runner)
print(json.dumps(dict(root=str(root),cases=1)))
