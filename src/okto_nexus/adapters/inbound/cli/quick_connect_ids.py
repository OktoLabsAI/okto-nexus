"""Public namespace reads and explicit collision decisions, never reservations."""
from urllib.parse import urlencode

from ....application.project_preset import CLIENTS
from ....application.terminal_connection import ConnectionError, PREFIX
from ....domain.quick_connect import normalize_connect_id
from .canonical_connections import IDENTITY, _identity


def public_ids(call, *, server_id, workspace_id):
    rows, cursor, revision, total, cursors, names = [], None, None, None, set(), set()
    for _ in range(32):
        page = call('GET', PREFIX + '/connections/public-ids?' + urlencode(dict(
            workspace_id=workspace_id, limit=100, **({'cursor': cursor} if cursor else {}))))
        if (type(page) is not dict or page.get('version') != 1
                or type(page.get('capabilities')) is not dict or page['capabilities'].get('public_connection') != 1
                or page.get('server_id') != server_id or type(page.get('scope')) is not dict
                or page['scope'].get('workspace_id') != workspace_id
                or type(page.get('revision')) is not str or len(page['revision']) != 64
                or type(page.get('items')) is not list or len(page['items']) > 100
                or type(page.get('has_more')) is not bool or page.get('total_is_exact') is not True
                or type(page.get('total')) is not int or page['total'] < 0):
            raise ConnectionError('PUBLIC_ID_CATALOG_UNCONFIRMED', 'The public Harness ID namespace is unconfirmed.')
        if revision is not None and (revision != page['revision'] or total != page['total']):
            raise ConnectionError('PUBLIC_ID_CATALOG_UNCONFIRMED', 'The Harness ID namespace changed; resolve it again.')
        revision, total = page['revision'], page['total']
        for row in page['items']:
            try:
                valid_id = type(row) is dict and normalize_connect_id(row.get('connect_id')) == row['connect_id']
            except ValueError:
                valid_id = False
            if (not valid_id
                    or row['connect_id'] in names or row.get('state') not in ('reserved', 'bound', 'retired')
                    or row.get('workspace_id') != workspace_id):
                raise ConnectionError('PUBLIC_ID_CATALOG_UNCONFIRMED', 'The public Harness ID metadata is invalid.')
            names.add(row['connect_id'])
            if row['state'] == 'bound':
                reference = row.get('canonical_ref')
                _identity(reference)
                if reference['server_id'] != server_id or reference['workspace_id'] != workspace_id:
                    raise ConnectionError('PUBLIC_ID_CATALOG_UNCONFIRMED', 'A public Harness ID has another canonical scope.')
            rows.append(row)
        if not page['has_more']:
            if page.get('next_cursor') is not None or len(rows) != total:
                raise ConnectionError('PUBLIC_ID_CATALOG_UNCONFIRMED', 'The public Harness ID namespace is incomplete.')
            return tuple(rows)
        following = page.get('next_cursor')
        if type(following) is not str or not following or following in cursors:
            raise ConnectionError('PUBLIC_ID_CATALOG_UNCONFIRMED', 'The public Harness ID cursor did not advance.')
        cursors.add(following)
        cursor = following
    raise ConnectionError('PUBLIC_ID_CATALOG_UNCONFIRMED', 'Select a smaller Harness ID namespace.')


def require_public_ids(call, server_id):
    """A new client must not invent a local namespace against an old Server."""
    try:
        value = call('GET', PREFIX + '/connections/public-ids')
    except ConnectionError as error:
        if error.code in ('NOT_FOUND', 'HTTP_ERROR', 'VALIDATION_ERROR'):
            raise ConnectionError('CONNECT_ID_UNSUPPORTED_SERVER', 'This Server must be upgraded to support public Harness IDs.') from None
        raise
    if (type(value) is not dict or value.get('version') != 1 or value.get('server_id') != server_id
            or type(value.get('capabilities')) is not dict or value['capabilities'].get('public_connection') != 1):
        raise ConnectionError('CONNECT_ID_UNSUPPORTED_SERVER', 'This Server cannot confirm public Harness ID support.')


def _client(row):
    return next((name for name, adapter in CLIENTS.items() if adapter == row.get('adapter_id')), None)


