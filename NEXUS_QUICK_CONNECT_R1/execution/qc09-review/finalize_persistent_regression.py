"""Normalize only the prepared external regression file, then update its pin."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
plan_path = HERE / 'persistent-regression-plan.json'
plan = json.loads(plan_path.read_text())
target = Path(plan['test_file']).resolve()
assert target.parent.name.startswith('nexus-qc-compat-regression-')
text = target.read_text(encoding='utf-8')
imports = ('from okto_nexus.adapters.inbound.cli.quick_connect_ids import require_public_ids\n'
    'from okto_nexus.adapters.outbound.operator_client import RemoteOperatorHTTP\n'
    'from okto_nexus.adapters.outbound.terminal_http import LocalOperatorHTTP\n')
assert text.count(imports) == 1
text = text.replace(imports, '')
text = text.replace('@pytest.mark.parametrize', imports + '\n@pytest.mark.parametrize', 1)
target.write_text(text, encoding='utf-8', newline='\n')
for args in (['check', '--select', 'I,F,E4,E7,E9', '--fix'], ['format'],
        ['check', '--select', 'I,F,E4,E7,E9']):
    subprocess.run(['rtk', 'proxy', 'ruff', *args, str(target)], check=True)
plan['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
plan['static_checks'] = 'AST parse and Ruff I/F/E4/E7/E9; no test execution'
plan_path.write_text(json.dumps(plan, indent=2), encoding='utf-8')
print(json.dumps(dict(test_file=str(target), sha256=plan['sha256'], tests_executed=False)))
