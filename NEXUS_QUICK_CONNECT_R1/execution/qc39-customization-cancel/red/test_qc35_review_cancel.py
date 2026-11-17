"""Exact C02/G08 new-review cancellation; real CLI/HTTP, inert lifecycle/Test peers."""
from copy import deepcopy
import pytest
import json
import os
from pathlib import Path
from types import SimpleNamespace

from test_quick_connect_cli import quick_cli as quick_cli,terminal as terminal,checking as checking,local_setup as local_setup,isolated_provider_environment as isolated_provider_environment
from okto_nexus.adapters.inbound.cli import connect
from okto_nexus.adapters.outbound import git_project_hint


def counts(c):
    tables=('workspaces','connection_public_ids','runtime_execution_grants','execution_bindings',
            'connection_setup_commits','execution_operations','execution_sessions')
    with c.t.deps.connection_factory.unit_of_work(write=False) as uow:
        return {table:uow.connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in tables}


@pytest.mark.parametrize('mode',['quick','legacy'])
def test_c02_g08_new_unmapped_cwd_basename_review_cancel_emits_honest_final_state(quick_cli,monkeypatch,capsys,mode):
    c=quick_cli
    assert Path.cwd()==c.project and not (c.project/'.git').exists()
    def no_git(*args,**kwargs):
        pytest.fail('Legacy explicit selectors must not discover Git')
    monkeypatch.setattr(git_project_hint,'_trusted_git',c.trusted_git if mode=='quick' else no_git)
    monkeypatch.setattr(connect.sys,'stdin',SimpleNamespace(isatty=lambda:True))
    displayed=[]
    original_display=connect._display
    def display(value,as_json):
        displayed.append(deepcopy(value))
        return original_display(value,as_json)
    monkeypatch.setattr(connect,'_display',display)
    before=counts(c)
    assert set(before.values())=={0}
    retained=[]
    review_stdout=[]
    def answer(prompt):
        assert 'Confirm this review' in prompt
        assert not retained
        captured=capsys.readouterr()
        review_stdout.append(captured.out)
        profile=c.home/'terminal/profiles/cancel-review.json'
        saved=json.loads(profile.read_text())
        assert saved['state']=='review'
        assert saved['selection']['label']==c.project.name
        assert saved['selection']['project']==str(c.project)
        if mode=='quick':
            assert saved['selection']['quick_connect']['project_name_source']=='directory'
            assert saved['selection']['quick_connect']['name_discovery']['status']=='fallback'
        else:
            assert 'quick_connect' not in saved['selection']
            assert saved['selection']['client']=='codex'
            assert 'public_connection' not in saved['request']
        assert saved['request']['workspace_id'] is None
        assert saved['request']['configuration']['workspace_label']==c.project.name
        assert saved['request']['configuration']['workspace_root']==str(c.project)
        assert 'Workspace: create '+c.project.name in captured.out
        if mode=='quick':
            assert 'Project name source: directory' in captured.out
            assert 'ID do Harness (proposed): codex' in captured.out
        else:
            assert 'Project name source:' not in captured.out
            assert 'ID do Harness (proposed):' not in captured.out
        assert 'Project: '+str(c.project) in captured.out
        assert counts(c)==before and c.t.probes==c.t.turns==[]
        assert c.lifecycle==['ensure']
        retained.append(profile.read_bytes())
        print(captured.out,end='')
        return 'n'
    monkeypatch.setattr('builtins.input',answer)
    command=['connect','codex','--profile','cancel-review','--no-chat'] if mode=='quick' else [
        'connect','--client','codex','--project',str(c.project),'--profile','cancel-review','--no-chat']
    assert c.run(command)==0
    capsys.readouterr()
    profile=c.home/'terminal/profiles/cancel-review.json'
    assert profile.read_bytes()==retained[0]
    assert counts(c)==before and c.t.probes==c.t.turns==[]
    out=Path(os.environ['QC_DERIVATIVE_OUTPUT'])
    c02=dict(mode=mode,cwd_unmapped=True,git_metadata_usable=False,basename_suggestion_identified=mode=='quick',legacy_selectors_preserved=mode=='legacy',
        new_workspace_offer_printed=True,physical_root_preserved=True,
        before_consent_counts=before,after_cancel_counts=counts(c),tests=0,probes=0,
        checkpoint_preserved=True,last_display_state=displayed[-1]['state'])
    (out/('review-proof-'+mode+'.json')).write_text(json.dumps(c02,indent=2)+'\n')
    final=displayed[-1]
    assert final['state']=='canceled',{'last_display_state':final['state']}
    assert final['lifecycle_requested'] is True
    assert final['canonical_metadata_revalidation_requested'] is (mode=='quick')
    assert final['effects_started'] is None
    (out/('g08-proof-'+mode+'.json')).write_text(json.dumps(dict(state='canceled',lifecycle_requested=True,
        canonical_metadata_revalidation_requested=mode=='quick',effects_started=None,
        checkpoint_preserved=True,ensure_calls=1,tests=0,probes=0),indent=2)+'\n')


