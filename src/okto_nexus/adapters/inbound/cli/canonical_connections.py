"""Complete bounded catalog consumption and canonical project association."""
import hashlib
import json
from urllib.parse import quote, urlencode

from ....application.project_preset import CLIENTS
from ....application.terminal_connection import ConnectionError, PREFIX, _same_local_path
from .connection_choices import ConnectionChoice, ConnectionChoiceCatalog, ChoiceIssue

IDENTITY = ('server_id', 'executor_id', 'binding_id', 'endpoint_id', 'agent_id', 'workspace_id', 'workspace_binding_id')
MAX_PAGES = 32


def _identity(row):
    if type(row) is not dict:
        raise ConnectionError('CATALOG_UNCONFIRMED', 'The canonical connection reference is invalid.')
    values = tuple(row.get(key) for key in IDENTITY)
    if any(type(value) is not str or not 1 <= len(value) <= 160 or not value.isprintable() for value in values):
        raise ConnectionError('CATALOG_UNCONFIRMED', 'The canonical connection reference is invalid.')
    return values


def merge_canonical_connections(call, *, local, server_id, project, workspace_id=None):
    """Never treat a failed/incomplete remote inventory as an empty project.

    Only catalog rows are paginated here. Per-binding revalidation is deliberate
    CLI association work and may materialize existing revision metadata; it is
    not part of the read-only backend catalog or execution admission.
    """
    rows, cursor, revision = [], None, None
    filters = {'workspace_id': workspace_id} if workspace_id else {'execution_location': 'local'}
    try:
        seen, cursors, expected_total = set(), set(), None
        for _ in range(MAX_PAGES):
            page = call('GET', PREFIX + '/connections/catalog?' + urlencode(dict(filters,
                limit=100, **({'cursor': cursor} if cursor else {}))))
            if (type(page) is not dict or type(page.get('version')) is not int or page['version'] != 1 or page.get('server_id') != server_id or page.get('scope') != filters
                    or type(page.get('items')) is not list or len(page['items']) > 100
                    or type(page.get('has_more')) is not bool or type(page.get('total')) is not int
                    or page['total'] < 0 or page.get('total_is_exact') is not True
                    or type(page.get('revision')) is not str or len(page['revision']) != 64):
                raise ConnectionError('CATALOG_UNCONFIRMED', 'The Server returned an invalid connection inventory.')
            if expected_total is not None and expected_total != page['total']:
                raise ConnectionError('CATALOG_CHANGED', 'The connection inventory total changed during pagination.')
            expected_total = page['total']
            if revision is not None and revision != page['revision']:
                raise ConnectionError('CATALOG_CHANGED', 'The connection inventory changed during pagination.')
            revision = page['revision']
            for row in page['items']:
                identity = _identity(row)
                if (identity[0] != server_id or row.get('execution_location') not in ('local', 'remote') or identity in seen
                        or workspace_id is None and row.get('execution_location') != 'local'
                        or workspace_id is not None and row['workspace_id'] != workspace_id):
                    raise ConnectionError('CATALOG_UNCONFIRMED', 'The connection inventory scope is inconsistent.')
                seen.add(identity)
                rows.append(row)
            if not page['has_more']:
                if len(rows) != page['total'] or page.get('next_cursor') is not None:
                    raise ConnectionError('CATALOG_UNCONFIRMED', 'The connection inventory is incomplete.')
                break
            following = page.get('next_cursor')
            if type(following) is not str or not 1 <= len(following) <= 2048 or following in cursors:
                raise ConnectionError('CATALOG_UNCONFIRMED', 'The connection inventory cursor did not advance.')
            cursors.add(following)
            cursor = following
        else:
            raise ConnectionError('CATALOG_UNCONFIRMED', 'The bounded connection inventory has more pages; select an explicit scope.')
        choices = list(local.choices)
        for row in rows:
            if row['execution_location'] == 'local':
                current = call('GET', PREFIX + '/connections/setup/' + quote(row['agent_id'], safe='')
                    + '?' + urlencode({'binding_id': row['binding_id']}))
                folders = current.get('folders')
                if type(folders) is not dict or type(folders.get('workspace_root')) is not str:
                    raise ConnectionError('CATALOG_UNCONFIRMED', 'The local binding project mapping is unavailable.')
                if not _same_local_path(folders['workspace_root'], project):
                    continue
            binding = call('GET', PREFIX + '/connections/bindings/' + quote(row['binding_id'], safe=''))
            if _identity(binding) != _identity(row):
                raise ConnectionError('CATALOG_CHANGED', 'The binding changed during project association.')
            if binding.get('state') not in {'APPROVED', 'REVOKED', 'DISABLED', 'PENDING_REVIEW', 'STALE'}:
                raise ConnectionError('CATALOG_UNCONFIRMED', 'The binding state is unavailable.')
            client = next((name for name, adapter in CLIENTS.items() if adapter == row['adapter_id']), None)
            # A local shortcut is a reference to the immutable binding ID within
            # this Server/agent. Setup + binding reads above prove its full tuple
            # now, including legacy shortcuts that retained only binding_id.
            matching = [choice for choice in choices if choice.binding_id == row['binding_id'] and choice.agent_id == row['agent_id']]
            if any(choice.binding_ref is not None and _identity(choice.binding_ref) != _identity(binding) for choice in matching):
                raise ConnectionError('CATALOG_CHANGED', 'A retained shortcut belongs to another connection scope.')
            if matching:
                continue
            reference = {key: binding[key] for key in IDENTITY}
            reference.update(client=client, binding_state=binding['state'], execution_location=row['execution_location'],
                host_label=row.get('host_label') or row['executor_id'])
            alias = 'canonical-' + hashlib.sha256(json.dumps([_identity(row), project],
                separators=(',', ':')).encode()).hexdigest()[:24]
            choices.append(ConnectionChoice(alias, row['agent_id'], client, row['binding_id'], row['workspace_id'],
                'canonical_' + binding['state'].lower(), False, False, False, False, False, False,
                canonical_ref=reference))
        return ConnectionChoiceCatalog(tuple(choices), local.issues, local.complete)
    except (ConnectionError, ValueError, TypeError, KeyError):
        return ConnectionChoiceCatalog(local.choices,
            local.issues + (ChoiceIssue(None, 'canonical_catalog_unconfirmed'),), False)


def associate_canonical(flow, call, *, reference, project):
    current = call('GET', PREFIX + '/connections/bindings/' + quote(reference['binding_id'], safe=''))
    if _identity(current) != _identity(reference) or current['state'] != 'APPROVED' or reference['client'] is None:
        raise ConnectionError('BINDING_UNAVAILABLE', 'The selected canonical connection cannot be resumed; inspect its existing approval.')
    selection = dict(agent=reference['agent_id'], client=reference['client'], project=project,
        label=project, workspace_id=reference['workspace_id'], binding_id=reference['binding_id'],
        candidate_ref=None, provider_home=None, create_agent=False, display_name=None)
    if reference['execution_location'] == 'remote':
        # The explicit workspace and full remote_scope identify the remote
        # connection. project is only this client's local shortcut namespace.
        return flow.review(selection)
    # _reused invokes observe before saving the ordinary format-1 profile. No
    # setup/test/Finish/grant/identity/operation endpoint participates.
    return flow._reused(selection, reference['server_id'], reference['binding_id'])
