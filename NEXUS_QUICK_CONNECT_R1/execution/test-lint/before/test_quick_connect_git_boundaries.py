"""Installed CLI + actual owned Git metadata; no remote transports."""
import json
import os
from pathlib import Path
import subprocess

import pytest
from test_quick_connect_cli import (  # noqa: F401
    checking, invoke, isolated_provider_environment, local_setup, quick_cli, terminal,
)
from test_quick_connect_extra_scenarios import canonical_snapshot

GIT = Path('C:/Program Files/Git/cmd/git.exe')


@pytest.fixture
def git_local(tmp_path):
    if not GIT.is_file():
        pytest.skip('Allowlisted absolute Git unavailable; no installation attempted.')
    hooks, templates = tmp_path / 'empty-hooks', tmp_path / 'empty-templates'
    hooks.mkdir()
    templates.mkdir()
    commands = []
    def run(root, *args, supported=False):
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
        env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0')
        argv = [str(GIT), '-c', 'core.hooksPath=' + str(hooks), '-c', 'init.templateDir=' + str(templates),
                '-c', 'protocol.allow=never', '-c', 'commit.gpgsign=false', '-c', 'user.name=Fixture Only',
                '-c', 'user.email=fixture@example.invalid', '-C', str(root), *args]
        result = subprocess.run(argv, env=env, cwd=root, stdin=subprocess.DEVNULL, shell=False,
                                capture_output=True, text=True, timeout=5)
        commands.append(dict(argv=argv, exit_code=result.returncode))
        if supported and result.returncode != 0 and ('unknown option' in result.stderr or 'not supported' in result.stderr):
            pytest.skip('Installed Git does not support this worktree/config feature.')
        assert result.returncode == 0, (args, result.stdout, result.stderr)
        return result.stdout.strip()
    run.commands = commands
    return run


def init(git, root, origin=None):
    git(root, 'init')
    if origin:
        git(root, 'config', '--local', 'remote.origin.url', origin)


def actual_review(c, capsys, monkeypatch, *, profile='boundary'):
    from okto_nexus.adapters.outbound import git_project_hint
    monkeypatch.setattr(git_project_hint, '_trusted_git', c.trusted_git)
    before = canonical_snapshot(c)
    value = invoke(c, capsys, ['connect', 'codex', '--profile', profile, '--json'], expected=3)
    assert value['state'] == 'review'
    assert value['selection']['project'] == str(c.project)
    assert value['quick_connect']['project_root'] == str(c.project)
    assert canonical_snapshot(c) == before and c.t.turns == c.t.probes == []
    return value


def configure(c, capsys, review, expected_name, *, profile='boundary'):
    result = invoke(c, capsys, ['connect', '--profile', profile, '--approve', review['review_revision'], '--json'])
    assert result['state'] == 'configured'
    assert result['quick_connect']['project_name'] == expected_name
    assert result['quick_connect']['project_root'] == str(c.project)
    reference = result['quick_connect']['canonical_reference']
    assert len(reference) == 7 and reference['binding_id'] == result['binding_id']
    before = canonical_snapshot(c)
    again = invoke(c, capsys, ['connect', '--profile', profile, '--json'])
    assert again['quick_connect']['canonical_reference'] == reference
    assert canonical_snapshot(c) == before and len(c.t.turns) == len(c.t.probes) == 1


def test_d08_path_without_git_reports_directory_fallback(quick_cli, monkeypatch, capsys):
    c = quick_cli
    monkeypatch.setenv('PATH', '')
    review = actual_review(c, capsys, monkeypatch)
    assert review['selection']['label'] == c.project.name
    assert review['quick_connect']['project_name_source'] == 'directory'
    assert review['quick_connect']['name_discovery'] == {'status': 'fallback', 'reason': 'git_unavailable'}


def test_d09_nonrepository_reports_directory_fallback(quick_cli, git_local, monkeypatch, capsys):
    c = quick_cli
    assert not (c.project / '.git').exists()
    review = actual_review(c, capsys, monkeypatch)
    assert review['selection']['label'] == c.project.name
    assert review['quick_connect']['project_name_source'] == 'directory'
    assert review['quick_connect']['name_discovery']['reason'] == 'not_a_repository'


def test_d11_invalid_private_origin_is_not_exposed(quick_cli, git_local, monkeypatch, capsys):
    c = quick_cli
    init(git_local, c.project, 'https://PRIVATE.invalid/team/bad%2fPRIVATE.git')
    review = actual_review(c, capsys, monkeypatch)
    assert 'PRIVATE' not in json.dumps(review)
    assert review['selection']['label'] == c.project.name
    assert review['quick_connect']['name_discovery']['reason'] == 'origin_invalid'
    assert review['quick_connect']['project_name_source'] == 'git_worktree'


