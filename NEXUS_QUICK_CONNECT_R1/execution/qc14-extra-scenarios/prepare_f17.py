"""Preserve first cut and prepare one exact project-CAS F17 derivative."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
allocation = json.loads((HERE / 'allocation.json').read_text())
old = Path(allocation['root'])
assert (old / 'result.json').exists()
shutil.copyfile(HERE / 'allocation.json', HERE / 'allocation-antecedent.json')
shutil.copyfile(HERE / 'run.py', HERE / 'run-antecedent.py')
root = Path(tempfile.mkdtemp(prefix='nexus-qc14-f17-'))
shutil.copytree(old / 'after', root / 'after', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for name in ('pytest.ini', 'source-pins.json'):
    shutil.copyfile(old / name, root / name)
test = root / 'after/tests/quick_connect/test_quick_connect_extra_scenarios.py'
text = test.read_text()
text = text.replace("assert result['code'] == 'HARNESS_ID_ALREADY_EXISTS'",
    "assert (result['code'], result['message']) in {\n"
    "        ('HARNESS_ID_ALREADY_EXISTS', 'This Harness ID or project directory is already reserved. Recover its original intent.'),\n"
    "        ('CONFLICT', 'The selected project or directory changed. Review it again.'),\n"
    "    }, result")
# The winner adds a canonical realization, which changes the exact project proof
# before the reservation INSERT's uniqueness guard. No generic CONFLICT allowed.
test.write_text(text, encoding='utf-8')
src = (HERE / 'run.py').read_text()
start = src.index('nodes=[')
end = src.index('\nfor label,node in nodes:', start)
node = 'tests/quick_connect/test_quick_connect_extra_scenarios.py::test_f17_free_id_review_loses_race_before_new_test_identity_or_grant'
src = src[:start] + 'nodes=' + repr([('f17-project-cas', node)]) + src[end:]
(HERE / 'run.py').write_text(src, encoding='utf-8')
(HERE / 'allocation.json').write_text(json.dumps(dict(root=str(root), antecedent_root=str(old),
    derivative=str(test), derivative_sha256=hashlib.sha256(test.read_bytes()).hexdigest(),
    reason='Exact project revision CAS conflicts before namespace uniqueness after winner creates a realization.',
    executed=False), indent=2) + '\n')
print(json.dumps(dict(root=str(root), sha256=hashlib.sha256(test.read_bytes()).hexdigest())))
