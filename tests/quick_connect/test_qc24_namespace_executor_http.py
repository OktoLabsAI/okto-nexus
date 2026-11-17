"""E06: canonical subject registration proves the second executor's origin."""
from copy import deepcopy
import uuid
import pytest

from test_qc24_namespace_http import local_setup as local_setup,finish_http,reserve,write_proof,BASE
from test_public_connection_ids import public_request
from test_connection_setup import request_for
from test_connection_setup_recovery import snapshot


def test_e06_same_workspace_id_collision_spans_two_canonically_registered_executors(local_setup,monkeypatch):
    setup=local_setup
    context,legacy=request_for(setup)
    existing=finish_http(setup,legacy,monkeypatch)
    workspace=existing['binding']['workspace_id']
    context,first=public_request(setup,name='reviewer',workspace_id=workspace)
    local=reserve(setup,first)
    registered=setup[2].post('/v1/connections/executors:register',headers=setup[3]['subject'],
        json=dict(client_intent_id='qc24-register-second',connector_id='qc24-owned-remote',
                  label='Owned inert remote executor',control_capabilities=[]))
    assert registered.status_code==201,registered.text
    remote=registered.json()
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        server_id=uow.connection.execute('SELECT server_id FROM execution_installation WHERE singleton=1').fetchone()[0]
    assert remote['server_id']==server_id
    assert remote['executor_id']!=first['executor_id']
    proof=setup[2].get(BASE+'/project-context',headers=setup[3]['operator'],
        params=dict(executor_id=remote['executor_id'],workspace_id=workspace))
    assert proof.status_code==200,proof.text
    assert proof.json()['executor_id']==remote['executor_id'] and proof.json()['workspace_id']==workspace
    second=deepcopy(first)
    second.update(executor_id=remote['executor_id'],client_intent_id='qc24-second-'+uuid.uuid4().hex)
    second.pop('candidate_ref')
    second.pop('inventory_revision')
    # Setup's configuration schema retains a required string root, while the
    # remote namespace proof is solely the selected canonical workspace. No
    # local path lookup may turn the proposed text into remote authority.
    second['configuration'].update(execution_location='remote',runtime_enabled=False)
    from okto_nexus.application import connection_project_context as projects
    monkeypatch.setattr(projects,'directory_identity',lambda *args:
        pytest.fail('Remote namespace reservation must not stat a local directory'))
    second['public_connection'].update(reservation_ref='pcr_'+uuid.uuid4().hex,
        project_revision=proof.json()['project_revision'])
    before=snapshot(setup[0])
    denied=setup[2].post(BASE+'/public-ids/reserve',headers=setup[3]['operator'],
        json=dict(approved=True,request=second))
    assert denied.status_code==409,denied.text
    assert denied.json()['error']['code']=='CONNECT_ID_PENDING'
    assert snapshot(setup[0])==before
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        executors=[dict(r) for r in uow.connection.execute(
            'SELECT executor_id,kind,registered_by_agent_id FROM execution_executors')]
        assert {r['executor_id'] for r in executors}=={first['executor_id'],remote['executor_id']}
        registered_row=next(r for r in executors if r['executor_id']==remote['executor_id'])
        assert registered_row['kind']=='remote' and registered_row['registered_by_agent_id']=='subject'
        rows=list(uow.connection.execute('SELECT reservation_ref,workspace_id FROM connection_public_ids'))
        assert [tuple(r) for r in rows]==[(local['reservation_ref'],workspace)]
    write_proof('e06-proof.json',dict(workspace_id=workspace,connect_id='reviewer',
        executor_count=2,second_executor_origin='canonical subject-authorized POST executors:register',
        new_reservation_refused=True,collision_code='CONNECT_ID_PENDING',canonical_refs_or_grants_unchanged=True,
        remote_transport_or_daemon_started=False))


# Explicit public exports include pytest fixtures used through injection.
__all__ = ['BASE', 'deepcopy', 'finish_http', 'local_setup', 'public_request', 'pytest', 'request_for', 'reserve', 'snapshot', 'test_e06_same_workspace_id_collision_spans_two_canonically_registered_executors', 'uuid', 'write_proof']
