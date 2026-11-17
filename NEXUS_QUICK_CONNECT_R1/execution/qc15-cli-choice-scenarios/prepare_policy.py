"""New bounded B07 cut, preserving the previous eight-case qualification."""
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
previous = Path(json.loads((HERE/'allocation.json').read_text())['root'])
root = Path(tempfile.mkdtemp(prefix='nexus-qc15-policy-')).resolve()
shutil.copytree(previous/'after',root/'after',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copyfile(previous/'source-pins.json',root/'source-pins.json')
shutil.copyfile(previous/'pytest.ini',root/'pytest.ini')
shutil.copyfile(HERE/'test_policy_denial.py',root/'after/tests/execution_r4/test_qc15_policy_denial.py')
(HERE/'policy-allocation.json').write_text(json.dumps(dict(root=str(root)),indent=2)+'\n',encoding='utf-8')
runner = (HERE/'run.py').read_text(encoding='utf-8')
runner = runner.replace("HERE/'allocation.json'", "HERE/'policy-allocation.json'")
runner = runner.replace("nodes=[('choices','tests/execution_r4/test_qc15_cli_choices.py')]",
    "nodes=[('policy','tests/execution_r4/test_qc15_policy_denial.py')]")
(HERE/'run_policy.py').write_text(runner,encoding='utf-8')
print(json.dumps(dict(root=str(root),cases=1)))