@pytest.mark.parametrize('cancel_at', ['c', 'empty', 'picker_eof', 'field_eof', 'review_eof'])
def test_customize_cancel_and_review_eof_preserve_review_and_emit_honest_state(quick_cli, monkeypatch, capsys, cancel_at):
    c = quick_cli
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(git_project_hint, '_trusted_git', c.trusted_git)
    before = counts(c)
    profile = c.home / 'terminal/profiles/customize-cancel.json'
    retained, prompts, displayed = [], [], []
    original_display = connect._display

    def display(value, as_json):
        displayed.append(deepcopy(value))
        original_display(value, as_json)

    def read(prompt):
        prompts.append(prompt)
        assert len(prompts) <= 3, 'Unexpected extra customization prompt'
        if len(prompts) == 1:
            assert prompt == 'Confirm this review, including the model connection test? [y/customize/cancel] '
            retained.append(profile.read_bytes())
            assert counts(c) == before and c.t.turns == c.t.probes == []
            if cancel_at == 'review_eof':
                raise EOFError
            return 'customize'
        if len(prompts) == 2:
            assert prompt == 'Customize: '
            if cancel_at == 'picker_eof':
                raise EOFError
            return {'c': 'c', 'empty': '', 'field_eof': '1'}[cancel_at]
        assert cancel_at == 'field_eof' and prompt == 'New ID do Harness: '
        raise EOFError

    monkeypatch.setattr(connect, '_display', display)
    monkeypatch.setattr('builtins.input', read)
    assert c.run(['connect', 'codex', 'Cancel customization', '--profile', 'customize-cancel', '--no-chat']) == 0
    capsys.readouterr()
    assert profile.read_bytes() == retained[0]
    assert len(list((c.home / 'terminal/profiles').glob('*.json'))) == 1
    assert counts(c) == before and c.t.turns == c.t.probes == []
    final = displayed[-1]
    assert final['state'] == 'canceled'
    assert final['lifecycle_requested'] is True
    assert final['canonical_metadata_revalidation_requested'] is True
    assert final['effects_started'] is None


def test_resume_eof_cancels_honestly_without_replaying_test(quick_cli, monkeypatch, capsys):
    c = quick_cli
    assert c.run(['connect', 'codex', 'Resume EOF', '--profile', 'resume-eof', '--no-chat', '--json']) == 3
    result = json.loads(capsys.readouterr().out)
    assert result['state'] == 'review'
    revision = result['review_revision']
    assert c.run(['connect', '--profile', 'resume-eof', '--approve', revision, '--no-chat', '--json']) == 0
    assert json.loads(capsys.readouterr().out)['state'] == 'configured'
    before = counts(c)
    profile = c.home / 'terminal/profiles/resume-eof.json'
    retained = profile.read_bytes()
    turns, probes = list(c.t.turns), list(c.t.probes)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    displayed, prompts = [], []
    original_display = connect._display

    def display(value, as_json):
        displayed.append(deepcopy(value))
        original_display(value, as_json)

    def read(prompt):
        prompts.append(prompt)
        assert prompts == ['Confirm resume? [y/N] ']
        raise EOFError

    monkeypatch.setattr(connect, '_display', display)
    monkeypatch.setattr('builtins.input', read)
    assert c.run(['connect', '--profile', 'resume-eof', '--no-chat']) == 0
    capsys.readouterr()
    assert profile.read_bytes() == retained
    assert counts(c) == before and c.t.turns == turns and c.t.probes == probes
    final = displayed[-1]
    assert final['state'] == 'canceled'
    assert final['lifecycle_requested'] is True
    assert final['canonical_metadata_revalidation_requested'] is True
    assert final['effects_started'] is None


# Explicit public exports include pytest fixtures used through injection.
__all__ = ['Path', 'SimpleNamespace', 'checking', 'connect', 'counts', 'deepcopy', 'git_project_hint', 'isolated_provider_environment', 'json', 'local_setup', 'os', 'pytest', 'quick_cli', 'terminal', 'test_c02_g08_new_unmapped_cwd_basename_review_cancel_emits_honest_final_state']
