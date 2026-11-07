"""Private bounded CAS storage, inside the caller's transaction only.

The host must authenticate and revalidate the selected OBS/native fences and OS
birth before calling replace_selection. A valid shape/digest is not that proof.
This module has no discovery, clock, commit, emitter, provider or public service.
"""
from datetime import datetime, timezone
import json
import re

from okto_nexus.domain.observation_correlation import (
    MAX_INT64, ObservationCorrelationError, correlation_digest, normalize_selection,
)
from okto_nexus.errors import ErrorCode, OktoNexusError


_OBS_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,159}\Z')
_COLUMNS = ('observed_instance_id', 'agent_id', 'workspace_id', 'schema_version', 'revision', 'state', 'server_id',
    'executor_id', 'session_id', 'selection_json', 'proof_json', 'correlation_digest',
    'verified_at', 'updated_at')


def _fail(code, reason):
    raise OktoNexusError(code, 'Observation correlation storage refused.', {'reason': reason})


def _text(value):
    if type(value) is not str or not 1 <= len(value) <= 160 or not value.isprintable() or value.strip() != value:
        _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_CORRELATION_INVALID')
    try:
        value.encode('utf-8')
    except UnicodeError:
        _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_CORRELATION_INVALID')
    return value


def _instance(value):
    if not _OBS_ID.fullmatch(_text(value)):
        _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_CORRELATION_INVALID')
    return value


def _expected(value):
    if type(value) is not int or not 0 <= value <= MAX_INT64:
        _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_CORRELATION_INVALID')
    return value


def _limit(value):
    if type(value) is not int or not 1 <= value <= 65536:
        _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_CORRELATION_INVALID_CAPACITY')
    return value


def _stamp(value):
    try:
        if type(value) is not str or len(value) > 64:
            raise ValueError
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')
    except (ValueError, OverflowError):
        _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_CORRELATION_INVALID_TIME')


def _json(value, maximum):
    try:
        result = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        if len(result.encode('utf-8')) > maximum:
            raise ValueError
        return result
    except (ValueError, TypeError, UnicodeError):
        _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_CORRELATION_INVALID')


def _decode(raw):
    if raw is None:
        return None
    row = dict(raw)
    try:
        _instance(row['observed_instance_id'])
        _text(row['agent_id'])
        _text(row['workspace_id'])
        if row['schema_version'] != 1 or type(row['revision']) is not int or not 1 <= row['revision'] <= MAX_INT64:
            raise ValueError
        updated = _stamp(row['updated_at'])
        if updated != row['updated_at']:
            raise ValueError
        selection = proof = digest = verified = provenance = None
        if row['state'] == 'selected':
            selection = normalize_selection(json.loads(row['selection_json']))
            proof = json.loads(row['proof_json'])
            digest = correlation_digest(selection, proof)
            if (digest != row['correlation_digest'] or selection['observed_instance_id'] != row['observed_instance_id']
                or selection['expected_correlation_revision'] + 1 != row['revision']
                or any(selection[key] != row[key] for key in ('server_id', 'executor_id', 'session_id'))
                or _json(selection, 8192) != row['selection_json'] or _json(proof, 2048) != row['proof_json']):
                raise ValueError
            verified = _stamp(row['verified_at'])
            if verified != row['verified_at'] or verified > updated:
                raise ValueError
            provenance = {key: proof[key] for key in ('external_binding_provenance', 'native_birth_provenance')}
        elif row['state'] not in ('cleared', 'revoked') or any(row[key] is not None for key in
            ('server_id', 'executor_id', 'session_id', 'selection_json', 'proof_json', 'correlation_digest', 'verified_at')):
            raise ValueError
    except (ValueError, TypeError, KeyError, ObservationCorrelationError, OktoNexusError):
        _fail(ErrorCode.DB_ERROR, 'OBSERVATION_CORRELATION_CORRUPT')
    return dict(observed_instance_id=row['observed_instance_id'], agent_id=row['agent_id'],
        workspace_id=row['workspace_id'], schema_version=1,
        revision=row['revision'], state=row['state'], selection=selection, proof=proof,
        digest=digest, provenance=provenance, verified_at=verified, updated_at=updated)


