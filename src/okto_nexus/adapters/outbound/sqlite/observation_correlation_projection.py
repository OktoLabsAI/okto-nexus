"""Private, passive correlation enrichment in the caller's authenticated snapshot.

The caller supplies already-authorized OBS IDs and applies current OBS availability
and canonical_matches before publishing any reference. This module never opens a
UoW, reads native state/artifacts, or grants authority. Its returned correlation
contains private proof and MUST NOT be copied directly into a public DTO.
"""
from datetime import datetime
import hashlib
import json
import sqlite3
import time

from nexus_connector_core import CoreError, decode_r4_frame
from nexus_connector_core.frame_codec import MAX_FRAME_BYTES

from ....errors import ErrorCode, OktoNexusError
from .observation_correlation_facts import SESSION_SQL
from .observation_correlations_repo import _decode, _instance


MAX_RECORDS = 65536
QUERY_SECONDS = 5.0
MAX_NATIVE_BYTES = 65536
MAX_RECEIPT_METADATA_BYTES = 2048
# UTF-8 serialized bytes retained by this result, not a bound on Python RSS.
MAX_RESULT_BYTES = 32 * 1024 * 1024
_FUNCTION = 'nexus_obs_receipt_metadata_v1'
_SESSION_FIELDS = '''server_id executor_id session_id open_operation_id binding_id
workspace_binding_id workspace_id owner_generation stream_epoch lifecycle_state
lease_state kind control_state revoked_at owner_instance_id executor_generation
subject_agent_id opening_workspace_id opening_action opening_binding_id
opening_workspace_binding_id opening_session_id expected_revisions_json
binding_revision binding_workspace_binding_id realization_revision
current_realization_revision realization_status realization_agent_id
realization_workspace_binding_id endpoint_agent_id endpoint_workspace_id protocol
endpoint_enabled activation_state health bound_workspace_id workspace_status'''.split()
_CORRELATION_FIELDS = '''observed_instance_id agent_id workspace_id schema_version
revision state server_id executor_id session_id selection_json proof_json
correlation_digest verified_at updated_at'''.split()


def _json_object(alias, fields):
    return 'json_object(' + ','.join("'" + key + "'," + alias + '.' + key for key in fields) + ')'


_NATIVE = _json_object('ns', _SESSION_FIELDS)
_OPERATION = _json_object('o', '''server_id executor_id operation_id subject_agent_id
binding_id workspace_id workspace_binding_id session_id action intent_hash expected_revisions_json'''.split())
# The sole canonical receipt producer uses strftime('%Y-%m-%dT%H:%M:%fZ','now').
# Trust only that fixed UTC/millisecond representation. A Julian-day roundtrip
# also rejects impossible calendar dates instead of accepting SQLite's spelling
# of them. Invalid/legacy spellings are unknown, never a reason to use an older
# receipt. This is a bounded SQL scalar check, not a frame decode per candidate.
_VALID_RECEIVED_AT = '''CASE WHEN typeof(r.received_at)='text'
    AND length(CAST(r.received_at AS BLOB))=24 AND substr(r.received_at,1,4)<>'0000'
    THEN COALESCE(strftime('%Y-%m-%dT%H:%M:%fZ',julianday(r.received_at))=r.received_at,0)
    ELSE 0 END'''
_RECEIPT = _json_object('r', '''server_id executor_id operation_id receipt_revision
intent_hash stage possible_effect retry_safe native_id error_code
source_connection_id source_connection_generation frame_digest'''.split())[:-1] + (
    ", 'received_at_valid',(" + _VALID_RECEIVED_AT + "), 'received_at',CASE WHEN ("
    + _VALID_RECEIVED_AT + ")=1 THEN r.received_at END"
    + ", 'canonical_frame',CASE WHEN length(CAST(r.canonical_frame AS BLOB))<="
    + str(MAX_FRAME_BYTES) + ' THEN r.canonical_frame END)')
