"""Authorized project resolution for Quick Connect; hints never select identity."""
from pathlib import Path
import re
from urllib.parse import quote, urlencode

from ....application.terminal_connection import ConnectionError, PREFIX, _same_local_path

MAX_PAGES = 32


def _get(call, path, **query):
    return call('GET', PREFIX + path + ('?' + urlencode({k: v for k, v in query.items()
        if v is not None}) if query else ''))


def local_executor(call, agent_id):
    rows, cursor, seen = [], None, set()
    for _ in range(MAX_PAGES):
        page = _get(call, '/agents/' + quote(agent_id, safe='') + '/executors',
            limit=100, after_executor_id=cursor)
        if type(page) is not dict or type(page.get('items')) is not list or type(page.get('has_more')) is not bool:
            raise ConnectionError('INVENTORY_UNCONFIRMED', 'Execution host inventory is incomplete.')
        rows.extend(row for row in page['items'] if row.get('kind') == 'embedded')
        if not page['has_more']:
            break
        cursor = page.get('next_executor_id')
        if not cursor or cursor in seen:
            raise ConnectionError('INVENTORY_UNCONFIRMED', 'Execution host inventory changed.')
        seen.add(cursor)
    else:
        raise ConnectionError('INVENTORY_UNCONFIRMED', 'Select an explicit execution host.')
    if len(rows) != 1:
        raise ConnectionError('LOCAL_EXECUTOR_UNAVAILABLE', 'No unique local execution host is available.')
    return rows[0]['executor_id']


def project_directory(call, server_id):
    """Consume the complete logical project directory, including empty projects."""
    rows, cursor, revision, total, seen, cursors = [], None, None, None, set(), set()
    for _ in range(MAX_PAGES):
        page = _get(call, '/connections/workspaces', limit=100, cursor=cursor)
        if (type(page) is not dict or page.get('version') != 1 or page.get('server_id') != server_id
                or type(page.get('revision')) is not str or re.fullmatch(r'[a-f0-9]{64}', page['revision']) is None
                or type(page.get('items')) is not list or len(page['items']) > 100
                or type(page.get('has_more')) is not bool or page.get('total_is_exact') is not True
                or type(page.get('total')) is not int or page['total'] < 0):
            raise ConnectionError('PROJECT_CATALOG_UNCONFIRMED', 'The authorized project directory is incomplete.')
        if revision is not None and (revision != page['revision'] or total != page['total']):
            raise ConnectionError('PROJECT_CATALOG_UNCONFIRMED', 'The project directory changed; resolve it again.')
        revision, total = page['revision'], page['total']
        for row in page['items']:
            if (type(row) is not dict or type(row.get('workspace_id')) is not str
                    or not 1 <= len(row['workspace_id']) <= 160 or not row['workspace_id'].isprintable()
                    or row['workspace_id'] in seen or type(row.get('display_name')) is not str
                    or not row['display_name'].strip() or not row['display_name'].isprintable()):
                raise ConnectionError('PROJECT_CATALOG_UNCONFIRMED', 'The project directory contains invalid metadata.')
            seen.add(row['workspace_id'])
            rows.append(row)
        if not page['has_more']:
            if page.get('next_cursor') is not None or len(rows) != total:
                raise ConnectionError('PROJECT_CATALOG_UNCONFIRMED', 'The project directory is incomplete.')
            return tuple(rows), revision
        following = page.get('next_cursor')
        if type(following) is not str or not following or following in cursors:
            raise ConnectionError('PROJECT_CATALOG_UNCONFIRMED', 'The project directory cursor did not advance.')
        cursors.add(following)
        cursor = following
    raise ConnectionError('PROJECT_CATALOG_UNCONFIRMED', 'The project directory exceeds its bounded page limit.')


def project_context(call, *, server_id, executor_id, root, workspace_id=None):
    value = _get(call, '/connections/project-context', executor_id=executor_id,
        project_root=root, workspace_id=workspace_id)
    if (type(value) is not dict or value.get('version') != 1 or value.get('server_id') != server_id
            or value.get('executor_id') != executor_id or value.get('workspace_id') != workspace_id
            or type(value.get('project_revision')) is not str
            or re.fullmatch(r'sha256:[a-f0-9]{64}', value['project_revision']) is None
            or root is not None and not _same_local_path(value.get('project_root'), root)
            or type(value.get('mapped_workspace_ids')) is not list
            or any(type(v) is not str for v in value['mapped_workspace_ids'])):
        raise ConnectionError('PROJECT_CATALOG_UNCONFIRMED', 'The canonical project context is unconfirmed.')
    return value


def _choose(rows, *, interactive, read, write):
    if len(rows) == 1:
        return rows[0]
    if not interactive:
        raise ConnectionError('PROJECT_SELECTION_REQUIRED', 'Select an exact authorized workspace.', choices=list(rows))
    write('Choose a Nexus project:')
    for index, row in enumerate(rows, 1):
        write(f"{index}. {row['display_name']} ({row['workspace_id']})")
    write('c. Cancel')
    while True:
        try:
            answer = read('Project: ').strip().lower()
        except EOFError:
            answer = 'c'
        if answer in ('', 'c'):
            raise ConnectionError('CONNECT_CANCELLED', 'Connection selection cancelled.')
        if answer.isdecimal() and 1 <= int(answer) <= len(rows):
            return rows[int(answer) - 1]
        write('Select a displayed project or c.')


