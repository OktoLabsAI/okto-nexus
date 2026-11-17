"""Explicit-name D26 variant, own local Git and canonical Finish recovery."""
import json
import os
from pathlib import Path
import subprocess

import pytest
from test_quick_connect_cli import (  # noqa: F401
    checking as checking, invoke, isolated_provider_environment as isolated_provider_environment, local_setup as local_setup, quick_cli as quick_cli, terminal as terminal,
)
from test_quick_connect_extra_scenarios import canonical_snapshot, public_row


def test_d26_explicit_name_finish_recovery_ignores_changed_local_git(quick_cli, capsys, monkeypatch, tmp_path):
    from okto_nexus.adapters.outbound import git_project_hint
    c = quick_cli
    git = Path('C:/Program Files/Git/cmd/git.exe')
    if not git.is_file():
        pytest.skip('The allowlisted Git executable is unavailable; no installation attempted.')
    hooks = tmp_path / 'empty-hooks'
    templates = tmp_path / 'empty-templates'
    hooks.mkdir()
    templates.mkdir()
    env = dict(os.environ)
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
               GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0')
    commands = []
    def local_git(*args):
        argv = [str(git), '-c', 'core.hooksPath=' + str(hooks),
                '-c', 'init.templateDir=' + str(templates), '-c', 'protocol.allow=never', *args]
        result = subprocess.run(argv, cwd=c.project, env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=5, shell=False)
        commands.append(dict(argv=argv, exit_code=result.returncode))
        assert result.returncode == 0, (args, result.stdout, result.stderr)
        return result.stdout.strip()
    local_git('init')
    local_git('config', '--local', 'remote.origin.url', 'https://example.invalid/team/original.git')
    local_git('symbolic-ref', 'HEAD', 'refs/heads/before-plan')
    base = ['connect', 'codex', 'Explicit Frozen Project', '--profile', 'git-recovery', '--json']
    review = invoke(c, capsys, [*base, '--plan'])
    assert review['quick_connect']['project_name_source'] == 'explicit'
    assert review['selection']['project'] == str(c.project)
    c.t.fault.after = 'setup:finish'
    uncertain = invoke(c, capsys, [*base, '--approve', review['review_revision']], expected=3)
    assert uncertain['code'] == 'OUTCOME_UNKNOWN'
    profile = c.home / 'terminal/profiles/git-recovery.json'
    pending = json.loads(profile.read_text())
    assert pending['state'] == 'finish'
    request = pending['request']
    with c.t.deps.connection_factory.unit_of_work(write=False) as uow:
        receipt = uow.connection.execute('SELECT result_json FROM connection_setup_commits WHERE client_intent_id=?',
                                         (request['client_intent_id'],)).fetchone()
        assert receipt is not None
        committed = json.loads(receipt[0])
    reference = committed['public_connection']['canonical_ref']
    assert len(reference) == 7
    old_public = public_row(c, 'codex', reference['workspace_id'])
    before = canonical_snapshot(c)
    turns, probes = tuple(c.t.turns), tuple(c.t.probes)
    local_git('config', '--local', 'remote.origin.url', 'https://example.invalid/changed/other.git')
    local_git('symbolic-ref', 'HEAD', 'refs/heads/after-finish')
    assert local_git('config', '--local', '--get', 'remote.origin.url') == 'https://example.invalid/changed/other.git'
    assert local_git('symbolic-ref', 'HEAD') == 'refs/heads/after-finish'
    def forbidden(*args, **kwargs):
        pytest.fail('Recovery must use the retained explicit selection, not rerun Git discovery')
    monkeypatch.setattr(git_project_hint, 'discover_project_name', forbidden)
    result = invoke(c, capsys, ['connect', '--profile', 'git-recovery', '--json'])
    repaired = json.loads(profile.read_text())
    assert repaired['state'] == 'done' and repaired['request'] == request
    assert repaired['review_request'] == pending['review_request']
    assert repaired['selection'] == pending['selection']
    assert result['quick_connect']['canonical_reference'] == reference
    assert result['quick_connect']['project_name'] == 'Explicit Frozen Project'
    assert result['quick_connect']['project_root'] == str(c.project)
    assert result['quick_connect']['connect_id'] == 'codex'
    assert result['setup_run_id'] == request['client_intent_id']
    assert result['binding_id'] == reference['binding_id']
    assert result['session_state'] == 'not_checked' and result['work_state'] == 'not_submitted'
    assert canonical_snapshot(c) == before
    assert public_row(c, 'codex', reference['workspace_id']) == old_public
    assert tuple(c.t.turns) == turns and tuple(c.t.probes) == probes
    assert all(row['exit_code'] == 0 for row in commands)


# Explicit public exports include pytest fixtures used through injection.
__all__ = ['Path', 'canonical_snapshot', 'checking', 'invoke', 'isolated_provider_environment', 'json', 'local_setup', 'os', 'public_row', 'pytest', 'quick_cli', 'subprocess', 'terminal', 'test_d26_explicit_name_finish_recovery_ignores_changed_local_git']
