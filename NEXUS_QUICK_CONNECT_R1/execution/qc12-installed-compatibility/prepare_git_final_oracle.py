"""Implement Root's exact six-field DONE-only observation whitelist externally."""
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
previous = Path(json.loads((HERE / 'git-derivative-allocation.json').read_text())['root'])
before = (previous / 'after/tests/quick_connect/test_git_cli_integration.py').read_text()
start = before.index("        assert set(changes) <= {'selection.quick_connect.operation'}, changes")
end = before.index('\n\n\ndef ', start)
text = before[:start] + '''        assert original_profile['state'] == observed_profile['state'] == 'done'
        expected_profile = json.loads(json.dumps(original_profile))
        if '--profile' in tokens:
            assert changes == [], changes
        else:
            allowed = {'selection.public_connection.project_revision', 'selection.public_connection.reservation_ref',
                'selection.quick_connect.name_discovery.reason', 'selection.quick_connect.name_discovery.status',
                'selection.quick_connect.operation', 'selection.quick_connect.project_name_source'}
            assert set(changes) == allowed, changes
            assert original_profile['selection']['quick_connect']['operation'] == 'created'
            assert original_profile['selection']['quick_connect']['project_name_source'] == 'git_origin'
            assert original_profile['selection']['quick_connect']['name_discovery'] == {
                'status': 'discovered', 'reason': 'git_origin'}
            proposal = original_profile['selection']['public_connection']
            assert isinstance(proposal['reservation_ref'], str) and proposal['reservation_ref']
            assert proposal['project_revision'].startswith('sha256:')
            assert proposal == original_profile['request']['public_connection']
            expected_profile['selection']['public_connection'] = {'version': 1, 'connect_id': 'codex'}
            expected_profile['selection']['quick_connect'].update(operation='reused',
                project_name_source='existing_nexus', name_discovery={
                    'status': 'not_needed', 'reason': 'existing_nexus'})
        # Full equality protects request/review_request/revisions/intent,
        # receipt, seven-field identities, approvals and unknown/private fields.
        assert observed_profile == expected_profile
''' + before[end:]
text = text.replace("saved['review_request']['workspace_root']", "saved['review_request']['configuration']['workspace_root']")
root = Path(tempfile.mkdtemp(prefix='nexus-qc-git-cli-final-')).resolve()
shutil.copytree(previous / 'after', root / 'after', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for name in ('source-pins.json', 'pytest.ini'):
    shutil.copyfile(previous / name, root / name)
test = root / 'after/tests/quick_connect/test_git_cli_integration.py'
test.write_text(text, encoding='utf-8', newline='\n')
(root / 'changes.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
    fromfile='strict-derivative/test_git_cli_integration.py', tofile='reviewed-derivative/test_git_cli_integration.py')), encoding='utf-8')
(root / 'extra-test-pin.json').write_text(json.dumps(dict(sha256=hashlib.sha256(test.read_bytes()).hexdigest(),
    policy='Root-reviewed exact six-path DONE-only observation delta; all remaining checkpoint fields exact.'), indent=2), encoding='utf-8')
(HERE / 'git-final-allocation.json').write_text(json.dumps(dict(root=str(root)), indent=2), encoding='utf-8')
runner = (HERE / 'run_git_derivative.py').read_text()
runner = runner.replace("HERE/'git-derivative-allocation.json'", "HERE/'git-final-allocation.json'")
(HERE / 'run_git_final.py').write_text(runner, encoding='utf-8')
print(json.dumps(dict(root=str(root), test_sha256=hashlib.sha256(test.read_bytes()).hexdigest(), scenarios=10)))
