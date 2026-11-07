"""Bounded external telemetry storage, inside the caller's transaction.

No clock, authentication cache, commit, event emitter or canonical work mutation.
The service authenticates current authority and emits metadata events in this
same UoW. All reads are passive, including expiration and missing-row reads.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math

from ....errors import ErrorCode, OktoNexusError


MAX_INTEGER = (1 << 63) - 1
AUDIENCE = 'observations.publish'
DEFAULT_RATES = {'source': (60, 20), 'agent': (1920, 80), 'installation': (8192, 512)}
_CREDIT = 60_000_000  # One report, with exact integer microsecond refill.
_RECEIPT = ('observed_instance_id', 'generation', 'sequence', 'report_hash', 'received_at', 'valid_until')
_ORPHAN_BUCKET = """(b.scope_kind='source' AND NOT EXISTS
    (SELECT 1 FROM observation_sources s WHERE s.source_id=b.scope_id)) OR
    (b.scope_kind='agent' AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.agent_id=b.scope_id))"""
_SOURCE = """SELECT s.*, COALESCE((SELECT json_group_array(workspace_id) FROM
    (SELECT workspace_id FROM observation_source_workspaces WHERE source_id=s.source_id
     ORDER BY workspace_id)), '[]') AS allowed_workspace_ids FROM observation_sources s"""


def _fail(code, reason):
    raise OktoNexusError(code, 'Observation storage request refused.', {'reason': reason})


def _positive(value, name, maximum=MAX_INTEGER):
    if type(value) is not int or not 1 <= value <= maximum:
        _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_INVALID_' + name.upper())
    return value


def _text(value, name, maximum=256):
    if type(value) is not str or not 1 <= len(value) <= maximum:
        _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_INVALID_' + name.upper())
    try:
        value.encode('utf-8')
    except UnicodeError:
        _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_INVALID_' + name.upper())
    return value


def _time(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError, OverflowError):
        _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_INVALID_TIME')


def _stamp(value):
    return _time(value).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _micros(value):
    delta = _time(value) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _workspaces(values):
    if type(values) is not list or not 1 <= len(values) <= 100:
        _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_INVALID_WORKSPACES')
    result = sorted({_text(value, 'workspace') for value in values})
    if len(result) != len(values):
        _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_DUPLICATE_WORKSPACE')
    return result


def _source(row):
    if row is None:
        return None
    result = dict(row)
    result['enabled'] = bool(result['enabled'])
    result['allowed_workspace_ids'] = json.loads(result['allowed_workspace_ids'])
    return result


def _agent(row):
    try:
        permissions = json.loads(row['permissions'])
    except (TypeError, ValueError):
        permissions = {}
    return dict(agent_id=row['agent_id'], is_active=bool(row['is_active']),
                api_key_hash=row['api_key_hash'], deleted_at=row['deleted_at'],
                permissions=permissions if isinstance(permissions, dict) else {})


def _head(row):
    if row is None or row['report_json'] is None:
        return None
    result = json.loads(row['report_json'])
    result.update({key: row[key] for key in (*_RECEIPT, 'source_revision', 'publisher_token_id',
                                           'last_completion_ref', 'last_completion_received_at')})
    return result


def _receipt(head):
    return {key: head[key] for key in _RECEIPT}


class SqliteObservationRepo:
    def _allocate(self, uow):
        row = uow.connection.execute('UPDATE observation_installation SET last_generation=last_generation+1 '
            'WHERE singleton=1 AND last_generation<? RETURNING last_generation', (MAX_INTEGER,)).fetchone()
        if row is None:
            _fail(ErrorCode.QUOTA_EXCEEDED, 'OBSERVATION_GENERATION_EXHAUSTED')
        return row[0]

    def get_source(self, uow, *, source_id):
        return _source(uow.connection.execute(_SOURCE + ' WHERE s.source_id=?', (source_id,)).fetchone())

    def list_sources(self, uow, *, agent_id=None, after=None, limit=100):
        return [_source(row) for row in uow.connection.execute(_SOURCE +
            ' WHERE (? IS NULL OR s.agent_id=?) AND (? IS NULL OR s.source_id>?) '
            'ORDER BY s.source_id LIMIT ?', (agent_id, agent_id, after, after, _positive(limit, 'limit', 201)))]

    def _require_source(self, uow, source_id, expected_revision, *, enabled=True):
        _positive(expected_revision, 'revision')
        source = self.get_source(uow, source_id=source_id)
        if source is None:
            _fail(ErrorCode.NOT_FOUND, 'OBSERVATION_SOURCE_NOT_FOUND')
        if source['revision'] != expected_revision:
            _fail(ErrorCode.CONFLICT, 'OBSERVATION_SOURCE_REVISION_CHANGED')
        if enabled and (not source['enabled'] or source['revoked_at'] is not None):
            _fail(ErrorCode.PERMISSION_DENIED, 'OBSERVATION_SOURCE_REVOKED')
        return source

    def create_source(self, uow, *, agent_id, source_kind, workspace_ids, registration_ref,
                      now, source_limit=32, installation_limit=4096):
        workspace_ids, now = _workspaces(workspace_ids), _stamp(now)
        _text(registration_ref, 'registration_ref')
        if source_kind not in ('herdr', 'hook', 'custom'):
            _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_INVALID_SOURCE_KIND')
        intent = hashlib.sha256(_json([source_kind, workspace_ids]).encode('utf-8')).hexdigest()
        existing = uow.connection.execute(_SOURCE + ' WHERE s.agent_id=? AND s.registration_ref=?',
                                          (agent_id, registration_ref)).fetchone()
        if existing is not None:
            if existing['registration_hash'] != intent:
                _fail(ErrorCode.CONFLICT, 'OBSERVATION_REGISTRATION_CONFLICT')
            return _source(existing)
        counts = uow.connection.execute('SELECT count(*),coalesce(sum(agent_id=?),0) '
                                        'FROM observation_sources', (agent_id,)).fetchone()
        if counts[0] >= _positive(installation_limit, 'installation_limit', 65536) or counts[1] >= _positive(source_limit, 'source_limit', 1024):
            _fail(ErrorCode.QUOTA_EXCEEDED, 'OBSERVATION_SOURCE_CAPACITY')
        source_id = f'obs_src_{self._allocate(uow):016x}'
        uow.connection.execute('INSERT INTO observation_sources VALUES(?,?,?,?,?,1,1,NULL,?,?)',
            (source_id, agent_id, source_kind, registration_ref, intent, now, now))
        uow.connection.executemany('INSERT INTO observation_source_workspaces VALUES(?,?)',
                                  [(source_id, workspace) for workspace in workspace_ids])
        return self.get_source(uow, source_id=source_id)

    def update_source(self, uow, *, source_id, expected_revision, now, workspace_ids=None, enabled=None):
        source = self._require_source(uow, source_id, expected_revision, enabled=False)
        now = _stamp(now)
        if enabled is not None and type(enabled) is not bool:
            _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_INVALID_ENABLED')
        workspaces = source['allowed_workspace_ids'] if workspace_ids is None else _workspaces(workspace_ids)
        next_enabled = source['enabled'] if enabled is None else enabled
        revoked = (None if next_enabled else source['revoked_at'] or now)
        if (workspaces == source['allowed_workspace_ids'] and next_enabled == source['enabled']
                and revoked == source['revoked_at']):
            return source
        if source['revision'] == MAX_INTEGER:
            _fail(ErrorCode.QUOTA_EXCEEDED, 'OBSERVATION_REVISION_EXHAUSTED')
        uow.connection.execute('UPDATE observation_sources SET revision=revision+1,enabled=?,revoked_at=?,updated_at=? '
                               'WHERE source_id=? AND revision=?', (int(next_enabled), revoked, now, source_id, expected_revision))
        if workspaces != source['allowed_workspace_ids']:
            uow.connection.execute('DELETE FROM observation_source_workspaces WHERE source_id=?', (source_id,))
            uow.connection.executemany('INSERT INTO observation_source_workspaces VALUES(?,?)',
                                      [(source_id, workspace) for workspace in workspaces])
        return self.get_source(uow, source_id=source_id)

    def revoke_source(self, uow, *, source_id, expected_revision, now):
        return self.update_source(uow, source_id=source_id, expected_revision=expected_revision, now=now, enabled=False)

    def create_instance(self, uow, *, source_id, expected_revision, workspace_id, external_instance_ref,
                        now, instance_limit=4096):
        source = self._require_source(uow, source_id, expected_revision)
        _text(external_instance_ref, 'external_instance_ref')
        now = _stamp(now)
        if workspace_id not in source['allowed_workspace_ids']:
            _fail(ErrorCode.PERMISSION_DENIED, 'OBSERVATION_WORKSPACE_NOT_APPROVED')
        existing = uow.connection.execute('SELECT * FROM observation_instances WHERE source_id=? '
            'AND workspace_id=? AND external_instance_ref=?', (source_id, workspace_id, external_instance_ref)).fetchone()
        if existing is not None:
            return dict(existing)
        if uow.connection.execute('SELECT count(*) FROM observation_instances').fetchone()[0] >= _positive(instance_limit, 'instance_limit', 65536):
            _fail(ErrorCode.QUOTA_EXCEEDED, 'OBSERVATION_INSTANCE_CAPACITY')
        generation = self._allocate(uow)
        identity = f'obs_inst_{generation:016x}'
        uow.connection.execute('INSERT INTO observation_instances VALUES(?,?,?,?,?,?,?)',
            (identity, source_id, workspace_id, external_instance_ref, generation, now, now))
        return dict(uow.connection.execute('SELECT * FROM observation_instances WHERE observed_instance_id=?', (identity,)).fetchone())

    def _require_instance(self, uow, source_id, expected_revision, identity, generation, *, available=True):
        source = self._require_source(uow, source_id, expected_revision, enabled=available)
        _positive(generation, 'generation')
        instance = uow.connection.execute('SELECT * FROM observation_instances WHERE observed_instance_id=? '
                                         'AND source_id=?', (identity, source_id)).fetchone()
        if instance is None:
            _fail(ErrorCode.NOT_FOUND, 'OBSERVATION_INSTANCE_NOT_FOUND')
        if instance['generation'] != generation:
            _fail(ErrorCode.CONFLICT, 'OBSERVATION_INSTANCE_GENERATION_CHANGED')
        if available and instance['workspace_id'] not in source['allowed_workspace_ids']:
            _fail(ErrorCode.PERMISSION_DENIED, 'OBSERVATION_WORKSPACE_NOT_APPROVED')
        return dict(instance)

    def rotate_instance(self, uow, *, source_id, expected_revision, observed_instance_id, expected_generation, now):
        self._require_instance(uow, source_id, expected_revision, observed_instance_id, expected_generation)
        now, generation = _stamp(now), self._allocate(uow)
        uow.connection.execute('DELETE FROM observation_heads WHERE observed_instance_id=?', (observed_instance_id,))
        uow.connection.execute('UPDATE observation_instances SET generation=?,updated_at=? '
            'WHERE observed_instance_id=? AND generation=?', (generation, now, observed_instance_id, expected_generation))
        return dict(uow.connection.execute('SELECT * FROM observation_instances WHERE observed_instance_id=?', (observed_instance_id,)).fetchone())

    def retire_instance(self, uow, *, source_id, expected_revision, observed_instance_id, expected_generation, now):
        instance = self._require_instance(uow, source_id, expected_revision, observed_instance_id, expected_generation, available=False)
        now = _stamp(now)
        uow.connection.execute('UPDATE observation_tokens SET revoked_at=? WHERE revoked_at IS NULL AND token_id IN '
            '(SELECT token_id FROM observation_token_instances WHERE observed_instance_id=?)', (now, observed_instance_id))
        uow.connection.execute('DELETE FROM observation_instances WHERE observed_instance_id=?', (observed_instance_id,))
        return dict(instance, retired_at=now)

    def list_instances(self, uow, *, source_id, after=None, limit=100):
        return [dict(row) for row in uow.connection.execute('SELECT * FROM observation_instances WHERE source_id=? '
            'AND (? IS NULL OR observed_instance_id>?) ORDER BY observed_instance_id LIMIT ?',
            (source_id, after, after, _positive(limit, 'limit', 201)))]

    def issue_token(self, uow, *, source_id, expected_revision, token_hash, instance_grants, issuer_agent_id,
                    now, expires_at, max_live=8):
        source = self._require_source(uow, source_id, expected_revision)
        now, expires_at = _stamp(now), _stamp(expires_at)
        if not 0 < (_time(expires_at) - _time(now)).total_seconds() <= 900:
            _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_TOKEN_LIFETIME')
        if type(token_hash) is not str or len(token_hash) != 64 or any(c not in '0123456789abcdef' for c in token_hash):
            _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_TOKEN_HASH')
        if type(instance_grants) is not list or not 1 <= len(instance_grants) <= 100:
            _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_TOKEN_SCOPE')
        requested = {}
        for grant in instance_grants:
            if type(grant) is not dict or set(grant) != {'observed_instance_id', 'generation'}:
                _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_TOKEN_SCOPE')
            identity = _text(grant['observed_instance_id'], 'instance')
            if identity in requested:
                _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_DUPLICATE_INSTANCE')
            requested[identity] = _positive(grant['generation'], 'generation')
        rows = uow.connection.execute('SELECT * FROM observation_instances WHERE source_id=? AND observed_instance_id IN (' +
            ','.join('?' for _ in requested) + ')', (source_id, *requested)).fetchall()
        if len(rows) != len(requested) or any(row['generation'] != requested[row['observed_instance_id']]
                or row['workspace_id'] not in source['allowed_workspace_ids'] for row in rows):
            _fail(ErrorCode.CONFLICT, 'OBSERVATION_TOKEN_SCOPE_CHANGED')
        self._prune_tokens(uow, now=now, limit=100, source_id=source_id)
        live, unreferenced = uow.connection.execute('SELECT coalesce(sum(revoked_at IS NULL AND expires_at>?),0),'
            'coalesce(sum(NOT EXISTS(SELECT 1 FROM observation_heads h WHERE h.publisher_token_id=t.token_id)),0) '
            'FROM observation_tokens t WHERE source_id=?', (now, source_id)).fetchone()
        if live >= _positive(max_live, 'max_live', 64) or unreferenced >= max_live:
            _fail(ErrorCode.QUOTA_EXCEEDED, 'OBSERVATION_TOKEN_CAPACITY')
        token_id = f'obs_token_{self._allocate(uow):016x}'
        uow.connection.execute('INSERT INTO observation_tokens VALUES(?,?,?,?,?,?,?,?,NULL)',
            (token_id, token_hash, AUDIENCE, source_id, expected_revision, issuer_agent_id, now, expires_at))
        uow.connection.executemany('INSERT INTO observation_token_instances VALUES(?,?,?,?)',
            [(token_id, row['observed_instance_id'], row['generation'], row['workspace_id']) for row in rows])
        token = dict(uow.connection.execute('SELECT * FROM observation_tokens WHERE token_id=?', (token_id,)).fetchone())
        token.pop('token_hash')
        token['instance_grants'] = [dict(observed_instance_id=row['observed_instance_id'], generation=row['generation'],
                                        workspace_id=row['workspace_id']) for row in rows]
        return token

    def revoke_token(self, uow, *, source_id, token_id, now):
        token = uow.connection.execute('SELECT * FROM observation_tokens WHERE source_id=? AND token_id=?', (source_id, token_id)).fetchone()
        if token is None:
            _fail(ErrorCode.NOT_FOUND, 'OBSERVATION_TOKEN_NOT_FOUND')
        if token['revoked_at'] is None:
            uow.connection.execute('UPDATE observation_tokens SET revoked_at=? WHERE token_id=?', (_stamp(now), token_id))
        result = dict(uow.connection.execute('SELECT * FROM observation_tokens WHERE token_id=?', (token_id,)).fetchone())
        result.pop('token_hash')
        return result

    def get_token_by_hash(self, uow, *, token_hash):
        row = uow.connection.execute('SELECT * FROM observation_tokens WHERE token_hash=?', (token_hash,)).fetchone()
        return dict(row) if row else None

    def list_tokens(self, uow, *, source_id, after=None, limit=100):
        rows = uow.connection.execute('SELECT token_id,audience,source_id,source_revision,issuer_agent_id,'
            'created_at,expires_at,revoked_at FROM observation_tokens WHERE source_id=? AND (? IS NULL OR token_id>?) '
            'ORDER BY token_id LIMIT ?', (source_id, after, after, _positive(limit, 'limit', 201)))
        return [dict(row) for row in rows]

    def get_publish_facts(self, uow, *, token_hash):
        token = self.get_token_by_hash(uow, token_hash=token_hash)
        if token is None:
            return None
        source = self.get_source(uow, source_id=token['source_id'])
        agent = uow.connection.execute('SELECT agent_id,is_active,api_key_hash,deleted_at,permissions FROM agents '
                                        'WHERE agent_id=?', (source['agent_id'],)).fetchone()
        rows = uow.connection.execute('SELECT g.observed_instance_id,g.generation AS granted_generation,'
            'g.workspace_id AS granted_workspace,i.source_id,i.workspace_id,i.external_instance_ref,i.generation,'
            'i.created_at,i.updated_at,h.sequence,h.report_hash,h.received_at,h.valid_until,h.report_json,'
            'h.source_revision,h.publisher_token_id,h.last_completion_ref,h.last_completion_received_at FROM observation_token_instances g '
            'JOIN observation_instances i USING(observed_instance_id) LEFT JOIN observation_heads h USING(observed_instance_id) '
            'WHERE g.token_id=? ORDER BY g.observed_instance_id', (token['token_id'],)).fetchall()
        instances, grants, heads = {}, {}, {}
        for row in rows:
            identity = row['observed_instance_id']
            instances[identity] = {key: row[key] for key in ('observed_instance_id', 'source_id', 'workspace_id',
                'external_instance_ref', 'generation', 'created_at', 'updated_at')}
            grants[identity] = dict(observed_instance_id=identity, generation=row['granted_generation'], workspace_id=row['granted_workspace'])
            if row['report_json'] is not None:
                heads[identity] = _head(row)
        return dict(token=token, source=source, agent=_agent(agent), grants=grants, instances=instances, heads=heads)

    def get_head(self, uow, *, observed_instance_id):
        return _head(uow.connection.execute('SELECT * FROM observation_heads WHERE observed_instance_id=?', (observed_instance_id,)).fetchone())

    def check_sequence(self, uow, *, observed_instance_id, generation, sequence, report_hash):
        _positive(generation, 'generation')
        _positive(sequence, 'sequence')
        instance = uow.connection.execute('SELECT generation FROM observation_instances WHERE observed_instance_id=?', (observed_instance_id,)).fetchone()
        if instance is None or instance['generation'] != generation:
            _fail(ErrorCode.CONFLICT, 'OBSERVATION_INSTANCE_GENERATION_CHANGED')
        head = self.get_head(uow, observed_instance_id=observed_instance_id)
        if head is not None:
            if head['generation'] != generation or sequence < head['sequence']:
                _fail(ErrorCode.CONFLICT, 'OBSERVATION_SEQUENCE_CONFLICT')
            if sequence == head['sequence']:
                if report_hash != head['report_hash']:
                    _fail(ErrorCode.CONFLICT, 'OBSERVATION_SEQUENCE_CONFLICT')
                return _receipt(head)
        return None

    def store_report(self, uow, *, report, report_hash, source_revision, publisher_token_id, received_at, valid_until):
        received_at, valid_until = _stamp(received_at), _stamp(valid_until)
        identity, generation = report['observed_instance_id'], report['generation']
        self._require_instance(uow, report['source_id'], source_revision, identity, generation)
        authority = uow.connection.execute('SELECT 1 FROM observation_tokens t JOIN observation_token_instances g '
            'USING(token_id) WHERE t.token_id=? AND t.source_id=? AND t.source_revision=? AND t.audience=? '
            'AND t.revoked_at IS NULL AND t.expires_at>? AND g.observed_instance_id=? AND g.generation=?',
            (publisher_token_id, report['source_id'], source_revision, AUDIENCE, received_at, identity, generation)).fetchone()
        if authority is None:
            _fail(ErrorCode.PERMISSION_DENIED, 'OBSERVATION_TOKEN_REVOKED')
        existing = self.check_sequence(uow, observed_instance_id=identity, generation=generation,
                                      sequence=report['sequence'], report_hash=report_hash)
        if existing is not None:
            return existing
        if valid_until <= received_at:
            _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_REPORT_EXPIRED')
        completion = report.get('current_completion_ref')
        uow.connection.execute('INSERT INTO observation_heads VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) '
            'ON CONFLICT(observed_instance_id) DO UPDATE SET generation=excluded.generation,source_revision=excluded.source_revision,'
            'publisher_token_id=excluded.publisher_token_id,sequence=excluded.sequence,report_hash=excluded.report_hash,'
            'state=excluded.state,evidence=excluded.evidence,observed_at=excluded.observed_at,received_at=excluded.received_at,'
            'valid_until=excluded.valid_until,report_json=excluded.report_json,'
            'last_completion_ref=COALESCE(excluded.last_completion_ref,observation_heads.last_completion_ref),'
            'last_completion_received_at=CASE WHEN excluded.last_completion_ref IS NOT NULL '
            'AND excluded.last_completion_ref IS NOT observation_heads.last_completion_ref '
            'THEN excluded.received_at ELSE observation_heads.last_completion_received_at END '
            'WHERE observation_heads.generation=excluded.generation AND observation_heads.sequence<excluded.sequence',
            (identity, generation, source_revision, publisher_token_id, report['sequence'], report_hash, report['state'],
             report['evidence'], _stamp(report['observed_at']), received_at, valid_until, _json(report),
             completion, received_at if completion is not None else None))
        return _receipt(self.get_head(uow, observed_instance_id=identity))

    def consume_budget(self, uow, *, source_id, agent_id, cost, now, rates=None):
        _positive(cost, 'cost', 100)
        rates = DEFAULT_RATES if rates is None else rates
        if type(rates) is not dict or set(rates) != set(DEFAULT_RATES):
            _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_RATE_POLICY')
        now_us = _micros(now)
        identities = [('agent', agent_id), ('installation', 'singleton')]
        if source_id is not None:
            identities.insert(0, ('source', source_id))
        staged, retry_us = [], 0
        for kind, identity in identities:
            _text(identity, 'rate_scope')
            spec = rates[kind]
            if type(spec) not in (tuple, list) or len(spec) != 2:
                _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_RATE_POLICY')
            rate, burst = (_positive(value, 'rate', 1_000_000) for value in spec)
            capacity = burst * _CREDIT
            row = uow.connection.execute('SELECT * FROM observation_rate_buckets WHERE scope_kind=? AND scope_id=?', (kind, identity)).fetchone()
            anchor = now_us if row is None else max(now_us, row['last_refill_us'])
            balance = capacity if row is None else min(capacity, row['balance'] + max(0, now_us - row['last_refill_us']) * rate)
            needed = cost * _CREDIT
            if needed > balance:
                retry_us = max(retry_us, (needed - balance + rate - 1) // rate)
            remaining = max(0, balance - needed)
            full_at = anchor + (capacity - remaining + rate - 1) // rate
            staged.append((kind, identity, remaining, anchor, full_at))
        if retry_us:
            return dict(allowed=False, retry_after_seconds=max(1, math.ceil(retry_us / 1_000_000)))
        uow.connection.executemany('INSERT INTO observation_rate_buckets VALUES(?,?,?,?,?) '
            'ON CONFLICT(scope_kind,scope_id) DO UPDATE SET balance=excluded.balance,'
            'last_refill_us=excluded.last_refill_us,full_at_us=excluded.full_at_us', staged)
        return dict(allowed=True, retry_after_seconds=0)

    def list_current(self, uow, *, agent_id=None, workspace_id=None, source_id=None, after=None, limit=100):
        # One page-bounded SELECT. No expiry updates, credential touch or event.
        rows = uow.connection.execute('SELECT i.*,s.agent_id,s.source_kind,s.registration_ref,s.registration_hash,'
            's.revision,s.enabled,s.revoked_at,s.created_at AS source_created_at,s.updated_at AS source_updated_at,'
            "(SELECT json_group_array(workspace_id) FROM observation_source_workspaces w WHERE w.source_id=s.source_id) AS allowed_workspace_ids,"
            'a.is_active,a.api_key_hash,a.deleted_at,a.permissions,h.generation AS head_generation,h.source_revision,'
            'h.publisher_token_id,h.sequence,h.report_hash,h.received_at,h.valid_until,h.report_json,'
            'h.last_completion_ref,h.last_completion_received_at,'
            't.revoked_at AS publisher_revoked_at FROM observation_instances i JOIN observation_sources s USING(source_id) '
            'JOIN agents a ON a.agent_id=s.agent_id LEFT JOIN observation_heads h USING(observed_instance_id) '
            'LEFT JOIN observation_tokens t ON t.token_id=h.publisher_token_id '
            'WHERE (? IS NULL OR s.agent_id=?) AND (? IS NULL OR i.workspace_id=?) AND (? IS NULL OR i.source_id=?) '
            'AND (? IS NULL OR i.observed_instance_id>?) ORDER BY i.observed_instance_id LIMIT ?',
            (agent_id, agent_id, workspace_id, workspace_id, source_id, source_id, after, after, _positive(limit, 'limit', 201))).fetchall()
        # Aggregate only sources present on this page, across their instances;
        # an old instance cannot make an actively reporting source look silent.
        sources = sorted({row['source_id'] for row in rows})
        continuity = {} if not sources else {row['source_id']: row['last_received_at'] for row in uow.connection.execute(
            'SELECT i.source_id,max(h.received_at) AS last_received_at FROM observation_instances i '
            'JOIN observation_heads h USING(observed_instance_id) WHERE i.source_id IN (' + ','.join('?' for _ in sources) +
            ') GROUP BY i.source_id', sources)}
        result = []
        for row in rows:
            instance = {key: row[key] for key in ('observed_instance_id', 'source_id', 'workspace_id', 'external_instance_ref', 'generation', 'created_at', 'updated_at')}
            source = _source({key: row[key] for key in ('source_id', 'agent_id', 'source_kind', 'registration_ref', 'registration_hash', 'revision', 'enabled', 'revoked_at', 'allowed_workspace_ids')})
            source.update(created_at=row['source_created_at'], updated_at=row['source_updated_at'])
            head = _head(dict(row, generation=row['head_generation']))
            result.append(dict(instance=instance, source=source, agent=_agent(row), head=head,
                               publisher_revoked=row['publisher_revoked_at'] is not None,
                               source_last_received_at=continuity.get(row['source_id'])))
        return result

    def _prune_tokens(self, uow, *, now, limit, source_id=None):
        return uow.connection.execute('DELETE FROM observation_tokens WHERE token_id IN '
            '(SELECT t.token_id FROM observation_tokens t WHERE (? IS NULL OR source_id=?) '
            'AND (expires_at<=? OR revoked_at IS NOT NULL) AND NOT EXISTS '
            '(SELECT 1 FROM observation_heads h WHERE h.publisher_token_id=t.token_id) '
            'ORDER BY expires_at,token_id LIMIT ?)', (source_id, source_id, now, limit)).rowcount

    def count_prunable(self, uow, *, now):
        now = _stamp(now)
        tokens = uow.connection.execute('SELECT count(*) FROM observation_tokens t WHERE (expires_at<=? OR revoked_at IS NOT NULL) '
            'AND NOT EXISTS(SELECT 1 FROM observation_heads h WHERE h.publisher_token_id=t.token_id)', (now,)).fetchone()[0]
        buckets = uow.connection.execute('SELECT count(*) FROM observation_rate_buckets b WHERE ' + _ORPHAN_BUCKET).fetchone()[0]
        return dict(tokens=tokens, rate_buckets=buckets)

    def prune(self, uow, *, now, limit=500):
        now, limit = _stamp(now), _positive(limit, 'limit', 1000)
        tokens = self._prune_tokens(uow, now=now, limit=limit)
        # Never use old-policy full_at to discard a current entity's quota:
        # lowering refill rates must not turn cleanup into a fresh burst.
        buckets = uow.connection.execute('DELETE FROM observation_rate_buckets WHERE (scope_kind,scope_id) IN '
            '(SELECT scope_kind,scope_id FROM observation_rate_buckets b WHERE ' + _ORPHAN_BUCKET +
            ' ORDER BY scope_kind,scope_id LIMIT ?)', (limit - tokens,)).rowcount
        return dict(tokens=tokens, rate_buckets=buckets)

    def prune_events(self, uow, *, cutoff, max_events=20000, limit=500):
        cutoff, limit = _stamp(cutoff), _positive(limit, 'limit', 1000)
        _positive(max_events, 'max_events')
        return uow.connection.execute("DELETE FROM events WHERE event_id IN (SELECT event_id FROM events WHERE type GLOB 'observation.*' "
            "AND (created_at<? OR event_id<=COALESCE((SELECT event_id FROM events WHERE type GLOB 'observation.*' "
            'ORDER BY event_id DESC LIMIT 1 OFFSET ?),-1)) ORDER BY event_id LIMIT ?)', (cutoff, max_events, limit)).rowcount

    def count_prunable_events(self, uow, *, cutoff, max_events=20000):
        cutoff = _stamp(cutoff)
        _positive(max_events, 'max_events')
        return uow.connection.execute("SELECT count(*) FROM events WHERE type GLOB 'observation.*' "
            "AND (created_at<? OR event_id<=COALESCE((SELECT event_id FROM events WHERE type GLOB 'observation.*' "
            'ORDER BY event_id DESC LIMIT 1 OFFSET ?),-1))', (cutoff, max_events)).fetchone()[0]
