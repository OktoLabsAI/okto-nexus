"""Operator-only inventory of recorded connections, never execution authority."""
import base64
import hashlib
import json

from ..errors import ErrorCode, OktoNexusError


def _invalid(message='Invalid connection catalog scope or cursor.'):
    return OktoNexusError(ErrorCode.VALIDATION_ERROR, message, {})


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Repeated cursor member')
        result[key] = value
    return result


class ConnectionCatalog:
    def __init__(self, *, factory, access, queries, clock):
        self.factory, self.access, self.queries, self.clock = factory, access, queries, clock

    def read(self, *, context, principal=None, filters=None, cursor=None, limit=25):
        with self.factory.unit_of_work(write=False) as uow:
            if context is None or not self.access.authenticate(context, uow=uow, require_feature=False):
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'An authenticated operator is required.', {})
            if filters is not None and type(filters) is not dict:
                raise _invalid()
            scope = dict(filters or {})
            if set(scope) - {'workspace_id', 'agent_id', 'executor_id', 'execution_location'}:
                raise _invalid()
            scope = {key: value for key, value in scope.items() if value is not None}
            if any(type(value) is not str or not 1 <= len(value) <= 160
                    or value != value.strip() or not value.isprintable() for value in scope.values()):
                raise _invalid()
            if scope.get('execution_location') not in (None, 'local', 'remote') or type(limit) is not int or not 1 <= limit <= 100:
                raise _invalid()
            if context.authentication_source == 'operator_session' and (type(principal) is not str or not 1 <= len(principal) <= 160):
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The authenticated human identity is unavailable.', {})
            server = uow.connection.execute('SELECT server_id FROM execution_installation WHERE singleton=1').fetchone()
            if server is None:
                raise OktoNexusError(ErrorCode.CONFLICT, 'Server installation identity is unavailable.', {})
            fence = hashlib.sha256(_canonical([server[0], context.authentication_source,
                context.actor_agent_id, principal if context.authentication_source == 'operator_session' else None,
                context.credential_binding, scope]).encode()).hexdigest()
            after = ('', '')
            saved = None
            if cursor is not None:
                try:
                    if type(cursor) is not str or not 1 <= len(cursor) <= 2048:
                        raise ValueError()
                    raw = base64.b64decode(cursor + '=' * (-len(cursor) % 4), altchars=b'-_', validate=True)
                    saved = json.loads(raw.decode('utf-8'), object_pairs_hook=_object)
                    if (type(saved) is not dict or set(saved) != {'version', 'kind', 'fence', 'revision', 'after', 'limit'}
                            or type(saved['version']) is not int or saved['version'] != 1
                            or saved['kind'] != 'connection_catalog' or saved['fence'] != fence
                            or type(saved['limit']) is not int or saved['limit'] != limit
                            or type(saved['after']) is not list or len(saved['after']) != 2
                            or any(type(value) is not str or not 1 <= len(value) <= 160 or not value.isprintable()
                                for value in saved['after']) or type(saved['revision']) is not str or len(saved['revision']) != 64):
                        raise ValueError()
                    after = tuple(saved['after'])
                except (ValueError, UnicodeError, TypeError, KeyError, RecursionError):
                    raise _invalid() from None
            total, material, rows = self.queries.read(uow, server_id=server[0], scope=scope, after=after, limit=limit)
            revision = hashlib.sha256(material.encode('utf-8')).hexdigest()
            if saved is not None and saved['revision'] != revision:
                raise OktoNexusError(ErrorCode.CONFLICT, 'The connection catalog changed. Restart its pagination.',
                    {'reason': 'CATALOG_CHANGED'})
            more = len(rows) > limit
            items = rows[:limit]
            following = None
            if more:
                last = items[-1]
                value = dict(version=1, kind='connection_catalog', fence=fence, revision=revision,
                    after=[last['executor_id'], last['binding_id']], limit=limit)
                following = base64.urlsafe_b64encode(_canonical(value).encode()).decode().rstrip('=')
            return dict(version=1, server_id=server[0], scope=scope, revision=revision,
                generated_at=self.clock.now_iso(), items=items, total=total, total_is_exact=True,
                has_more=more, next_cursor=following,
                cursor_integrity='unsigned_scope_checked', requires_canonical_revalidation=True)