_SQL = '''WITH requested AS MATERIALIZED (
    SELECT DISTINCT value AS observed_instance_id FROM json_each(:observed_instance_ids)
), selected AS MATERIALIZED (
    SELECT c.* FROM requested q JOIN observation_correlations c USING(observed_instance_id)
    JOIN observation_instances i USING(observed_instance_id)
    JOIN observation_sources src ON src.source_id=i.source_id
    WHERE c.state='selected' AND c.agent_id=src.agent_id AND c.workspace_id=i.workspace_id
      AND json_extract(c.selection_json,'$.source_id')=i.source_id
      AND json_extract(c.selection_json,'$.source_revision')=src.revision
      AND json_extract(c.selection_json,'$.generation')=i.generation
), session_keys AS MATERIALIZED (
    SELECT DISTINCT server_id,executor_id,session_id FROM selected
), native_sessions AS MATERIALIZED (''' + SESSION_SQL + '''
    JOIN session_keys k ON k.server_id=s.server_id
        AND k.executor_id=s.executor_id AND k.session_id=s.session_id
), native_facts AS MATERIALIZED (
    SELECT ns.*,''' + _NATIVE + ''' AS native_json FROM native_sessions ns
), receipt_candidates AS MATERIALIZED (
    -- Sort only small keys. Do not filter provenance before choosing the latest
    -- received candidate: an incomplete latest fact must not resurrect an older one.
    SELECT ns.server_id,ns.executor_id,ns.session_id,r.rowid AS receipt_rowid,
        row_number() OVER (PARTITION BY ns.server_id,ns.executor_id,ns.session_id
            ORDER BY (''' + _VALID_RECEIVED_AT + '''),substr(r.received_at,1,24) DESC,r.rowid DESC) AS received_rank
    FROM native_facts ns JOIN execution_operations o ON o.server_id=ns.server_id
        AND o.executor_id=ns.executor_id AND o.session_id=ns.session_id
        AND o.subject_agent_id=ns.subject_agent_id AND o.workspace_id=ns.workspace_id
        AND o.binding_id=ns.binding_id AND o.workspace_binding_id=ns.workspace_binding_id
    JOIN execution_receipts r ON r.server_id=o.server_id
        AND r.executor_id=o.executor_id AND r.operation_id=o.operation_id
), receipt_metadata AS MATERIALIZED (
    -- Validate at most one frame per distinct native namespace. Retain only small
    -- metadata, never a materialized collection of full receipt frames.
    SELECT rc.server_id,rc.executor_id,rc.session_id,
        ''' + _FUNCTION + '(' + _RECEIPT + ',' + _OPERATION + ''',ns.native_json) AS receipt_json
    FROM receipt_candidates rc JOIN execution_receipts r ON r.rowid=rc.receipt_rowid
    JOIN execution_operations o ON o.server_id=r.server_id
        AND o.executor_id=r.executor_id AND o.operation_id=r.operation_id
    JOIN native_facts ns ON ns.server_id=rc.server_id
        AND ns.executor_id=rc.executor_id AND ns.session_id=rc.session_id
    WHERE rc.received_rank=1
)
SELECT c.*,ns.native_json,rm.receipt_json FROM selected c
LEFT JOIN native_facts ns ON ns.server_id=c.server_id
    AND ns.executor_id=c.executor_id AND ns.session_id=c.session_id
LEFT JOIN receipt_metadata rm ON rm.server_id=c.server_id
    AND rm.executor_id=c.executor_id AND rm.session_id=c.session_id
ORDER BY c.observed_instance_id'''


