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


def local_git(cli, tmp_path):
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

    run('init', '--quiet')
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
    original_profile = profile.read_bytes()
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
        assert profile.read_bytes() == original_profile


@pytest.mark.parametrize('mode,expected_reason', [
    ('no-origin', 'origin_missing'), ('conflicting-origins', 'origin_ambiguous'),
])
def test_local_git_fallback_enters_canonical_review_without_implicit_test(quick_cli, tmp_path, monkeypatch, capsys, mode, expected_reason):
    c = quick_cli
    git = local_git(c, tmp_path)
    if mode == 'conflicting-origins':
        git('config', '--add', 'remote.origin.url', 'https://fixture.invalid/one.git')
        git('config', '--add', 'remote.origin.url', 'https://fixture.invalid/two.git')
    monkeypatch.setattr(hints, '_trusted_git', c.trusted_git)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr('builtins.input', lambda prompt: 'n')
    assert c.run(['connect', 'codex', '--no-chat']) == 0
    output = capsys.readouterr().out
    profile, = (c.home / 'terminal/profiles').glob('*.json')
    saved = json.loads(profile.read_text())
    metadata = saved['selection']['quick_connect']
    assert metadata['name_discovery']['reason'] == expected_reason
    assert saved['selection']['project'] == str(c.project)
    assert saved['state'] == 'review'
    assert c.t.turns == c.t.probes == []
    assert 'fixture.invalid' not in output
