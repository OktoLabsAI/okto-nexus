"""Prepare the narrowly reviewed checkpoint oracle and monorepo composition."""
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
original = Path(json.loads((HERE / 'git-integration-proposal.json').read_text())['test_file'])
before = original.read_text(encoding='utf-8')
text = before.replace('def local_git(cli, tmp_path):', 'def local_git(cli, tmp_path, *, init_root=None):')
text = text.replace("run('init', '--quiet')", "run('init', '--quiet', cwd=init_root)")
text = text.replace('    original_profile = profile.read_bytes()',
    '    original_profile = json.loads(profile.read_text())')
text = text.replace('        assert profile.read_bytes() == original_profile', '''        observed_profile = json.loads(profile.read_text())
        changes = changed_paths(original_profile, observed_profile)
        (tmp_path / ('checkpoint-delta-' + ('profile' if '--profile' in tokens else 'id') + '.json')).write_text(
            json.dumps({'paths': changes, 'original_operation': original_profile['selection']['quick_connect']['operation'],
                'observed_operation': observed_profile['selection']['quick_connect']['operation']}))
        assert set(changes) <= {'selection.quick_connect.operation'}, changes
        if changes:
            assert original_profile['selection']['quick_connect']['operation'] == 'created'
            assert observed_profile['selection']['quick_connect']['operation'] == 'reused'
        expected_profile = json.loads(json.dumps(original_profile))
        expected_profile['selection']['quick_connect']['operation'] = observed_profile['selection']['quick_connect']['operation']
        assert observed_profile == expected_profile''')
text += '''

def changed_paths(before, after, prefix=''):
    if isinstance(before, dict) and isinstance(after, dict):
        changes = []
        for key in before.keys() | after.keys():
            path = prefix + ('.' if prefix else '') + key
            if key not in before or key not in after:
                changes.append(path)
            else:
                changes.extend(changed_paths(before[key], after[key], path))
        return sorted(changes)
    return [] if before == after else [prefix]


def test_monorepo_ancestor_origin_does_not_expand_execution_root(quick_cli, tmp_path, monkeypatch, capsys):
    c = quick_cli
    ancestor = c.project.parent.resolve()
    assert ancestor.is_relative_to(tmp_path.resolve())
    assert not (c.project / '.git').exists()
    git = local_git(c, tmp_path, init_root=ancestor)
    git('config', '--local', 'remote.origin.url', 'https://fixture.invalid/ancestor-logical.git', cwd=ancestor)
    monkeypatch.setattr(hints, '_trusted_git', c.trusted_git)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    prompts = []
    def confirm(prompt):
        prompts.append(prompt)
        assert len(prompts) == 1
        return 'y'
    monkeypatch.setattr('builtins.input', confirm)
    assert Path.cwd() == c.project
    assert c.run(['connect', 'codex', '--no-chat']) == 0
    output = capsys.readouterr().out
    assert len(prompts) == 1 and 'ancestor-logical' in output and 'git_origin' in output
    assert Path.cwd() == c.project and not (c.project / '.git').exists()
    profile, = (c.home / 'terminal/profiles').glob('*.json')
    saved = json.loads(profile.read_text())
    assert saved['selection']['label'] == 'ancestor-logical'
    assert saved['selection']['project'] == str(c.project)
    assert saved['review_request']['workspace_root'] == str(c.project)
    binding = saved['result']['binding']
    current = c.t.flow.current(saved['selection']['agent'], binding['binding_id'])
    assert current['folders']['workspace_root'] == str(c.project)
    assert saved['state'] == 'done' and saved['result']['public_connection']['state'] == 'bound'
    assert len(c.t.turns) == len(c.t.probes) == 1
'''
root = Path(tempfile.mkdtemp(prefix='nexus-qc-git-cli-derivative-')).resolve()
previous = Path(json.loads((HERE / 'allocation.json').read_text())['root'])
shutil.copytree(previous / 'after', root / 'after', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for name in ('source-pins.json', 'pytest.ini'):
    shutil.copyfile(previous / name, root / name)
test = root / 'after/tests/quick_connect/test_git_cli_integration.py'
test.write_text(text, encoding='utf-8', newline='\n')
(root / 'changes.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
    fromfile='original/test_git_cli_integration.py', tofile='derivative/test_git_cli_integration.py')), encoding='utf-8')
(HERE / 'git-derivative-allocation.json').write_text(json.dumps(dict(root=str(root)), indent=2), encoding='utf-8')
runner = (HERE / 'run_git_integration.py').read_text(encoding='utf-8')
runner = runner.replace("HERE/'git-integration-allocation.json'", "HERE/'git-derivative-allocation.json'")
runner = runner.replace("due=now>=deadline or failed_at is not None and now-failed_at>=15", 'due=now>=deadline')
runner = runner.replace("'-v','-s','--tb=short'", "'-v','-s','-x','--tb=short'")
(HERE / 'run_git_derivative.py').write_text(runner, encoding='utf-8')
(root / 'extra-test-pin.json').write_text(json.dumps(dict(sha256=hashlib.sha256(test.read_bytes()).hexdigest(),
    derivative_changes='Only created→reused observation metadata may change; all other checkpoint fields stay exact. Added monorepo ancestor origin.'), indent=2), encoding='utf-8')
print(json.dumps(dict(root=str(root), test_sha256=hashlib.sha256(test.read_bytes()).hexdigest(), scenarios=10)))
