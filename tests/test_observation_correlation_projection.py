"""Real migrated SQLite + production receipt ingress, without a runtime or OS."""
import hashlib
import json
import sqlite3

from nexus_connector_core import R4_PREVIEW_REVISION
from nexus_connector_core.protocol import canonical_json
import pytest

from okto_nexus.adapters.outbound.sqlite import observation_correlation_projection as projection
from okto_nexus.adapters.outbound.sqlite.execution_receipts import append_execution_receipt
from okto_nexus.adapters.outbound.sqlite.execution_tickets import VerifiedExecutionTicket
from okto_nexus.errors import OktoNexusError
from test_observation_correlations_storage import env as storage_env, put, NOW  # noqa: F401


def insert(conn, table, **values):
    conn.execute('INSERT INTO ' + table + '(' + ','.join(values) + ') VALUES(' +
                 ','.join('?' for _ in values) + ')', tuple(values.values()))


@pytest.fixture
def observed(request):
    env = request.getfixturevalue('storage_env')
    conn = env.connection
    insert(conn, 'execution_installation', singleton=1, server_id='server-a',
        embedded_executor_id='executor-a', schema_revision=1, created_at=NOW)
    conn.execute("UPDATE execution_executors SET control_state='CONTROL_READY',owner_instance_id='control'")
    conn.execute("UPDATE execution_sessions SET lifecycle_state='READY'")
    conn.execute("UPDATE agent_endpoints SET enabled=1,activation_state='approved'")
    insert(conn, 'execution_realizations', server_id='server-a', executor_id='executor-a',
        realization_ref='realization', local_realization_ref='fixture-local', subject_agent_id='alice',
        workspace_binding_id='workspace-binding-one', candidate_ref='candidate', inventory_revision='inventory',
        configuration_digest='sha256:'+'a'*64, local_root_proof_digest='sha256:'+'b'*64, revision=1, status='READY')
    env.scope = dict(server_id='server-a', executor_id='executor-a', session_id='session-same',
        agent_id='alice', workspace_id='ws', binding_id='binding-one',
        workspace_binding_id='workspace-binding-one', session_owner_generation=3, binding_revision=1)
    operation(env, 'opening-one', action='runtime.open')
    insert(conn, 'execution_leases', server_id='server-a', executor_id='executor-a', session_id='session-same',
        lease_serial=1, lease_id='lease', grant_id='grant', allowed_actions_json='["turn.submit"]',
        authorization_revision=1, configuration_revision=1, owner_generation=3, connection_generation=1,
        credential_epoch=1, valid_until_server='2099-01-01T00:00:00Z', request_id='request', status='ACTIVE',
        connection_id='control', scope_json=json.dumps(env.scope), applied_at=NOW)
    put(env)
    conn.commit()
    return env


def operation(env, operation_id='turn-one', action='turn.submit'):
    insert(env.connection, 'execution_operations',
        **{key: env.scope[key] for key in ('server_id', 'executor_id', 'binding_id', 'workspace_id', 'workspace_binding_id', 'session_id')},
        operation_id=operation_id, subject_agent_id='alice', actor_agent_id='alice', action=action,
        intent_hash='sha256:'+'c'*64, semantic_payload='{}', expected_revisions_json=json.dumps(env.scope),
        admission_state='ACCEPTED', created_at=NOW)
    insert(env.connection, 'execution_dispatch_outbox', server_id='server-a', executor_id='executor-a',
        operation_id=operation_id, dispatch_state='DISPATCHED', lease_id='lease', lease_serial=1)


def receipt(env, operation_id='turn-one', revision=1, stage='RECEIVED_DURABLE', received_at=None):
    if not env.connection.execute('SELECT 1 FROM execution_operations WHERE operation_id=?', (operation_id,)).fetchone():
        operation(env, operation_id)
    frame = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, type='operation.receipt',
        server_id='server-a', executor_id='executor-a', binding_id='binding-one', agent_id='alice',
        session_id='session-same', connection_id='control', connection_generation=1,
        operation_id=operation_id, intent_hash='sha256:'+'c'*64, receipt_revision=revision, stage=stage,
        possible_effect=stage != 'RECEIVED_DURABLE', retry_safe=stage == 'RECEIVED_DURABLE')
    principal = VerifiedExecutionTicket('fixture-ticket', 'server-a', 'executor-a', 'binding-one', 'alice',
        frozenset({'receipt:publish'}), 1, 1)
    append_execution_receipt(env.factory, principal=principal, uow=env, frame=frame)
    if received_at:
        env.connection.execute('UPDATE execution_receipts SET received_at=? WHERE operation_id=? AND receipt_revision=?',
            (received_at, operation_id, revision))
    env.connection.commit()
    return frame


