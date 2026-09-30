"""Session credentials bound to canonical admission, never execution tickets.

Issuance reserves material for host configuration. A reserved credential does
not authorize a tool call: consumers must check active session/lease authority
and their domain permissions at the actual use-case boundary.
"""

from __future__ import annotations

from datetime import timedelta
import hashlib
import json
import secrets

from nexus_connector_core.protocol import canonical_json

from ..adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from ..adapters.outbound.sqlite.execution_identity import ensure_execution_installation
from ..adapters.outbound.sqlite.execution_leases import SqliteExecutionLeaseRepository
from ..domain.runtime_context import RuntimeRequestContext
from ..errors import ErrorCode, OktoNexusError
from .connection_policy import require_method
from .execution_binding_proposals import _agent_guard
from .execution_leases import _stamp


AUDIENCES = frozenset({'nexus-mcp-session', 'nexus-native-session'})


def _error(code, message, **details):
    return OktoNexusError(code, message, details)


class ExecutionCapabilityService:
    def __init__(self, *, factory, access):
        self.factory, self.access = factory, access
        self.repo = SqliteExecutionLeaseRepository()

    def _target(self, uow, *, server_id, session_id, binding_id, context):
        operator = self.access.authenticate(context, uow=uow)
        rows = uow.connection.execute(
            'SELECT s.*,e.agent_id FROM execution_sessions s '
            'JOIN execution_bindings b ON b.server_id=s.server_id AND b.executor_id=s.executor_id '
            'AND b.binding_id=s.binding_id JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id '
            'WHERE s.server_id=? AND s.session_id=? AND s.binding_id=? '
            'AND (? OR e.agent_id=?) LIMIT 2',
            (server_id, session_id, binding_id, operator, context.actor_agent_id)).fetchall()
        if not rows:
            raise _error(ErrorCode.NOT_FOUND, 'The session was not found in this credential scope.')
        if len(rows) != 1:
            raise _error(ErrorCode.CONFLICT, 'The session scope is ambiguous.')
        return rows[0]

    def _authority(self, uow, scope, *, grant_id=None, grant_revision=None):
        revisions = uow.connection.execute(
            'SELECT credential_epoch,authorization_revision,configuration_revision '
            'FROM execution_agent_revisions WHERE server_id=? AND agent_id=?',
            (scope['server_id'], scope['agent_id'])).fetchone()
        if revisions is None or any(revisions[k] != scope[k] for k in revisions.keys()):
            raise _error(ErrorCode.CONFLICT, 'The session capability revisions changed.')
        row = self.repo.authority(uow, scope)
        if (row is None or not row['is_active'] or not row['api_key_hash'] or
                row['lifecycle_state'] not in ('OPEN_PENDING', 'READY') or
                row['revoked_at'] is not None or row['protocol'] != 'nxl-r4' or
                row['activation_state'] != 'approved' or not row['enabled'] or
                row['health'] == 'quarantined' or row['workspace_status'] != 'READY' or
                row['realization_status'] != 'READY' or
                row['realization_revision'] != row['current_realization_revision'] or
                row['agent_id'] != scope['agent_id'] or row['subject_agent_id'] != scope['agent_id'] or
                row['actor_agent_id'] != scope['agent_id'] or row['binding_id'] != scope['binding_id'] or
                row['binding_revision'] != scope['binding_revision'] or
                row['workspace_id'] != scope['workspace_id'] or
                any(row[k] != scope['workspace_binding_id'] for k in (
                    'workspace_binding_id', 'binding_workspace_binding_id', 'realization_workspace_binding_id')) or
                row['owner_generation'] != scope['session_owner_generation'] or
                json.loads(row['expected_revisions_json']) != scope or
                row['admission_state'] not in ('ACCEPTED', 'DISPATCH_PENDING', 'DISPATCHED', 'RESOLVED_TERMINAL') or
                row['source_guard_digest'] != _agent_guard(uow.connection, scope['agent_id'])):
            raise _error(ErrorCode.CONFLICT, 'The session capability authority changed.')
        semantic = json.loads(row['semantic_payload'])
        if semantic['action'] != 'runtime.open':
            raise _error(ErrorCode.CONFLICT, 'A canonical opening operation is required.')
        selected_id = grant_id or row['dispatch_grant_id']
        if grant_id and row['dispatch_grant_id'] not in (None, grant_id):
            raise _error(ErrorCode.CONFLICT, 'The dispatched execution grant changed.')
        context = RuntimeRequestContext(scope['agent_id'], 'agent_key',
            credential_binding=row['api_key_hash'], execution_grant_id=selected_id,
            represented_agent_id=scope['agent_id'], workspace_id=scope['workspace_id'],
            endpoint_id=row['endpoint_id'])
        grant = self.access.authorize(context, action='open', endpoint_id=row['endpoint_id'],
            represented_agent_id=scope['agent_id'], workspace_id=scope['workspace_id'],
            substrate=semantic['payload']['mode'], uow=uow, audit=False, check_budget=False)
        if (grant is None or (grant_revision is not None and grant['revision'] != grant_revision) or
                _stamp(grant['expires_at']) <= _stamp(self.access.clock.now_iso())):
            raise _error(ErrorCode.PERMISSION_DENIED, 'A current session execution grant is required.')
        return row, grant

    def issue(self, *, context, session_id, request, mcp_url):
        required = {'capability_request_id', 'binding_id', 'audience', 'actions'}
        if (type(request) is not dict or not required <= request.keys() or
                not request.keys() <= required | {'replaces_capability_id'} or
                any(type(request[k]) is not str or not 1 <= len(request[k]) <= 160
                    for k in ('capability_request_id', 'binding_id')) or
                type(session_id) is not str or not 1 <= len(session_id) <= 160 or
                type(request['audience']) is not str or request['audience'] not in AUDIENCES or
                type(request['actions']) is not list or
                len(request['actions']) > 128 or any(type(a) is not str or not 1 <= len(a) <= 160
                    for a in request['actions']) or len(set(request['actions'])) != len(request['actions']) or
                (request.get('replaces_capability_id') is not None and
                 (type(request['replaces_capability_id']) is not str or
                  not 1 <= len(request['replaces_capability_id']) <= 160))):
            raise _error(ErrorCode.VALIDATION_ERROR, 'Invalid session capability request.')
        server_id = ensure_execution_installation(self.factory).server_id
        with self.factory.unit_of_work(write=False) as uow:
            target = self._target(uow, server_id=server_id, session_id=session_id,
                                  binding_id=request['binding_id'], context=context)
        _, revisions, _ = current_agent_revisions(self.factory, agent_id=target['agent_id'])
        body = dict(request, session_id=session_id, actions=sorted(request['actions']))
        if body.get('replaces_capability_id') is None:
            body.pop('replaces_capability_id', None)
        digest = hashlib.sha256(canonical_json(body)).hexdigest()
        with self.factory.unit_of_work() as uow:
            conn = uow.connection
            target = self._target(uow, server_id=server_id, session_id=session_id,
                                  binding_id=request['binding_id'], context=context)
            operation = conn.execute(
                'SELECT expected_revisions_json FROM execution_operations WHERE server_id=? '
                'AND executor_id=? AND operation_id=?',
                (server_id, target['executor_id'], target['open_operation_id'])).fetchone()
            if operation is None:
                raise _error(ErrorCode.CONFLICT, 'The session has no admitted opening operation.')
            scope = json.loads(operation['expected_revisions_json'])
            if ((scope['credential_epoch'], scope['authorization_revision'], scope['configuration_revision']) !=
                    (revisions.credential_epoch, revisions.authorization, revisions.configuration)):
                raise _error(ErrorCode.CONFLICT, 'The session credential revisions changed.')
            authority, grant = self._authority(uow, scope)
            if request['audience'] == 'nexus-mcp-session':
                require_method(uow, scope['agent_id'], 'mcp')
            prior = conn.execute('SELECT * FROM execution_session_capabilities WHERE server_id=? '
                'AND actor_agent_id=? AND request_id=?',
                (server_id, context.actor_agent_id, request['capability_request_id'])).fetchone()
            if prior:
                if prior['request_digest'] != digest:
                    raise _error(ErrorCode.CONFLICT, 'The capability request ID has different content.')
                raise _error('CREDENTIAL_MATERIAL_UNAVAILABLE', 'The capability secret is returned only once.',
                    capability_id=prior['capability_id'], recovery_allowed=self._replaceable(uow, authority, scope))
            live = conn.execute('SELECT * FROM execution_session_capabilities WHERE server_id=? '
                'AND executor_id=? AND session_id=? AND audience=? AND revoked_at IS NULL',
                (*self.repo.key(scope), request['audience'])).fetchall()
            replaces = request.get('replaces_capability_id')
            if live and (len(live) != 1 or replaces != live[0]['capability_id']):
                raise _error(ErrorCode.CONFLICT, 'This session already has a capability for the audience.')
            if replaces and (not live or live[0]['capability_id'] != replaces or
                    live[0]['scope_json'] != canonical_json(scope).decode() or
                    live[0]['actor_agent_id'] != context.actor_agent_id or
                    not self._replaceable(uow, authority, scope)):
                raise _error(ErrorCode.CONFLICT, 'The session capability cannot be replaced safely.')
            now = _stamp(self.access.clock.now_iso())
            expires = min(now + timedelta(seconds=120), _stamp(grant['expires_at']))
            lease = self.repo.latest(uow, scope)
            if lease is not None:
                if (lease['status'] != 'ACTIVE' or lease['scope_json'] != canonical_json(scope).decode() or
                        lease['grant_id'] != grant['grant_id']):
                    raise _error(ErrorCode.CONFLICT, 'The session lease is not active.')
                expires = min(expires, _stamp(lease['valid_until_server']))
            ttl = int((expires - now).total_seconds())
            if ttl < 1:
                raise _error(ErrorCode.CONFLICT, 'The session authority expires too soon.')
            capability_id = 'cap_' + secrets.token_hex(16)
            material = 'nxc4_' + secrets.token_urlsafe(32)
            if replaces:
                conn.execute('UPDATE execution_session_capabilities SET revoked_at=?,replaced_by=? '
                    'WHERE capability_id=? AND revoked_at IS NULL', (now.isoformat(), capability_id, replaces))
            conn.execute('INSERT INTO execution_session_capabilities(capability_id,secret_hash,audience,'
                'server_id,executor_id,session_id,subject_agent_id,actions_json,valid_until_server,'
                'actor_agent_id,request_id,request_digest,scope_json,source_grant_id,source_grant_revision,issued_at) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (capability_id, hashlib.sha256(material.encode()).hexdigest(), request['audience'],
                 *self.repo.key(scope), scope['agent_id'], canonical_json(body['actions']).decode(), expires.isoformat(),
                 context.actor_agent_id, request['capability_request_id'], digest, canonical_json(scope).decode(),
                 grant['grant_id'], grant['revision'], now.isoformat()))
        return dict(capability_id=capability_id, capability_ref='mcp-cap:' + capability_id
            if request['audience'] == 'nexus-mcp-session' else 'native-cap:' + capability_id,
            capability=material, scope=scope, audience=request['audience'], actions=body['actions'],
            expires_in=ttl, mcp_url=mcp_url if request['audience'] == 'nexus-mcp-session' else None)

    def _replaceable(self, uow, authority, scope):
        # Once dispatch may have delivered configuration, do not guess whether
        # the secret reached a harness. Expiry does not prove noninstallation.
        return (authority['lifecycle_state'] == 'OPEN_PENDING' and
                authority['dispatch_phase'] is None and self.repo.latest(uow, scope) is None)

    def authorize_call(self, *, token, audience, action, expected_scope):
        """Check the credential ceiling; the caller must still authorize its domain action.

        This port is deliberately not an agent-key fallback. An adapter must
        supply its own audience and the exact use-case scope before invoking
        the existing domain permission/claim checks.
        """
        if (type(token) is not str or not token.startswith('nxc4_') or not 32 <= len(token) <= 4096 or
                type(audience) is not str or audience not in AUDIENCES or
                type(action) is not str or type(expected_scope) is not dict):
            raise _error(ErrorCode.PERMISSION_DENIED, 'The session capability is invalid.')
        digest = hashlib.sha256(token.encode()).hexdigest()
        try:
            expected_json = canonical_json(expected_scope).decode()
        except (ValueError, TypeError, RecursionError):
            raise _error(ErrorCode.PERMISSION_DENIED, 'The session capability scope is invalid.') from None
        with self.factory.unit_of_work(write=False) as uow:
            return self._authorize_hash(uow, digest=digest, audience=audience,
                                        actions=(action,), expected_json=expected_json)

    def _authorize_hash(self, uow, *, digest, audience, actions=(), expected_json=None):
        credential = uow.connection.execute(
            'SELECT * FROM execution_session_capabilities WHERE secret_hash=?', (digest,)).fetchone()
        if (credential is None or credential['audience'] != audience or credential['revoked_at'] is not None or
                not credential['scope_json'] or
                (expected_json is not None and credential['scope_json'] != expected_json) or
                any(a not in json.loads(credential['actions_json']) for a in actions) or
                _stamp(credential['valid_until_server']) <= _stamp(self.access.clock.now_iso())):
            raise _error(ErrorCode.PERMISSION_DENIED, 'The session capability is unavailable in this scope.')
        expected_scope = json.loads(credential['scope_json'])
        authority, _ = self._authority(uow, expected_scope,
            grant_id=credential['source_grant_id'], grant_revision=credential['source_grant_revision'])
        lease = self.repo.latest(uow, expected_scope)
        if (authority['lifecycle_state'] != 'READY' or authority['lease_state'] != 'ACTIVE' or
                lease is None or lease['status'] != 'ACTIVE' or lease['applied_at'] is None or
                lease['scope_json'] != credential['scope_json'] or
                lease['grant_id'] != credential['source_grant_id'] or
                lease['source_grant_revision'] != credential['source_grant_revision'] or
                _stamp(lease['valid_until_server']) <= _stamp(self.access.clock.now_iso())):
            raise _error(ErrorCode.PERMISSION_DENIED, 'An active session and applied lease are required.')
        if audience == 'nexus-mcp-session':
            require_method(uow, expected_scope['agent_id'], 'mcp')
        return {'capability_id': credential['capability_id'], 'scope': dict(expected_scope),
                'audience': audience, 'actions': json.loads(credential['actions_json'])}

    def authenticate_transport(self, *, token, audience):
        from types import MappingProxyType
        from ..domain.execution_principal import ExecutionPrincipal
        if (type(token) is not str or not token.startswith('nxc4_') or
                not 32 <= len(token) <= 4096 or audience not in AUDIENCES):
            raise _error(ErrorCode.PERMISSION_DENIED, 'The session capability is invalid.')
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.factory.unit_of_work(write=False) as uow:
            credential = self._authorize_hash(uow, digest=digest, audience=audience)
        return ExecutionPrincipal(credential['capability_id'], digest, audience,
                                  MappingProxyType(credential['scope']))

    def authorize_principal(self, uow, *, principal, actions):
        return self._authorize_hash(uow, digest=principal.secret_hash,
            audience=principal.audience, actions=actions,
            expected_json=canonical_json(dict(principal.scope)).decode())