def resolve_project(call, *, server_id, executor_id, invocation_cwd, root,
        explicit_root=False, workspace_id=None, project_name=None, plan=False,
        interactive=False, read=input, write=print, discover=None):
    """Return frozen review inputs. This function never creates a project/folder."""
    if project_name is not None and (type(project_name) is not str or not project_name.strip()
            or not project_name.isprintable() or len(project_name) > 120):
        raise ConnectionError('PROJECT_NAME_INVALID', 'Use a printable project name of at most 120 characters.')
    directory, directory_revision = project_directory(call, server_id)
    context = project_context(call, server_id=server_id, executor_id=executor_id, root=root)
    mapped = [row for row in directory if row['workspace_id'] in context['mapped_workspace_ids']]
    if len(mapped) != len(set(context['mapped_workspace_ids'])):
        raise ConnectionError('PROJECT_CATALOG_UNCONFIRMED', 'A mapped project is absent from the authorized directory.')
    chosen = None
    root_source = 'explicit_project' if explicit_root else 'cwd'
    if workspace_id:
        exact = [row for row in directory if row['workspace_id'] == workspace_id]
        if len(exact) != 1:
            raise ConnectionError('PROJECT_SELECTION_REQUIRED', 'The selected project is unavailable.')
        chosen = exact[0]
        if project_name is not None and chosen['display_name'] != project_name:
            raise ConnectionError('PROJECT_SELECTOR_CONFLICT', 'The project name and exact workspace selector disagree.')
    elif project_name is not None:
        matches = [row for row in directory if row['display_name'] == project_name]
        if matches:
            chosen = _choose(matches, interactive=interactive, read=read, write=write)
        elif mapped:
            raise ConnectionError('PROJECT_SELECTOR_CONFLICT', 'This folder already maps to another project; its name is preserved.')
    elif mapped:
        chosen = _choose(mapped, interactive=interactive, read=read, write=write)
    if chosen:
        workspace_id = chosen['workspace_id']
        if workspace_id not in context['mapped_workspace_ids']:
            paths = _get(call, '/workspaces/' + quote(workspace_id, safe='') + '/paths', executor_id=executor_id)
            if paths.get('has_more') or type(paths.get('items')) is not list:
                raise ConnectionError('PROJECT_CATALOG_UNCONFIRMED', 'The project folder inventory is incomplete.')
            roots = [row.get('path') for row in paths['items']]
            if any(type(path) is not str for path in roots):
                raise ConnectionError('PROJECT_CATALOG_UNCONFIRMED', 'The project folder inventory is invalid.')
            if roots and not any(_same_local_path(path, root) for path in roots):
                if explicit_root or not interactive:
                    raise ConnectionError('PROJECT_DIRECTORY_MISMATCH', 'The selected project has another approved root; select it explicitly.')
                write('This project uses a different approved execution folder:')
                for index, path in enumerate(roots, 1):
                    write(f'{index}. {path}')
                write('c. Cancel; no folder will be changed without approval.')
                try:
                    answer = read('Use approved folder: ').strip().lower()
                except EOFError:
                    answer = 'c'
                if not answer.isdecimal() or not 1 <= int(answer) <= len(roots):
                    raise ConnectionError('CONNECT_CANCELLED', 'Folder selection cancelled.')
                root = str(Path(roots[int(answer) - 1]).resolve(strict=True))
                root_source = 'existing_nexus'
        label = chosen['display_name']
        source, discovery = ('explicit', {'status': 'not_needed', 'reason': 'explicit_name'}) if project_name is not None else (
            'existing_nexus', {'status': 'not_needed', 'reason': 'existing_nexus'})
    elif project_name is not None:
        label, source, discovery = project_name, 'explicit', {'status': 'not_needed', 'reason': 'explicit_name'}
    else:
        if discover is None:
            from ...outbound.git_project_hint import discover_project_name
            discover = discover_project_name
        hint = discover(Path(root), plan=plan)
        label, source = hint.name, hint.source
        discovery = {'status': hint.status, 'reason': hint.reason}
        if not label:
            raise ConnectionError('PROJECT_NAME_REQUIRED', 'Choose an explicit project name for this execution folder.')
        # A hint can only propose a new project; equal names are not associations.
        if interactive and directory:
            write(f'New project suggestion: {label}. Existing projects:')
            for index, row in enumerate(directory, 1):
                write(f"{index}. {row['display_name']} ({row['workspace_id']})")
            write('n. Use the suggested name for a new project\nc. Cancel')
            try:
                answer = read('Project: ').strip().lower()
            except EOFError:
                answer = 'c'
            if answer.isdecimal() and 1 <= int(answer) <= len(directory):
                selected = directory[int(answer) - 1]
                return resolve_project(call, server_id=server_id, executor_id=executor_id,
                    invocation_cwd=invocation_cwd, root=root, explicit_root=explicit_root,
                    workspace_id=selected['workspace_id'], project_name=None,
                    plan=plan, interactive=interactive, read=read, write=write, discover=discover)
            if answer != 'n':
                raise ConnectionError('CONNECT_CANCELLED', 'Project selection cancelled.')
    final = project_context(call, server_id=server_id, executor_id=executor_id, root=root, workspace_id=workspace_id)
    _, current_revision = project_directory(call, server_id)
    if current_revision != directory_revision:
        raise ConnectionError('PROJECT_CATALOG_UNCONFIRMED', 'The project directory changed during selection; review it again.')
    return dict(project=root, label=label, workspace_id=workspace_id,
        project_revision=final['project_revision'], project_name_source=source,
        name_discovery=discovery, cwd_resolution=dict(invocation_cwd=invocation_cwd,
            project_root=root, root_explicit=explicit_root,
            source=root_source))
