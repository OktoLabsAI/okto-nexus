"""Resolve a shared project only through authorized canonical binding reads."""
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from ....application.terminal_connection import ConnectionError, PREFIX, _same_local_path


@dataclass(frozen=True)
class ProjectWorkspaceChoice:
    workspace_id: str
    label: str


def project_workspace_choices(call, catalog, project):
    """Local shortcut paths nominate bindings, never grant workspace access.

    Current setup GET authorizes the operator and returns the binding's approved
    workspace and host mapping. Missing/changed provenance is a refusal rather
    than permission to create a substitute project.
    """
    if not catalog.complete:
        raise ConnectionError('PROJECT_SELECTION_UNCONFIRMED', 'Inspect incomplete connection metadata before choosing a project.')
    found = {}
    for choice in catalog.choices:
        if not choice.binding_id:
            continue  # An unfinished setup is not an approved project mapping.
        path = '/connections/setup/' + quote(choice.agent_id, safe='') + '?' + urlencode({'binding_id': choice.binding_id})
        current = call('GET', PREFIX + path)
        matches = [row for row in current.get('connections', ()) if row.get('binding_id') == choice.binding_id]
        if (len(matches) != 1 or matches[0].get('execution_location') != 'local'
                or not _same_local_path(current.get('folders', {}).get('workspace_root'), project)):
            raise ConnectionError('PROJECT_MAPPING_CHANGED', 'The existing connection no longer proves this approved local project mapping.')
        workspace_id = matches[0].get('workspace_id')
        if not isinstance(workspace_id, str) or not workspace_id:
            raise ConnectionError('PROJECT_SELECTION_UNCONFIRMED', 'The canonical connection has no confirmed project.')
        label = current.get('folders', {}).get('workspace_label') or workspace_id
        found[workspace_id] = ProjectWorkspaceChoice(workspace_id, label)
    return tuple(found[key] for key in sorted(found))


def pick_project_workspace(choices, *, read=input, write=print):
    if len(choices) == 1:
        return choices[0].workspace_id
    write('Choose the existing Nexus project for this additional connection:')
    for index, row in enumerate(choices, 1):
        write(f'{index}. {row.label} ({row.workspace_id})')
    write('c. Cancel')
    while True:
        try:
            answer = read('Project: ').strip().lower()
        except EOFError:
            return None
        if answer in {'', 'c'}:
            return None
        if answer.isdecimal() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1].workspace_id
        write('Select a displayed project or c.')
