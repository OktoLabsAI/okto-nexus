"""Composed real local Git + synthetic setup + canonical HTTP/SQLite.

Interactive input/isatty are controlled by the test; this is not real PTY
or human acceptance. Git only reads/writes an owned temporary repository.
No provider, native executable, account, remote Git transport or service starts.
"""
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
import test_quick_connect_cli as fixtures
from test_connection_setup_recovery import snapshot

from okto_nexus.adapters.inbound.cli import connect
from okto_nexus.adapters.outbound import git_project_hint as hints

local_setup = fixtures.local_setup
checking = fixtures.checking
terminal = fixtures.terminal
quick_cli = fixtures.quick_cli
isolated_provider_environment = fixtures.isolated_provider_environment


def local_git(cli, tmp_path, *, init_root=None):
    executable = cli.trusted_git(cli.project)
    if not executable:
        pytest.skip('A trusted local Git is required for this composed fixture')
    empty = tmp_path / 'git-empty-template'
    empty.mkdir()
    env = {k: v for k, v in os.environ.items() if k.upper() in (
        'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'SYSTEMDRIVE', 'PATHEXT', 'PATH', 'TEMP', 'TMP')}
    env.update(HOME=str(tmp_path), USERPROFILE=str(tmp_path), XDG_CONFIG_HOME=str(tmp_path),
        GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_GLOBAL=os.devnull,
        GIT_TERMINAL_PROMPT='0')

    def run(*args, cwd=None):
        return subprocess.run([str(executable), '-c', 'init.templateDir=' + str(empty),
            '-c', 'core.hooksPath=' + str(empty), '-C', str(cwd or cli.project), *args],
            cwd=tmp_path, env=env, stdin=subprocess.DEVNULL, capture_output=True,
            timeout=5, check=True)

    run('init', '--quiet', cwd=init_root)
    return run


def session_count(cli):
    with cli.t.deps.connection_factory.unit_of_work(write=False) as uow:
        return uow.connection.execute('SELECT COUNT(*) FROM execution_sessions').fetchone()[0]


@pytest.mark.parametrize('origin', [
    'https://example.invalid/team/logical-origin.git',
    'git@example.invalid:team/logical-origin.git',
    'ssh://git@example.invalid:2222/team/logical-origin.git',
    'file:///srv/git/logical-origin.git',
    '/srv/git/logical-origin.git',
    r'C:\fixture\logical-origin.git',
    'https://fake-user:PRIVATE@example.invalid/team/logical-origin.git?token=PRIVATE#PRIVATE',
])
def test_origin_first_connect_and_changed_metadata_exact_resume(quick_cli, tmp_path, monkeypatch, capsys, origin):
    c = quick_cli
    git = local_git(c, tmp_path)
    git('config', '--local', 'remote.origin.url', origin)
    monkeypatch.setattr(hints, '_trusted_git', c.trusted_git)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    prompts = []

    def confirm(prompt):
        prompts.append(prompt)
        assert len(prompts) == 1, 'First short entry requested another choice'
        return 'y'

    monkeypatch.setattr('builtins.input', confirm)
    before_sessions = session_count(c)
    assert c.project.name != 'logical-origin'
    assert c.run(['connect', 'codex', '--no-chat']) == 0
    output = capsys.readouterr().out
    assert len(prompts) == 1
    assert 'ID do Harness: codex' in output and 'git_origin' in output
    assert 'logical-origin' in output and str(c.project) in output
    assert 'PRIVATE' not in output and 'example.invalid' not in output
    profile, = (c.home / 'terminal/profiles').glob('*.json')
    saved = json.loads(profile.read_text())
    assert saved['state'] == 'done'
    assert saved['selection']['label'] == 'logical-origin'
    assert saved['selection']['project'] == str(c.project)
    public = saved['result']['public_connection']
    assert public['connect_id'] == 'codex' and public['state'] == 'bound'
    reference = public['canonical_ref']
    assert set(reference) == {'server_id', 'executor_id', 'workspace_id', 'binding_id',
        'workspace_binding_id', 'agent_id', 'endpoint_id'}
    assert all(isinstance(value, str) and value for value in reference.values())
    assert len(c.t.turns) == len(c.t.probes) == 1
    assert session_count(c) == before_sessions
    before = snapshot(c.t.deps)
    original_profile = json.loads(profile.read_text())
    git('config', '--local', 'remote.origin.url', 'https://changed.invalid/different-name.git')

    def forbidden(*args, **kwargs):
        pytest.fail('Exact profile or ID resume rediscovered Git metadata')

    monkeypatch.setattr(hints, 'discover_project_name', forbidden)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: False))
    for tokens in (['connect', '--profile', profile.stem, '--json', '--no-chat'],
            ['connect', '--id', 'codex', '--json', '--no-chat']):
        assert c.run(tokens) == 0
        resumed = json.loads(capsys.readouterr().out)
        assert resumed['quick_connect']['status'] == 'connected'
        assert resumed['quick_connect']['canonical_reference'] == reference
        assert resumed['quick_connect']['project_name'] == 'logical-origin'
        assert resumed['quick_connect']['project_root'] == str(c.project)
        assert snapshot(c.t.deps) == before
        assert len(c.t.turns) == len(c.t.probes) == 1
        assert session_count(c) == before_sessions
        observed_profile = json.loads(profile.read_text())
        changes = changed_paths(original_profile, observed_profile)
        (tmp_path / ('checkpoint-delta-' + ('profile' if '--profile' in tokens else 'id') + '.json')).write_text(
            json.dumps({'paths': changes, 'original_operation': original_profile['selection']['quick_connect']['operation'],
                'observed_operation': observed_profile['selection']['quick_connect']['operation']}))
        assert original_profile['state'] == observed_profile['state'] == 'done'
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
    assert saved['review_request']['configuration']['workspace_root'] == str(c.project)
    binding = saved['result']['binding']
    current = c.t.flow.current(saved['selection']['agent'], binding['binding_id'])
    assert current['folders']['workspace_root'] == str(c.project)
    assert saved['state'] == 'done' and saved['result']['public_connection']['state'] == 'bound'
    assert len(c.t.turns) == len(c.t.probes) == 1
