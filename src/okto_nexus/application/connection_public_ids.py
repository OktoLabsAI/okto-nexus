"""Durable product IDs, independent of execution authorization and technical aliases."""
import json
import base64
import hashlib
import sqlite3
import uuid

from ..bootstrap.execution_authority import build_execution_access
from ..domain.connection_public_ids import canonical_reference, connect_id, normalize
from ..errors import ErrorCode, OktoNexusError
from .connection_project_context import project_context_in
from .connection_setup import require_operator, setup_actor
from .execution_local_realizations import _digest
from .connection_catalog import _object


def _conflict(message, reason='PUBLIC_CONNECTION_CONFLICT'):
    return OktoNexusError(ErrorCode.CONFLICT, message, {'reason': reason})


def _occupied_reason(uow, server, workspace, name):
    row = uow.connection.execute('SELECT state FROM connection_public_ids WHERE server_id=? '
                                 'AND workspace_id=? AND connect_id=?', (server, workspace, name)).fetchone()
    return 'CONNECT_ID_PENDING' if row is None or row['state'] == 'reserved' else 'HARNESS_ID_ALREADY_EXISTS'


def _server(uow):
    row = uow.connection.execute('SELECT server_id FROM execution_installation WHERE singleton=1').fetchone()
    if row is None:
        raise _conflict('Server installation identity is unavailable.')
    return row[0]


def _proof(uow, request):
    public = normalize(request['public_connection'])
    configuration = request['configuration']
    root = configuration.get('workspace_root') if configuration.get('execution_location') != 'remote' else None
    proof = project_context_in(uow, executor_id=request['executor_id'], project_root=root,
                               workspace_id=request.get('workspace_id'), include_private_identity=True)
    if proof['project_revision'] != public['project_revision']:
        raise _conflict('The selected project or directory changed. Review it again.', 'PROJECT_SELECTION_CHANGED')
    if request.get('workspace_id') is None and proof['mapped_workspace_ids']:
        raise _conflict('Select the existing project associated with this directory.', 'PROJECT_SELECTION_REQUIRED')
    return public, proof


def _row_result(row):
    return dict(version=1, state=row['state'], connect_id=row['connect_id'],
                reservation_ref=row['reservation_ref'], revision=row['revision'],
                setup_run_id=row['client_intent_id'], workspace_id=row['workspace_id'],
                project_draft_ref=row['project_draft_ref'], request_hash=row['request_hash'],
                canonical_ref=json.loads(row['canonical_ref_json']) if row['canonical_ref_json'] else None)


def reserve_public_id(deps, context, request, *, approved):
    if approved is not True or request.get('public_connection') is None:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Approve the reviewed public connection intent.', {})
    public = normalize(request['public_connection'])
    digest = _digest(request)
    with deps.connection_factory.unit_of_work() as uow:
        require_operator(build_execution_access(deps), context, uow)
        server, actor = _server(uow), setup_actor(context)
        committed = uow.connection.execute('SELECT request_hash FROM connection_setup_commits '
            'WHERE actor_agent_id=? AND client_intent_id=?', (actor, request['client_intent_id'])).fetchone()
        if committed is not None and committed['request_hash'] != digest:
            raise _conflict('The committed setup receipt belongs to different reviewed content.')
        rows = uow.connection.execute('SELECT * FROM connection_public_ids WHERE server_id=? '
            'AND (reservation_ref=? OR (actor_agent_id=? AND client_intent_id=?))',
            (server, public['reservation_ref'], actor, request['client_intent_id'])).fetchall()
        if rows:
            if len(rows) != 1 or any(rows[0][name] != value for name, value in (
                    ('reservation_ref', public['reservation_ref']), ('actor_agent_id', actor),
                    ('client_intent_id', request['client_intent_id']), ('request_hash', digest))):
                raise _conflict('This reservation belongs to a different approved intent.')
            return _row_result(rows[0])
        public, proof = _proof(uow, request)
        workspace = request.get('workspace_id')
        draft = None
        now = deps.clock.now_iso()
        try:
            if workspace is None:
                draft = 'pjd_' + uuid.uuid4().hex
                root_key = _digest(proof['_directory_identity'])
                uow.connection.execute('INSERT INTO connection_project_drafts '
                    '(server_id,project_draft_ref,executor_id,directory_key,project_revision,workspace_label,'
                    'actor_agent_id,client_intent_id,state,workspace_id,revision,created_at,updated_at) '
                    "VALUES(?,?,?,?,?,?,?,?,'reserved',NULL,1,?,?)",
                    (server, draft, request['executor_id'], root_key, public['project_revision'],
                     request['configuration']['workspace_label'], actor, request['client_intent_id'], now, now))
            namespace = 'workspace:' + workspace if workspace is not None else 'draft:' + draft
            uow.connection.execute('INSERT INTO connection_public_ids '
                '(server_id,reservation_ref,actor_agent_id,client_intent_id,namespace_ref,workspace_id,'
                'project_draft_ref,connect_id,state,request_hash,adapter_id,revision,created_at,updated_at) '
                "VALUES(?,?,?,?,?,?,?,?,'reserved',?,?,1,?,?)",
                (server, public['reservation_ref'], actor, request['client_intent_id'], namespace, workspace,
                 draft, public['connect_id'], digest, request['configuration']['adapter_id'], now, now))
        except sqlite3.IntegrityError:
            raise _conflict('This Harness ID or project directory is already reserved. Recover its original intent.',
                            _occupied_reason(uow, server, workspace, public['connect_id'])) from None
        row = uow.connection.execute('SELECT * FROM connection_public_ids WHERE server_id=? AND reservation_ref=?',
                                     (server, public['reservation_ref'])).fetchone()
        return _row_result(row)