class SqliteObservationCorrelationRepo:
    def capacity(self, uow, *, max_records):
        """Operator-only inventory of all live selections and tombstones."""
        limit = _limit(max_records)
        row = uow.connection.execute('SELECT count(*) AS total, '
            "coalesce(sum(state='selected'),0) AS selected FROM observation_correlations").fetchone()
        return dict(limit=limit, total=row['total'], selected=row['selected'],
            tombstones=row['total'] - row['selected'], available=max(0, limit - row['total']),
            full=row['total'] >= limit)

    def get(self, uow, *, observed_instance_id):
        return _decode(uow.connection.execute('SELECT * FROM observation_correlations WHERE observed_instance_id=?',
            (_instance(observed_instance_id),)).fetchone())

    def get_scoped(self, uow, *, observed_instance_id, agent_id, workspace_id):
        return _decode(uow.connection.execute('SELECT * FROM observation_correlations '
            'WHERE observed_instance_id=? AND agent_id=? AND workspace_id=?',
            (_instance(observed_instance_id), _text(agent_id), _text(workspace_id))).fetchone())

    def get_for_session(self, uow, *, observed_instance_id, server_id, executor_id, session_id):
        """Exact namespace filter only; a returned selection is not current authority."""
        return _decode(uow.connection.execute('SELECT * FROM observation_correlations '
            "WHERE observed_instance_id=? AND state='selected' AND server_id=? AND executor_id=? AND session_id=?",
            (_instance(observed_instance_id), _text(server_id), _text(executor_id), _text(session_id))).fetchone())

    def _cas(self, uow, values, expected, max_records):
        expected = _expected(expected)
        max_records = _limit(max_records)
        if expected == MAX_INT64:
            _fail(ErrorCode.QUOTA_EXCEEDED, 'OBSERVATION_CORRELATION_REVISION_EXHAUSTED')
        values = dict(values, schema_version=1, revision=expected + 1)
        if expected == 0:
            # Capacity admission and insertion are one SQLite write statement.
            # Every row counts, including tombstones whose revision prevents ABA.
            statement = 'INSERT INTO observation_correlations (' + ','.join(_COLUMNS) + ') SELECT ' + ','.join(
                ':' + column for column in _COLUMNS) + (
                ' WHERE (SELECT count(*) FROM observation_correlations)<:max_records '
                'ON CONFLICT(observed_instance_id) DO NOTHING RETURNING *')
            values['max_records'] = max_records
        else:
            statement = 'UPDATE observation_correlations SET ' + ','.join(
                column + '=:' + column for column in _COLUMNS
                if column not in ('observed_instance_id', 'agent_id', 'workspace_id')) + (
                ' WHERE observed_instance_id=:observed_instance_id AND revision=:expected '
                'AND agent_id=:agent_id AND workspace_id=:workspace_id RETURNING *')
            values['expected'] = expected
        row = uow.connection.execute(statement, values).fetchone()
        if row is None:
            if expected == 0 and uow.connection.execute(
                'SELECT 1 FROM observation_correlations WHERE observed_instance_id=?',
                (values['observed_instance_id'],)).fetchone() is None:
                _fail(ErrorCode.QUOTA_EXCEEDED, 'OBSERVATION_CORRELATION_CAPACITY')
            _fail(ErrorCode.CONFLICT, 'OBSERVATION_CORRELATION_REVISION_CHANGED')
        return _decode(row)

    def replace_selection(self, uow, *, selection, proof, verified_at, now, max_records, agent_id, workspace_id):
        """Persist supplied host-verified metadata; performs no verification itself."""
        try:
            selected = normalize_selection(selection)
            digest = correlation_digest(selected, proof)
        except ObservationCorrelationError:
            _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_CORRELATION_INVALID')
        verified_at, now = _stamp(verified_at), _stamp(now)
        if verified_at > now:
            _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_CORRELATION_INVALID_TIME')
        values = dict(observed_instance_id=selected['observed_instance_id'], state='selected',
            agent_id=_text(agent_id), workspace_id=_text(workspace_id),
            **{key: selected[key] for key in ('server_id', 'executor_id', 'session_id')},
            selection_json=_json(selected, 8192), proof_json=_json(proof, 2048),
            correlation_digest=digest, verified_at=verified_at, updated_at=now)
        return self._cas(uow, values, selected['expected_correlation_revision'], max_records)

    def tombstone(self, uow, *, observed_instance_id, expected_revision, state, now, max_records, agent_id, workspace_id):
        """Clear/revoke by CAS; even an absent row creates revision-one tombstone."""
        if type(state) is not str or state not in ('cleared', 'revoked'):
            _fail(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_CORRELATION_INVALID')
        values = dict(observed_instance_id=_instance(observed_instance_id), state=state,
            agent_id=_text(agent_id), workspace_id=_text(workspace_id),
            server_id=None, executor_id=None, session_id=None, selection_json=None,
            proof_json=None, correlation_digest=None, verified_at=None, updated_at=_stamp(now))
        return self._cas(uow, values, expected_revision, max_records)
