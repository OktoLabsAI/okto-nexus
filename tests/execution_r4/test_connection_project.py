"""Approved mappings, never folder-name authority, nominate shared projects."""
import pytest

from okto_nexus.adapters.inbound.cli.connection_choices import ConnectionChoice, ConnectionChoiceCatalog
from okto_nexus.adapters.inbound.cli.connection_project import project_workspace_choices, pick_project_workspace
from okto_nexus.application.terminal_connection import ConnectionError


def catalog(*names):
    return ConnectionChoiceCatalog(tuple(ConnectionChoice(name, 'agent-' + name, 'codex',
        'binding-' + name, None, 'done', False, False, False, False, False, False) for name in names), (), True)


def response(project, workspace='workspace', *, location='local'):
    def call(method, path):
        assert method == 'GET' and '/connections/setup/agent-' in path
        name = path.split('/connections/setup/agent-')[1].split('?')[0]
        return dict(connections=[dict(binding_id='binding-' + name,
            workspace_id=workspace + name, execution_location=location)],
            folders=dict(workspace_root=project, workspace_label='Approved ' + name))
    return call


def test_legacy_missing_workspace_is_resolved_from_authorized_binding(tmp_path):
    rows = project_workspace_choices(response(str(tmp_path)), catalog('a'), str(tmp_path))
    assert rows[0].workspace_id == 'workspacea'
    assert pick_project_workspace(rows, read=lambda p: pytest.fail('unique approved project should be suggested')) == 'workspacea'


def test_multiple_approved_workspaces_require_explicit_choice(tmp_path):
    rows = project_workspace_choices(response(str(tmp_path)), catalog('a', 'b'), str(tmp_path))
    answers = iter(['0', '2'])
    assert pick_project_workspace(rows, read=lambda p: next(answers), write=lambda p: None) == 'workspaceb'


@pytest.mark.parametrize('kind', ['root', 'remote', 'unauthorized', 'missing'])
def test_path_or_label_alone_cannot_authorize_project(tmp_path, kind):
    good = response(str(tmp_path))
    def call(method, path):
        if kind == 'unauthorized':
            raise ConnectionError('PERMISSION_DENIED', 'Not authorized')
        value = good(method, path)
        if kind == 'root':
            value['folders']['workspace_root'] = str(tmp_path / 'other')
        if kind == 'remote':
            value['connections'][0]['execution_location'] = 'remote'
        if kind == 'missing':
            value['connections'] = []
        return value
    with pytest.raises(ConnectionError):
        project_workspace_choices(call, catalog('a'), str(tmp_path))