def _selectors_agree(row, selectors):
    reference = row.get('canonical_ref') or {}
    return all(value is None or reference.get(key) == value for key, value in selectors.items())


def propose_id(rows, harness):
    if harness not in CLIENTS:
        raise ConnectionError('CLIENT_SELECTION_REQUIRED', 'Select a supported harness before proposing its Harness ID.')
    occupied = {row['connect_id'] for row in rows}
    if harness not in occupied:
        return harness
    for index in range(2, 10001):
        candidate = f'{harness}-{index}'
        if candidate not in occupied:
            return candidate
    raise ConnectionError('HARNESS_ID_SELECTION_REQUIRED', 'Choose an explicit unused Harness ID.')


def select_id(rows, *, harness, connect_id=None, new_connection=False, selectors=None,
        interactive=False, read=input, write=print):
    """Return (new|resume, ID, occupant). Choice alone never approves setup."""
    selectors = dict(selectors or {})
    explicit = connect_id is not None
    if explicit:
        connect_id = normalize_connect_id(connect_id)
    elif not new_connection:
        candidates = [row for row in rows if _client(row) == harness and row['state'] == 'bound'
            and _selectors_agree(row, selectors)]
        if len(candidates) > 1:
            if not interactive:
                raise ConnectionError('HARNESS_ID_SELECTION_REQUIRED', 'Select an exact Harness ID; multiple connections match.',
                    choices=[dict(connect_id=r['connect_id'], harness=_client(r)) for r in candidates])
            write('Choose an existing ID do Harness, or add another connection:')
            for index, row in enumerate(candidates, 1):
                write(f"{index}. {row['connect_id']} · {_client(row)}")
            write('a. Add another\nc. Cancel')
            try:
                answer = read('Connection: ').strip().lower()
            except EOFError:
                answer = 'c'
            if answer == 'a':
                return 'new', propose_id(rows, harness), None
            if answer.isdecimal() and 1 <= int(answer) <= len(candidates):
                row = candidates[int(answer) - 1]
                return 'resume', row['connect_id'], row
            raise ConnectionError('CONNECT_CANCELLED', 'Connection selection cancelled.')
        if candidates:
            connect_id = candidates[0]['connect_id']
    connect_id = connect_id or propose_id(rows, harness)
    while True:
        row = next((r for r in rows if r['connect_id'] == connect_id), None)
        if row is None:
            return 'new', connect_id, None
        if not _selectors_agree(row, selectors):
            raise ConnectionError('CONNECTION_SELECTOR_CONFLICT', 'Exact connection selectors disagree with this Harness ID.')
        existing_client = _client(row)
        resumable = row['state'] == 'bound' and existing_client is not None and not new_connection
        if not interactive:
            if resumable and existing_client == harness:
                return 'resume', connect_id, row
            code = 'HARNESS_ID_PENDING' if row['state'] == 'reserved' else 'HARNESS_ID_ALREADY_EXISTS'
            raise ConnectionError(code, 'This Harness ID is already occupied; select another ID explicitly.',
                choices=[dict(connect_id=propose_id(rows, harness), proposed=True)] if harness in CLIENTS else [])
        write(f'ID do Harness: {connect_id} is occupied ({row["state"]}).')
        if resumable:
            write(f'r. Resume the existing {existing_client} connection'
                + (f' (requested: {harness})' if existing_client != harness else ''))
        write('i. Choose another ID do Harness\ns. Propose an available ID\nc. Cancel')
        try:
            answer = read('Choice: ').strip().lower()
        except EOFError:
            answer = 'c'
        if answer == 'r' and resumable:
            return 'resume', connect_id, row
        if answer == 's':
            return 'new', propose_id(rows, harness), None
        if answer == 'i':
            try:
                connect_id = normalize_connect_id(read('ID do Harness: '))
            except EOFError:
                raise ConnectionError('CONNECT_CANCELLED', 'Connection selection cancelled.') from None
            continue
        if answer in ('c', ''):
            raise ConnectionError('CONNECT_CANCELLED', 'Connection selection cancelled.')
        write('Choose one of the displayed actions.')


def binding_reference(row):
    """Return a fresh exact reference; no ID label becomes a routing target."""
    reference = row['canonical_ref']
    _identity(reference)
    return {key: reference[key] for key in IDENTITY}
