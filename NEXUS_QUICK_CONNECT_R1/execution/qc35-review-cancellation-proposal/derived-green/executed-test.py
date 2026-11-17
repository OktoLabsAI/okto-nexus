"""Exact C02/G08 new-review cancellation; real CLI/HTTP, inert lifecycle/Test peers."""
from copy import deepcopy
import json
import os
from pathlib import Path
from types import SimpleNamespace

from test_quick_connect_cli import quick_cli,terminal,checking,local_setup,isolated_provider_environment
from okto_nexus.adapters.inbound.cli import connect
from okto_nexus.adapters.outbound import git_project_hint


def counts(c):
    tables=('workspaces','connection_public_ids','runtime_execution_grants','execution_bindings',
            'connection_setup_commits','execution_operations','execution_sessions')
    with c.t.deps.connection_factory.unit_of_work(write=False) as uow:
        return {table:uow.connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in tables}


def test_c02_g08_new_unmapped_cwd_basename_review_cancel_emits_honest_final_state(quick_cli,monkeypatch,capsys):
    c=quick_cli
    assert Path.cwd()==c.project and not (c.project/'.git').exists()
    monkeypatch.setattr(git_project_hint,'_trusted_git',c.trusted_git)
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
        assert saved['selection']['quick_connect']['project_name_source']=='directory'
        assert saved['selection']['quick_connect']['name_discovery']['status']=='fallback'
        assert saved['request']['workspace_id'] is None
        assert saved['request']['configuration']['workspace_label']==c.project.name
        assert saved['request']['configuration']['workspace_root']==str(c.project)
        assert 'Workspace: create '+c.project.name in captured.out
        assert 'Project name source: directory' in captured.out
        assert 'Project: '+str(c.project) in captured.out
        assert 'ID do Harness (proposed): codex' in captured.out
        assert counts(c)==before and c.t.probes==c.t.turns==[]
        assert c.lifecycle==['ensure']
        retained.append(profile.read_bytes())
        print(captured.out,end='')
        return 'n'
    monkeypatch.setattr('builtins.input',answer)
    assert c.run(['connect','codex','--profile','cancel-review','--no-chat'])==0
    capsys.readouterr()
    profile=c.home/'terminal/profiles/cancel-review.json'
    assert profile.read_bytes()==retained[0]
    assert counts(c)==before and c.t.probes==c.t.turns==[]
    out=Path(os.environ['QC_DERIVATIVE_OUTPUT'])
    c02=dict(cwd_unmapped=True,git_metadata_usable=False,basename_suggestion_identified=True,
        new_workspace_offer_printed=True,physical_root_preserved=True,
        before_consent_counts=before,after_cancel_counts=counts(c),tests=0,probes=0,
        checkpoint_preserved=True,last_display_state=displayed[-1]['state'])
    (out/'c02-proof.json').write_text(json.dumps(c02,indent=2)+'\n')
    final=displayed[-1]
    assert final['state']=='canceled',{'last_display_state':final['state']}
    assert final['lifecycle_requested'] is True
    assert final['canonical_metadata_revalidation_requested'] is True
    assert final['effects_started'] is None
    (out/'g08-proof.json').write_text(json.dumps(dict(state='canceled',lifecycle_requested=True,
        canonical_metadata_revalidation_requested=True,effects_started=None,
        checkpoint_preserved=True,ensure_calls=1,tests=0,probes=0),indent=2)+'\n')