def _error(code, reason):
    raise OktoNexusError(code, 'Observation correlation projection unavailable.', {'reason': reason})


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _receipt_metadata(receipt, operation, native):
    """Verify persisted Core provenance, never infer process/activity/authority."""
    unknown = dict(status='unknown', reason='receipt_provenance_unavailable')
    try:
        raw = receipt['canonical_frame']
        if (receipt['received_at_valid'] != 1 or type(raw) is not str or len(raw) > MAX_FRAME_BYTES
                or not receipt['source_connection_id']
                or type(receipt['source_connection_generation']) is not int
                or receipt['source_connection_generation'] < 1):
            return unknown
        raw = raw.encode('utf-8')
        if len(raw) > MAX_FRAME_BYTES or 'sha256:' + hashlib.sha256(raw).hexdigest() != receipt['frame_digest']:
            return unknown
        frame = decode_r4_frame(raw)
        if frame['type'] != 'operation.receipt' or any(frame[key] != receipt[key] for key in (
            'server_id', 'executor_id', 'operation_id', 'receipt_revision', 'intent_hash', 'stage',
            'possible_effect', 'retry_safe')) or any(frame.get(key) != receipt[key] for key in ('native_id', 'error_code')):
            return unknown
        if (frame['connection_id'] != receipt['source_connection_id']
                or frame['connection_generation'] != receipt['source_connection_generation']
                or frame['agent_id'] != operation['subject_agent_id']
                or any(frame[key] != operation[key] for key in (
                    'server_id', 'executor_id', 'operation_id', 'binding_id', 'session_id', 'intent_hash'))):
            return unknown
        scope = json.loads(operation['expected_revisions_json'])
        expected = {key: native[key] for key in (
            'server_id', 'executor_id', 'session_id', 'binding_id', 'workspace_id', 'workspace_binding_id', 'binding_revision')}
        expected.update(agent_id=native['subject_agent_id'], session_owner_generation=native['owner_generation'])
        if type(scope) is not dict or any(type(scope.get(key)) is not type(value) or scope[key] != value
                                        for key, value in expected.items()):
            return unknown
        if (type(operation['action']) is not str or not 1 <= len(operation['action']) <= 160
                or not operation['action'].isprintable()
                or type(receipt['received_at']) is not str or len(receipt['received_at']) > 64
                or datetime.fromisoformat(receipt['received_at'].replace('Z', '+00:00')).tzinfo is None):
            return unknown
        return dict(status='verified', operation_id=frame['operation_id'], action=operation['action'],
            stage=frame['stage'], receipt_revision=frame['receipt_revision'], received_at=receipt['received_at'],
            provenance='core_committed')
    except (CoreError, ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        return unknown


def load(uow, *, observed_instance_ids, check_budget=None):
    """Read one bounded batch in the existing UoW; no public DTO or authorization.

    With check_budget, preserve the caller's installed progress handler exactly.
    Without it the caller must supply a fresh UoW connection without another
    handler; this function installs and removes its own five-second handler.
    """
    deadline = time.monotonic() + QUERY_SECONDS

    def check():
        if check_budget is not None:
            check_budget()
        if time.monotonic() >= deadline:
            _error('OBSERVATION_CORRELATION_QUERY_BUDGET', 'OBSERVATION_CORRELATION_QUERY_BUDGET')

    check()
    if type(observed_instance_ids) not in (list, tuple) or len(observed_instance_ids) > MAX_RECORDS:
        _error(ErrorCode.VALIDATION_ERROR, 'OBSERVATION_CORRELATION_INVALID_BATCH')
    ids = set()
    for value in observed_instance_ids:
        check()
        ids.add(_instance(value))
    if not ids:
        return {}
    callback_error = None

    def project(receipt, operation, native):
        nonlocal callback_error
        try:
            check()
            if len(native.encode('utf-8')) > MAX_NATIVE_BYTES or len(operation.encode('utf-8')) > MAX_NATIVE_BYTES:
                _error(ErrorCode.DB_ERROR, 'OBSERVATION_CORRELATION_FACTS_TOO_LARGE')
            result = _encoded(_receipt_metadata(json.loads(receipt), json.loads(operation), json.loads(native)))
            if len(result.encode('utf-8')) > MAX_RECEIPT_METADATA_BYTES:
                _error(ErrorCode.DB_ERROR, 'OBSERVATION_CORRELATION_FACTS_TOO_LARGE')
            check()
            return result
        except Exception as error:
            callback_error = error
            raise

    conn = uow.connection
    cursor = None
    try:
        if check_budget is None:
            conn.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        conn.create_function(_FUNCTION, 3, project)
        cursor = conn.execute(_SQL, dict(observed_instance_ids=_encoded(sorted(ids))))
        result, retained_bytes = {}, 0
        for row in cursor:
            check()
            retained_bytes += sum(len(value.encode('utf-8')) for value in row if isinstance(value, str))
            if retained_bytes > MAX_RESULT_BYTES:
                _error(ErrorCode.QUOTA_EXCEEDED, 'OBSERVATION_CORRELATION_RESULT_CAPACITY')
            if row['native_json'] is not None and len(row['native_json'].encode('utf-8')) > MAX_NATIVE_BYTES:
                _error(ErrorCode.DB_ERROR, 'OBSERVATION_CORRELATION_FACTS_TOO_LARGE')
            correlation = _decode({key: row[key] for key in _CORRELATION_FIELDS})
            key = correlation['observed_instance_id']
            if key in result:
                _error(ErrorCode.DB_ERROR, 'OBSERVATION_CORRELATION_DUPLICATE')
            result[key] = dict(correlation=correlation,
                native=json.loads(row['native_json']) if row['native_json'] is not None else None,
                last_received_receipt=json.loads(row['receipt_json']) if row['receipt_json'] is not None else None)
        check()
        return result
    except sqlite3.Error as error:
        if callback_error is not None:
            raise callback_error from None
        check()
        raise OktoNexusError(ErrorCode.DB_ERROR, 'Observation correlation projection could not be read.', {}) from error
    finally:
        if cursor is not None:
            cursor.close()
        conn.create_function(_FUNCTION, 3, None)
        if check_budget is None:
            conn.set_progress_handler(None, 0)
