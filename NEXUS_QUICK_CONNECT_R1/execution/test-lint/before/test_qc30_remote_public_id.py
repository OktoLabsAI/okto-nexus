"""Remote human CLI over one real embedded Server fixture, no real host pair."""
import json
import os
from pathlib import Path
from urllib.parse import unquote

import pytest
from test_remote_operator_terminal import remote,work,connected_local,local_setup,qualified_contract
from okto_nexus.adapters.inbound.cli import connect,work as cli_work
from okto_nexus.adapters.inbound.cli.main import main
from okto_nexus.adapters.outbound import git_project_hint

BASE='/api/v1/runtime-management/connections'
KEYS=('server_id','executor_id','binding_id','endpoint_id','agent_id','workspace_id','workspace_binding_id')
TABLES=('connection_setup_commits','execution_bindings','agent_endpoints','runtime_execution_grants',
        'agent_execution_policies','agent_runtime_overrides','connection_public_ids','connection_project_drafts',
        'execution_operations','execution_sessions','execution_realizations','execution_workspace_bindings')


def rows(t):
    with t.deps.connection_factory.unit_of_work(write=False) as uow:
        return {table:sorted([tuple(r) for r in uow.connection.execute('SELECT * FROM '+table)],key=repr)
                for table in TABLES}


def test_i03_public_id_remote_operator_reuses_exact_binding_without_local_root_or_effects(remote,tmp_path,monkeypatch,capsys):
    r=remote
    call=r.profile.client()
    binding=r.t.binding
    workspace=binding['workspace_id']
    catalog=call('GET',BASE+'/catalog?workspace_id='+workspace)
    item,=[item for item in catalog['items'] if item['binding_id']==binding['binding_id']]
    reference={key:item[key] for key in KEYS}
    assert all(isinstance(value,str) and value for value in reference.values())
    before_association=rows(r.t)
    associated=call('POST',BASE+'/public-ids/associate-existing',dict(approved=True,
        client_intent_id='qc30-associate-exact',connect_id='remote-codex',expected_binding_ref=reference,
        expected_binding_revision=item['binding_revision']))
    assert associated['state']=='bound' and associated['canonical_ref']==reference
    after_association=rows(r.t)
    assert [table for table in TABLES if before_association[table]!=after_association[table]]==['connection_public_ids']
    # Read the canonical execution configuration before taking the stable
    # observation baseline; do not use operator CWD to construct a remote root.
    canonical=call('GET',BASE+'/setup/'+reference['agent_id']+'?binding_id='+reference['binding_id'])
    execution_root=canonical['folders']['workspace_root']
    operator_cwd=tmp_path/'different-operator-cwd'
    operator_cwd.mkdir()
    assert str(operator_cwd.resolve())!=execution_root
    monkeypatch.chdir(operator_cwd)
    def forbidden(*args,**kwargs):
        pytest.fail('Remote public-ID resume attempted local Server/Git/input/Test',pytrace=False)
    monkeypatch.setattr(connect,'resolve_local_service',forbidden)
    monkeypatch.setattr(cli_work,'resolve_local_service',forbidden)
    monkeypatch.setattr(connect,'LocalOperatorHTTP',forbidden)
    monkeypatch.setattr(git_project_hint,'discover_project_name',forbidden)
    monkeypatch.setattr(git_project_hint,'_trusted_git',forbidden)
    monkeypatch.setattr('builtins.input',forbidden)
    monkeypatch.setattr(r.t.app.state.connection_tests,'run',forbidden)
    before=rows(r.t)
    first_call=len(r.bridge.calls)
    capsys.readouterr()
    command=['connect','--operator-profile','remote','--workspace-id',workspace,'--id','remote-codex',
        '--home',str(r.profile.home),'--profile','qc30-remote','--json','--no-chat']
    assert main(command)==0
    observed=json.loads(capsys.readouterr().out)
    assert observed['topology']=='remote_operator' and observed['execution_location']=='remote'
    assert observed['configuration']['folders']['workspace_root']==execution_root
    assert observed['configuration']==canonical
    assert observed['public_connection']['canonical_ref']==reference
    quick=observed['quick_connect']
    assert quick['status']=='connected' and quick['operation']=='reused'
    assert quick['connect_id']=='remote-codex' and quick['canonical_reference']==reference
    assert quick['execution_location']=='remote' and 'project_root' not in quick
    assert quick['cwd_resolution']['project_root'] is None and quick['cwd_resolution']['source']=='remote'
    assert rows(r.t)==before and r.t.native.opens==0
    wire=r.bridge.calls[first_call:]
    assert wire and all(request.method=='GET' and request.data is None for request in wire)
    assert all(str(operator_cwd.resolve()) not in unquote(request.full_url) for request in wire)
    saved=json.loads((r.profile.home/'terminal/profiles/qc30-remote.json').read_text())
    assert saved['state']=='done' and saved['remote_scope']['binding_id']==reference['binding_id']
    assert {key:saved['result']['binding'][key] for key in KEYS}==reference
    assert saved['selection']['public_connection']['connect_id']=='remote-codex'
    assert not (r.profile.home/'nexus.db').exists() and not (r.profile.home/'service-context.json').exists()
    with r.t.deps.connection_factory.unit_of_work(write=False) as uow:
        kind=uow.connection.execute('SELECT kind FROM execution_executors WHERE executor_id=?',
            (reference['executor_id'],)).fetchone()[0]
        assert kind=='embedded'
    # Only public refs/facts, never cookies, password, vault or raw HTTP headers.
    proof=dict(canonical_reference=reference,connect_id='remote-codex',
        topology='remote_operator',operator_view_execution_location='remote',
        canonical_configuration_unchanged=True,executor_kind='embedded',two_physical_computers=False,
        execution_root_preserved=True,operator_cwd_distinct=True,local_server_and_git_forbidden=True,
        http_methods=[request.method for request in wire],operator_cwd_transferred=False,
        compared_tables=list(TABLES),tables_unchanged=True,native_opens=0,new_reservations=0,new_tests=0,
        new_grants=0,new_operations=0,new_sessions=0)
    if os.environ.get('QC_DERIVATIVE_OUTPUT'):
        (Path(os.environ['QC_DERIVATIVE_OUTPUT'])/'remote-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
