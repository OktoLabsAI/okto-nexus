"""A first handoff in a local project creates its workspace atomically."""
import pytest
from test_pr34_remediation import runtime as runtime_fixture, tool
from okto_nexus.domain.ids import resolve_workspace_id

runtime = runtime_fixture


@pytest.mark.parametrize('target', [dict(strategy='direct', agent_id='worker'), dict(strategy='broadcast')])
def test_first_project_handoff_registers_workspace_with_notification(runtime, target):
    deps, client, root, _, _, caller = runtime
    workspace = resolve_workspace_id(root)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert deps.repos.workspaces.get(uow, workspace) is None
    response = tool(client, caller, 'handoff_create', dict(project_root=root, from_agent_id='caller',
        target=target, visibility='eligible', payload='First work in this project'))
    assert response['ok'], response
    assert response['data']['workspace_created'] is True
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert deps.repos.workspaces.get(uow, workspace) is not None
        assert uow.connection.execute('SELECT workspace_id FROM handoffs').fetchone()[0] == workspace
        assert uow.connection.execute('SELECT COUNT(*) FROM message_deliveries').fetchone()[0] == (target['strategy'] == 'direct')
        assert not uow.connection.execute('PRAGMA foreign_key_check').fetchall()


def test_first_workspace_rolls_back_with_failed_handoff_write(runtime, monkeypatch):
    deps, client, root, _, _, caller = runtime
    original = deps.repos.handoffs.create
    reached = []
    def cut(*args, **kwargs):
        original(*args, **kwargs)
        reached.append(True)
        raise OSError('Injected failure after handoff insert')
    monkeypatch.setattr(deps.repos.handoffs, 'create', cut)
    response = tool(client, caller, 'handoff_create', dict(project_root=root, from_agent_id='caller',
        target=dict(strategy='direct', agent_id='worker'), visibility='eligible', payload='Rolled back'))
    assert not response['ok'] and reached == [True], response
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert deps.repos.workspaces.get(uow, resolve_workspace_id(root)) is None
        for table in ('handoffs', 'handoff_authorization_receipts', 'messages', 'message_deliveries'):
            assert uow.connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] == 0