def read(env, ids=None, **kwargs):
    return projection.load(env, observed_instance_ids=ids or ['instance-one'], **kwargs)


def snapshot(env):
    tables = [r[0] for r in env.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    return {name: sorted((tuple(row) for row in env.connection.execute('SELECT * FROM "'+name+'"')), key=repr) for name in tables}


def test_real_receipt_producer_provenance_and_passive_minimal_metadata(observed, monkeypatch):
    env = observed
    receipt(env)
    receipt(env, revision=2, stage='RUNNING')
    receipt(env, revision=3, stage='SUCCEEDED')
    before = snapshot(env)
    from okto_nexus.bootstrap import runtime_host
    monkeypatch.setattr(runtime_host, 'open_journal', lambda *a, **k: pytest.fail('native journal'))
    monkeypatch.setattr(runtime_host, 'create_runtime', lambda *a, **k: pytest.fail('runtime'))
    value = read(env)['instance-one']
    assert value['correlation']['proof'] is not None  # Private internal result, never public DTO.
    assert value['native']['lifecycle_state'] == 'READY'
    meta = value['last_received_receipt']
    assert meta == dict(status='verified', operation_id='turn-one', action='turn.submit', stage='SUCCEEDED',
        receipt_revision=3, received_at=meta['received_at'], provenance='core_committed')
    assert not {'native_id', 'canonical_frame', 'proof', 'connection_id', 'idle'} & meta.keys()
    assert snapshot(env) == before


def test_absent_receipt_is_distinct_from_unknown(observed):
    assert read(observed)['instance-one']['last_received_receipt'] is None
    receipt(observed)
    observed.connection.execute('UPDATE execution_receipts SET canonical_frame=NULL,frame_digest=NULL')
    assert read(observed)['instance-one']['last_received_receipt'] == dict(status='unknown', reason='receipt_provenance_unavailable')


@pytest.mark.parametrize('column,value', [
    ('canonical_frame', '{}'), ('canonical_frame', 'SYNTHETIC_PRIVATE_FRAME'),
    pytest.param('canonical_frame', 'x'*(1024*1024+1), id='oversized-frame'),
    ('frame_digest', 'sha256:'+'a'*64), ('source_connection_id', None), ('source_connection_generation', None),
    ('source_connection_id', 'other'), ('source_connection_generation', 2), ('intent_hash', 'sha256:'+'d'*64),
    ('stage', 'FAILED'), ('native_id', 'private-native'), ('error_code', 'private-error'), ('received_at', 'no-clock'),
])
def test_incomplete_or_corrupt_latest_never_falls_back(observed, column, value):
    env = observed
    receipt(env, operation_id='older', received_at='2026-01-01T00:00:00.001Z')
    receipt(env, operation_id='latest', received_at='2026-01-01T00:00:00.002Z')
    env.connection.execute('UPDATE execution_receipts SET '+column+'=? WHERE operation_id=\'latest\'', (value,))
    assert read(env)['instance-one']['last_received_receipt'] == dict(status='unknown', reason='receipt_provenance_unavailable')


@pytest.mark.parametrize('received_at', [
    '', '2025-02-30T00:00:00.001Z', '2025-02-29T00:00:00.001Z',
    '2025-00-01T00:00:00.001Z', '2025-01-00T00:00:00.001Z', '2025-01-01T24:00:00.001Z',
    '0000-01-01T00:00:00.001Z', '2025-01-01T00:00:00.001+00:00',
    '2024-12-31T21:00:00.001-03:00', '2025-01-01T00:00:00.001000Z',
    '2025-01-01 00:00:00.001Z', '2025-01-01T00:00:00.001', 'not-a-clock',
])
def test_noncanonical_receipt_time_is_unknown_even_when_it_sorts_before_an_older_valid_receipt(
        observed, monkeypatch, received_at):
    """Only the producer's fixed UTC format is trusted, not equivalent legacy offsets."""
    receipt(observed, operation_id='older', received_at='2026-01-01T00:00:00.001Z')
    receipt(observed, operation_id='latest', received_at='2026-01-01T00:00:00.002Z')
    observed.connection.execute("UPDATE execution_receipts SET received_at=? WHERE operation_id='latest'", (received_at,))
    monkeypatch.setattr(projection, 'decode_r4_frame', lambda _: pytest.fail('invalid time must not decode a frame'))
    assert read(observed)['instance-one']['last_received_receipt'] == dict(
        status='unknown', reason='receipt_provenance_unavailable')


def test_valid_leap_day_receipt_still_uses_timestamp_then_rowid_order(observed):
    receipt(observed, operation_id='older', received_at='2024-02-29T23:59:59.998Z')
    receipt(observed, operation_id='latest', received_at='2024-02-29T23:59:59.999Z')
    value = read(observed)['instance-one']['last_received_receipt']
    assert value['status'] == 'verified' and value['operation_id'] == 'latest'
    assert value['received_at'] == '2024-02-29T23:59:59.999Z'


@pytest.mark.parametrize('field,value', [('server_id','elsewhere'), ('executor_id','elsewhere'),
    ('session_id','elsewhere'), ('binding_id','elsewhere'), ('agent_id','foreign'), ('operation_id','elsewhere'),
    ('intent_hash','sha256:'+'e'*64)])
def test_digest_consistent_wrong_namespace_frame_is_not_trusted(observed, field, value):
    frame = receipt(observed)
    frame[field] = value
    raw = canonical_json(frame)
    observed.connection.execute('UPDATE execution_receipts SET canonical_frame=?,frame_digest=?',
        (raw.decode(), 'sha256:'+hashlib.sha256(raw).hexdigest()))
    assert read(observed)['instance-one']['last_received_receipt']['status'] == 'unknown'


@pytest.mark.parametrize('field,value', [('server_id','elsewhere'), ('executor_id','elsewhere'),
    ('session_id','elsewhere'), ('binding_id','elsewhere'), ('agent_id','foreign'), ('workspace_id','foreign'),
    ('workspace_binding_id','elsewhere'), ('session_owner_generation',4), ('binding_revision',2),
    ('session_owner_generation',True)])
def test_operation_admitted_scope_must_match_current_native_fences(observed, field, value):
    receipt(observed)
    changed = dict(observed.scope, **{field:value})
    observed.connection.execute("UPDATE execution_operations SET expected_revisions_json=? WHERE operation_id='turn-one'", (json.dumps(changed),))
    assert read(observed)['instance-one']['last_received_receipt']['status'] == 'unknown'


@pytest.mark.parametrize('scope', ['{}', '[]', '{'])
def test_legacy_or_invalid_operation_scope_is_unknown(observed, scope):
    receipt(observed)
    observed.connection.execute("UPDATE execution_operations SET expected_revisions_json=? WHERE operation_id='turn-one'", (scope,))
    assert read(observed)['instance-one']['last_received_receipt']['status'] == 'unknown'


def test_last_received_convention_is_not_operation_execution_order(observed):
    receipt(observed, operation_id='z-first', received_at='2026-01-01T00:00:00.001Z')
    receipt(observed, operation_id='a-second', received_at='2026-01-01T00:00:00.001Z')
    assert read(observed)['instance-one']['last_received_receipt']['operation_id'] == 'a-second'
    observed.connection.execute("UPDATE execution_receipts SET received_at='2026-01-02T00:00:00.001Z' WHERE operation_id='z-first'")
    assert read(observed)['instance-one']['last_received_receipt']['operation_id'] == 'z-first'


@pytest.mark.parametrize('sql', [
    'UPDATE observation_sources SET revision=revision+1', 'UPDATE observation_instances SET generation=generation+1',
    "UPDATE observation_correlations SET agent_id='foreign'", "UPDATE observation_correlations SET workspace_id='foreign'",
    'DELETE FROM observation_instances',
])
def test_current_observation_scope_filters_old_private_correlation(observed, sql):
    observed.connection.execute(sql)
    assert read(observed) == {}


@pytest.mark.parametrize('state', ['cleared', 'revoked'])
def test_tombstones_never_enrich(observed, state):
    observed.repo.tombstone(observed, observed_instance_id='instance-one', expected_revision=1,
        state=state, now=NOW, max_records=4096, agent_id='alice', workspace_id='ws')
    assert read(observed) == {}


@pytest.mark.parametrize('key', ['server_id', 'executor_id', 'session_id'])
def test_namespace_requires_exact_match_without_label_fallback(observed, key):
    put(observed, 1, **{key:'another'})
    assert read(observed)['instance-one']['native'] is None
    assert read(observed)['instance-one']['last_received_receipt'] is None


def test_owner_change_retains_native_fact_but_invalidates_old_receipt_scope(observed):
    receipt(observed)
    observed.connection.execute('UPDATE execution_sessions SET owner_generation=4')
    value = read(observed)['instance-one']
    assert value['native']['owner_generation'] == 4
    assert value['last_received_receipt']['status'] == 'unknown'


def test_historical_connection_generation_is_not_current_ownership(observed):
    receipt(observed)
    observed.connection.execute("UPDATE execution_executors SET generation=2,owner_instance_id='new-owner'")
    assert read(observed)['instance-one']['last_received_receipt']['status'] == 'verified'


def test_correlation_digest_corruption_is_honest_error(observed):
    observed.connection.execute('UPDATE observation_correlations SET correlation_digest=?', ('sha256:'+'f'*64,))
    with pytest.raises(OktoNexusError) as error:
        read(observed)
    assert error.value.code == 'DB_ERROR'
    assert error.value.details == {'reason':'OBSERVATION_CORRELATION_CORRUPT'}


def test_batch_constant_queries_and_one_decode_per_distinct_namespace(observed, monkeypatch):
    env = observed
    receipt(env)
    ids = ['instance-one']
    for index in range(20):
        name = 'instance-extra-'+str(index)
        insert(env.connection, 'observation_instances', observed_instance_id=name, source_id='source-one',
            workspace_id='ws', external_instance_ref=name, generation=index+2, created_at=NOW, updated_at=NOW)
        put(env, observed_instance_id=name, generation=index+2)
        ids.append(name)
    decoded, sql = [], []
    original = projection.decode_r4_frame
    def decode(raw):
        decoded.append(len(raw))
        return original(raw)
    monkeypatch.setattr(projection, 'decode_r4_frame', decode)
    env.connection.set_trace_callback(sql.append)
    result = read(env, ids+ids)
    env.connection.set_trace_callback(None)
    assert set(result) == set(ids)
    assert len(decoded) == 1
    assert len(sql) == 1 and sql[0].startswith('WITH')
    assert len({_encoded_metadata(value) for value in result.values()}) == 1


def _encoded_metadata(value):
    return json.dumps(value['last_received_receipt'], sort_keys=True)


@pytest.mark.parametrize('ids', [None, 'instance-one', set(), ['bad/path'], ['x']*65537])
def test_invalid_or_excessive_input_is_refused_before_sql(observed, ids):
    sql = []
    observed.connection.set_trace_callback(sql.append)
    try:
        with pytest.raises(OktoNexusError, match='VALIDATION_ERROR'):
            projection.load(observed, observed_instance_ids=ids)
    finally:
        observed.connection.set_trace_callback(None)
    assert sql == []


def test_empty_batch_does_not_query(observed):
    sql = []
    observed.connection.set_trace_callback(sql.append)
    assert projection.load(observed, observed_instance_ids=[]) == {}
    observed.connection.set_trace_callback(None)
    assert sql == []


def test_result_capacity_refuses_without_partial_success_and_cleans_up(observed, monkeypatch):
    monkeypatch.setattr(projection, 'MAX_RESULT_BYTES', 1)
    with pytest.raises(OktoNexusError) as error:
        read(observed)
    assert error.value.code == 'QUOTA_EXCEEDED'
    assert error.value.details == {'reason':'OBSERVATION_CORRELATION_RESULT_CAPACITY'}
    assert observed.connection.execute('SELECT 1').fetchone()[0] == 1
    with pytest.raises(sqlite3.OperationalError):
        observed.connection.execute('SELECT nexus_obs_receipt_metadata_v1(NULL,NULL,NULL)').fetchone()


def test_standalone_deadline_in_last_callback_is_not_swallowed_and_is_removed(observed, monkeypatch):
    receipt(observed)
    clock = [0.0]
    monkeypatch.setattr(projection.time, 'monotonic', lambda: clock[0])
    original = projection._receipt_metadata
    def late(*args):
        value = original(*args)
        clock[0] = 6.0
        return value
    monkeypatch.setattr(projection, '_receipt_metadata', late)
    with pytest.raises(OktoNexusError, match='OBSERVATION_CORRELATION_QUERY_BUDGET'):
        read(observed)
    assert observed.connection.execute('WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<2000) SELECT sum(x) FROM n').fetchone()[0] == 2001000


def test_outer_progress_handler_survives_success_and_errors(observed):
    interrupts = [False]
    observed.connection.set_progress_handler(lambda: int(interrupts[0]), 1)
    try:
        assert read(observed, check_budget=lambda: None)
        def denied():
            raise OktoNexusError('ATTENTION_QUERY_BUDGET', 'outer deadline', {})
        with pytest.raises(OktoNexusError, match='ATTENTION_QUERY_BUDGET'):
            read(observed, check_budget=denied)
        interrupts[0] = True
        with pytest.raises(sqlite3.OperationalError, match='interrupted'):
            observed.connection.execute('SELECT 1').fetchone()
    finally:
        observed.connection.set_progress_handler(None, 0)


def test_same_uow_sees_current_changes_without_hidden_cache(observed):
    receipt(observed)
    assert read(observed)['instance-one']['last_received_receipt']['status'] == 'verified'
    observed.connection.execute('UPDATE observation_sources SET revision=revision+1')
    assert read(observed) == {}
    observed.connection.rollback()
    assert read(observed)['instance-one']['last_received_receipt']['status'] == 'verified'