def validate_reserved(uow, context, request, *, revalidate_project=True):
    if request.get('public_connection') is None:
        return None
    public = normalize(request['public_connection'])
    row = uow.connection.execute('SELECT * FROM connection_public_ids WHERE server_id=? AND reservation_ref=?',
                                 (_server(uow), public['reservation_ref'])).fetchone()
    if row is None or row['state'] != 'reserved' or row['actor_agent_id'] != setup_actor(context) or (
            row['client_intent_id'] != request['client_intent_id'] or row['request_hash'] != _digest(request)):
        raise _conflict('Recover or reserve this exact approved intent before Test or Finish.', 'PUBLIC_RESERVATION_REQUIRED')
    if revalidate_project:
        _proof(uow, request)
    return row


def bind_public_id(uow, context, request, result, *, now):
    if request.get('public_connection') is None:
        return
    row = validate_reserved(uow, context, request, revalidate_project=False)
    binding = result.get('binding')
    if not binding:
        raise _conflict('A public Harness ID requires a canonical connection binding.')
    ref = uow.connection.execute('SELECT b.server_id,b.executor_id,b.binding_id,b.endpoint_id,'
        'e.agent_id,e.workspace_id,b.workspace_binding_id FROM execution_bindings b '
        'JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id WHERE b.server_id=? AND b.executor_id=? AND b.binding_id=?',
        (row['server_id'], request['executor_id'], binding['binding_id'])).fetchone()
    if ref is None:
        raise _conflict('The committed connection reference is unavailable.')
    reference = canonical_reference(dict(ref))
    if row['workspace_id'] is not None and row['workspace_id'] != reference['workspace_id']:
        raise _conflict('The committed connection belongs to another project.')
    try:
        uow.connection.execute("UPDATE connection_public_ids SET state='bound',namespace_ref=?,workspace_id=?,"
            'canonical_ref_json=?,revision=revision+1,updated_at=? WHERE server_id=? AND reservation_ref=?',
            ('workspace:' + reference['workspace_id'], reference['workspace_id'], json.dumps(reference, sort_keys=True),
             now, row['server_id'], row['reservation_ref']))
        if row['project_draft_ref']:
            uow.connection.execute("UPDATE connection_project_drafts SET state='bound',workspace_id=?,"
                'revision=revision+1,updated_at=? WHERE server_id=? AND project_draft_ref=?',
                (reference['workspace_id'], now, row['server_id'], row['project_draft_ref']))
    except sqlite3.IntegrityError:
        raise _conflict('This Harness ID is occupied in the committed project.',
                        _occupied_reason(uow, row['server_id'], reference['workspace_id'], row['connect_id'])) from None
    result['public_connection'] = dict(version=1, connect_id=row['connect_id'], reservation_ref=row['reservation_ref'],
                                      revision=row['revision'] + 1, state='bound', canonical_ref=reference)


