"""Add explicit project-proof and winning-reference assertions, F17 only."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
prior = json.loads((HERE / 'allocation.json').read_text())
old = Path(prior['root'])
assert (old / 'result.json').exists()
shutil.copyfile(HERE / 'allocation.json', HERE / 'allocation-f17-cas.json')
root = Path(tempfile.mkdtemp(prefix='nexus-qc14-f17-proof-'))
shutil.copytree(old / 'after', root / 'after', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for name in ('pytest.ini', 'source-pins.json'):
    shutil.copyfile(old / name, root / name)
test = root / 'after/tests/quick_connect/test_quick_connect_extra_scenarios.py'
text = test.read_text().replace('import json\n', 'import json\nfrom urllib.parse import urlencode\n')
needle = "    before = canonical_snapshot(c)\n    turns = tuple(c.t.turns)\n    call_index = len(c.t.calls)"
replacement = """    winner_public = public_row(c, 'raced-reviewer', first['workspace_id'])
    assert json.loads(winner_public['canonical_ref_json']) == winner['quick_connect']['canonical_reference']
    old_request = json.loads((c.home / 'terminal/profiles/loser.json').read_text())['request']
    current_proof = c.t.call('GET', '/api/v1/runtime-management/connections/project-context?' + urlencode(dict(
        executor_id=old_request['executor_id'], workspace_id=first['workspace_id'], project_root=str(c.project))))
    assert current_proof['project_revision'] != old_request['public_connection']['project_revision']
    before = canonical_snapshot(c)
    turns = tuple(c.t.turns)
    call_index = len(c.t.calls)"""
assert needle in text
text = text.replace(needle, replacement)
text = text.replace("assert public_row(c, 'codex', first['workspace_id']) == first_public\n    saved =",
                    "assert public_row(c, 'codex', first['workspace_id']) == first_public\n"
                    "    assert public_row(c, 'raced-reviewer', first['workspace_id']) == winner_public\n    saved =")
# In this scenario the proven project-CAS is specifically expected; do not
# accept a generic conflict or an unrelated namespace error as evidence.
start = text.index("    assert (result['code'], result['message']) in {")
end = text.index('    assert canonical_snapshot(c) == before', start)
text = text[:start] + "    assert (result['code'], result['message']) == ('CONFLICT', 'The selected project or directory changed. Review it again.'), result\n" + text[end:]
test.write_text(text, encoding='utf-8')
(HERE / 'allocation.json').write_text(json.dumps(dict(root=str(root), antecedent_root=str(old),
    derivative=str(test), derivative_sha256=hashlib.sha256(test.read_bytes()).hexdigest(),
    reason='Explicit GET project-proof difference and exact unchanged winning canonical reference.',
    executed=False), indent=2) + '\n')
print(json.dumps(dict(root=str(root), sha256=hashlib.sha256(test.read_bytes()).hexdigest())))