def make_worktree(c, git, monkeypatch, *, per_worktree=False):
    primary = c.project
    init(git, primary, None if per_worktree else 'https://example.invalid/team/linked-name.git')
    git(primary, 'commit', '--allow-empty', '-m', 'Owned synthetic fixture')
    if per_worktree:
        git(primary, 'config', '--local', 'extensions.worktreeConfig', 'true')
    target = primary.parent / 'linked-physical-root'
    target.mkdir()  # new empty directory; never remove an existing tree
    git(primary, 'worktree', 'add', '--detach', str(target), 'HEAD', supported=True)
    if per_worktree:
        git(target, 'config', '--worktree', 'remote.origin.url', 'https://example.invalid/team/per-worktree-name.git', supported=True)
    assert (target / '.git').is_file()
    monkeypatch.chdir(target)
    c.project = target


def test_d12_real_linked_worktree_keeps_execution_root(quick_cli, git_local, monkeypatch, capsys):
    c = quick_cli
    make_worktree(c, git_local, monkeypatch)
    review = actual_review(c, capsys, monkeypatch)
    assert review['selection']['label'] == 'linked-name'
    assert review['quick_connect']['project_name_source'] == 'git_origin'
    configure(c, capsys, review, 'linked-name')


def test_d13_per_worktree_origin_is_read_without_shared_origin(quick_cli, git_local, monkeypatch, capsys):
    c = quick_cli
    make_worktree(c, git_local, monkeypatch, per_worktree=True)
    review = actual_review(c, capsys, monkeypatch)
    assert review['selection']['label'] == 'per-worktree-name'
    assert review['quick_connect']['project_name_source'] == 'git_origin'
    configure(c, capsys, review, 'per-worktree-name')


def test_d14_nested_repository_origin_wins(quick_cli, git_local, monkeypatch, capsys):
    c = quick_cli
    outer = c.project
    init(git_local, outer, 'https://example.invalid/team/outer-name.git')
    inner = outer / 'inner-physical'
    inner.mkdir()
    init(git_local, inner, 'https://example.invalid/team/inner-name.git')
    monkeypatch.chdir(inner)
    c.project = inner
    review = actual_review(c, capsys, monkeypatch)
    assert review['selection']['label'] == 'inner-name'
    configure(c, capsys, review, 'inner-name')


def test_d21_hostile_git_directory_environment_cannot_redirect_discovery(quick_cli, git_local, monkeypatch, capsys):
    c = quick_cli
    init(git_local, c.project, 'https://example.invalid/team/chosen-name.git')
    hostile = c.project.parent / 'own-hostile-target'
    hostile.mkdir()
    init(git_local, hostile, 'https://PRIVATE.invalid/team/wrong-name.git')
    monkeypatch.setenv('GIT_DIR', str(hostile / '.git'))
    monkeypatch.setenv('GIT_WORK_TREE', str(hostile))
    review = actual_review(c, capsys, monkeypatch)
    assert review['selection']['label'] == 'chosen-name' and 'PRIVATE' not in json.dumps(review)
    configure(c, capsys, review, 'chosen-name')


def test_d22_cwd_and_ancestor_project_git_are_never_launched(quick_cli, git_local, monkeypatch, capsys):
    from okto_nexus.adapters.outbound import git_project_hint
    c = quick_cli
    outer = c.project
    init(git_local, outer)
    inner = outer / 'inner-invocation'
    inner.mkdir()
    bins = [inner / 'bin', outer / 'tools']
    for directory in bins:
        directory.mkdir()
        (directory / 'git.exe').write_bytes(b'Untrusted fixture executable, must never be launched')
    marker = outer / 'untrusted-git-launch-attempt.marker'
    real_popen = subprocess.Popen
    def launch(argv, *args, **kwargs):
        if Path(argv[0]).resolve() in {(directory / 'git.exe').resolve() for directory in bins}:
            marker.write_text('Untrusted candidate launch attempted')
            pytest.fail('Project-controlled Git executable reached subprocess.Popen')
        return real_popen(argv, *args, **kwargs)
    monkeypatch.setattr(git_project_hint.subprocess, 'Popen', launch)
    monkeypatch.setenv('PATH', os.pathsep.join(map(str, bins)))
    monkeypatch.chdir(inner)
    c.project = inner
    review = actual_review(c, capsys, monkeypatch)
    assert review['selection']['label'] == inner.name
    assert review['quick_connect']['name_discovery']['reason'] == 'git_unavailable'
    assert not marker.exists()