def list_public_ids(deps, context, *, workspace_id=None, requested_id=None, limit=100, cursor=None, principal=None):
    if type(limit) is not int or not 1 <= limit <= 100 or (workspace_id is not None and (
            type(workspace_id) is not str or not 1 <= len(workspace_id) <= 160)):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid public ID scope.', {})
    requested_id = connect_id(requested_id) if requested_id is not None else None
    with deps.connection_factory.unit_of_work(write=False) as uow:
        require_operator(build_execution_access(deps), context, uow)
        if context.authentication_source == 'operator_session' and (type(principal) is not str or not 1 <= len(principal) <= 160):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The authenticated human identity is unavailable.', {})
        server = _server(uow)
        scope = dict(workspace_id=workspace_id, connect_id=requested_id)
        if workspace_id is None:
            if requested_id is not None or cursor is not None:
                raise _conflict('Select a project before checking Harness ID availability.', 'PROJECT_SELECTION_REQUIRED')
            return dict(version=1, capabilities={'public_connection': 1}, server_id=server,
                        scope=scope, status='namespace_required', revision=None, items=[], total=None,
                        total_is_exact=False, has_more=False, next_cursor=None)
        if uow.connection.execute('SELECT 1 FROM workspaces WHERE workspace_id=?', (workspace_id,)).fetchone() is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'Workspace not found.', {})
        where, args = 'server_id=? AND workspace_id=?', [server, workspace_id]
        if requested_id is not None:
            where += ' AND connect_id=?'
            args.append(requested_id)
        # Public metadata only; neither full setup requests nor private paths enter a cursor.
        material = uow.connection.execute('SELECT COUNT(*),json_group_array(json_array(reservation_ref,connect_id,'
            'workspace_id,project_draft_ref,state,request_hash,adapter_id,canonical_ref_json,revision)) '
            'FROM (SELECT * FROM connection_public_ids WHERE ' + where + ' ORDER BY connect_id)', args).fetchone()
        revision = hashlib.sha256(material[1].encode()).hexdigest()
        fence = _digest([server, context.authentication_source, context.actor_agent_id,
                         context.credential_binding, principal, scope])
        after = ''
        if cursor is not None:
            try:
                if type(cursor) is not str or not 1 <= len(cursor) <= 2048:
                    raise ValueError()
                saved = json.loads(base64.b64decode(cursor + '=' * (-len(cursor) % 4), altchars=b'-_', validate=True),
                                   object_pairs_hook=_object)
                if (set(saved) != {'kind', 'fence', 'revision', 'after', 'limit'}
                        or saved['kind'] != 'public_ids' or saved['fence'] != fence
                        or type(saved['limit']) is not int or saved['limit'] != limit
                        or type(saved['after']) is not str):
                    raise ValueError()
                if saved['revision'] != revision:
                    raise _conflict('The public ID namespace changed. Restart pagination.', 'PUBLIC_IDS_CHANGED')
                after = saved['after']
            except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid public ID cursor.', {}) from None
        selected = uow.connection.execute('SELECT * FROM connection_public_ids WHERE ' + where +
            ' AND connect_id>? ORDER BY connect_id LIMIT ?', [*args, after, limit + 1]).fetchall()
        more = len(selected) > limit
        items = [dict(_row_result(row), adapter_id=row['adapter_id'], requires_canonical_revalidation=True)
                 for row in selected[:limit]]
        following = None
        if more:
            following = base64.urlsafe_b64encode(json.dumps(dict(kind='public_ids', fence=fence, revision=revision,
                after=items[-1]['connect_id'], limit=limit), sort_keys=True).encode()).decode().rstrip('=')
        return dict(version=1, capabilities={'public_connection': 1}, server_id=server, scope=scope,
                    revision=revision, items=items, total=material[0], total_is_exact=True, has_more=more,
                    next_cursor=following, cursor_integrity='unsigned_scope_checked')


def associate_existing(deps, context, request):
    from .execution_binding_views import read_execution_binding
    if request.get('approved') is not True:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Approve the exact existing connection association.', {})
    reference = canonical_reference(request['expected_binding_ref'])
    name = connect_id(request['connect_id'])
    digest = _digest(request)
    with deps.connection_factory.unit_of_work() as uow:
        access = build_execution_access(deps)
        require_operator(access, context, uow)
        server, actor = _server(uow), setup_actor(context)
        if reference['server_id'] != server:
            raise _conflict('The connection belongs to another Server.')
        prior = uow.connection.execute('SELECT * FROM connection_public_ids WHERE server_id=? '
            'AND actor_agent_id=? AND client_intent_id=?', (server, actor, request['client_intent_id'])).fetchone()
        if prior:
            if prior['request_hash'] != digest:
                raise _conflict('This association intent has different content.')
            return _row_result(prior)
        current = read_execution_binding(deps.connection_factory, server_id=server, binding_id=reference['binding_id'],
                                         context=context, access=access, uow=uow)
        if any(current.get(key) != value for key, value in reference.items()) or (
                current.get('binding_revision') != request['expected_binding_revision'] or current.get('state') != 'APPROVED'):
            raise _conflict('The selected connection changed. Review it again.')
        now, reservation = deps.clock.now_iso(), 'pcr_' + uuid.uuid4().hex
        try:
            uow.connection.execute('INSERT INTO connection_public_ids '
                '(server_id,reservation_ref,actor_agent_id,client_intent_id,namespace_ref,workspace_id,connect_id,'
                'state,request_hash,adapter_id,canonical_ref_json,revision,created_at,updated_at) '
                "VALUES(?,?,?,?,?,?,?,'bound',?,?,?,1,?,?)", (server, reservation, actor, request['client_intent_id'],
                'workspace:' + reference['workspace_id'], reference['workspace_id'], name, digest,
                current['adapter_id'], json.dumps(reference, sort_keys=True), now, now))
        except sqlite3.IntegrityError:
            raise _conflict('This Harness ID or connection already has a public association.',
                            'HARNESS_ID_ALREADY_EXISTS') from None
        row = uow.connection.execute('SELECT * FROM connection_public_ids WHERE server_id=? AND reservation_ref=?',
                                     (server, reservation)).fetchone()
        return _row_result(row)
