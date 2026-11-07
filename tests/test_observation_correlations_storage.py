"""Real migrated SQLite qualification; no host auth/OS/provider claim."""
from concurrent.futures import ThreadPoolExecutor
import json
import shutil
import sqlite3
from threading import Barrier
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner, _default_migrations_dir
from okto_nexus.adapters.outbound.sqlite.observation_correlations_repo import SqliteObservationCorrelationRepo
from okto_nexus.application.database_reset import clear_operational_history
from okto_nexus.bootstrap.dependencies import build_repos
from okto_nexus.domain.observation_correlation import MAX_INT64, correlation_digest
from okto_nexus.errors import OktoNexusError

NOW = '2026-01-01T00:00:00.000000Z'



def selection(expected=0, **changes):
    return dict(dict(source_id='source-one', observed_instance_id='instance-one',
        server_id='server-a', executor_id='executor-a', session_id='session-same',
        open_operation_id='opening-one', stream_epoch='stream-one', binding_id='binding-one',
        workspace_binding_id='workspace-binding-one', source_revision=1, generation=1,
        session_owner_generation=3, expected_correlation_revision=expected), **changes)


def proof():
    return dict(kind='local_windows_process_v1',
        external_binding_provenance='operator_attested_external_binding',
        native_birth_provenance='machine_checked_native_birth', host_id='a' * 64,
        pid=123, creation_filetime=133000000000000000,
        image_path_sha256='sha256:' + 'b' * 64, binding_hash='sha256:' + 'c' * 64)


def setup(connection):
    connection.execute("INSERT INTO agents(agent_id,created_at,is_active,api_key_hash,permissions) VALUES('alice',?,1,'synthetic','{}')", (NOW,))
    connection.execute("INSERT INTO workspaces(workspace_id,created_at) VALUES('ws',?)", (NOW,))
    connection.execute("INSERT INTO runtime_profiles(profile_id,adapter_id,config,created_at,updated_at) VALUES('profile-one','fixture','{}',?,?)", (NOW, NOW))
    connection.execute("INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,adapter_id,protocol,profile_id,created_at,updated_at) VALUES('endpoint-one','alice','ws','fixture','nxl-r4','profile-one',?,?)", (NOW, NOW))
    connection.execute("INSERT INTO observation_sources VALUES('source-one','alice','custom','synthetic',?,1,1,NULL,?,?)", ('d' * 64, NOW, NOW))
    connection.execute("INSERT INTO observation_instances VALUES('instance-one','source-one','ws','synthetic',1,?,?)", (NOW, NOW))
    connection.execute("INSERT INTO execution_executors(server_id,executor_id,kind,control_state,generation) VALUES('server-a','executor-a','embedded','READY',1)")
    connection.execute("INSERT INTO execution_workspace_bindings VALUES('server-a','workspace-binding-one','executor-a','ws','synthetic',1,NULL,'READY')")
    connection.execute("INSERT INTO execution_bindings(server_id,binding_id,executor_id,endpoint_id,workspace_binding_id,candidate_ref,inventory_revision,realization_ref,realization_revision,binding_revision) VALUES('server-a','binding-one','executor-a','endpoint-one','workspace-binding-one','candidate','inventory','realization',1,1)")
    connection.execute("INSERT INTO execution_sessions(server_id,executor_id,session_id,binding_id,workspace_id,workspace_binding_id,open_operation_id,owner_generation,lifecycle_state,stream_epoch,lease_state) VALUES('server-a','executor-a','session-same','binding-one','ws','workspace-binding-one','opening-one',3,'RUNNING','stream-one','ACTIVE')")
    connection.commit()


def other_rows(connection):
    names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name<>'observation_correlations'")]
    return {name: sorted((tuple(row) for row in connection.execute('SELECT * FROM "' + name + '"')), key=repr) for name in names}


@pytest.fixture
def env(migrated_factory):
    connection = migrated_factory.get_connection()
    setup(connection)
    connection.isolation_level = ''
    yield SimpleNamespace(connection=connection, repo=SqliteObservationCorrelationRepo(), factory=migrated_factory)
    connection.close()


def put(env, expected=0, max_records=4096, agent_id='alice', workspace_id='ws', **changes):
    return env.repo.replace_selection(env, agent_id=agent_id, workspace_id=workspace_id, max_records=max_records, selection=selection(expected, **changes), proof=proof(), verified_at=NOW, now=NOW)


def test_first_write_and_exact_digest_provenance_are_detached(env):
    selected, supplied = selection(), proof()
    row = env.repo.replace_selection(env, agent_id='alice', workspace_id='ws', max_records=4096, selection=selected, proof=supplied, verified_at=NOW, now=NOW)
    selected['session_id'] = 'mutated'
    supplied['pid'] = 999
    assert row['revision'] == 1 and row['state'] == 'selected'
    assert row['selection'] == selection() and row['proof'] == proof()
    assert row['digest'] == correlation_digest(selection(), proof())
    assert row['provenance']['external_binding_provenance'] == 'operator_attested_external_binding'
    assert env.repo.get(env, observed_instance_id='instance-one') == row


def test_correlation_mutations_do_not_emit_events_or_change_other_tables(env):
    before = other_rows(env.connection)
    put(env)
    env.repo.tombstone(env, agent_id='alice', workspace_id='ws', max_records=4096, observed_instance_id='instance-one', expected_revision=1, state='revoked', now=NOW)
    assert other_rows(env.connection) == before


def test_stale_create_update_and_missing_nonzero_revision_are_conflicts(env):
    put(env)
    for expected in (0, 2):
        with pytest.raises(OktoNexusError) as error:
            put(env, expected)
        assert error.value.code == 'CONFLICT'
    with pytest.raises(OktoNexusError) as error:
        put(env, 9, observed_instance_id='missing')
    assert error.value.code == 'CONFLICT'
    assert env.repo.get(env, observed_instance_id='missing') is None


def test_clear_revoke_reselect_never_resets_revision_or_reuses_old_zero(env):
    put(env)
    for revision, state in ((1, 'cleared'), (2, 'revoked')):
        row = env.repo.tombstone(env, agent_id='alice', workspace_id='ws', max_records=4096, observed_instance_id='instance-one', expected_revision=revision, state=state, now=NOW)
        assert row['revision'] == revision + 1 and row['state'] == state
        assert all(row[key] is None for key in ('selection', 'proof', 'digest', 'verified_at', 'provenance'))
    assert put(env, 3)['revision'] == 4
    with pytest.raises(OktoNexusError, match='CONFLICT'):
        put(env)
    assert env.connection.execute('SELECT count(*) FROM observation_correlations').fetchone()[0] == 1


def test_clear_absent_creates_revision_one_tombstone(env):
    row = env.repo.tombstone(env, agent_id='alice', workspace_id='ws', max_records=4096, observed_instance_id='absent', expected_revision=0, state='cleared', now=NOW)
    assert row['revision'] == 1 and row['selection'] is None
    with pytest.raises(OktoNexusError, match='CONFLICT'):
        put(env, observed_instance_id='absent')
    assert put(env, 1, observed_instance_id='absent')['revision'] == 2


def test_outer_rollback_removes_insert_and_restores_update_without_hidden_commit(env):
    env.connection.execute('BEGIN')
    put(env)
    env.connection.rollback()
    assert env.repo.get(env, observed_instance_id='instance-one') is None
    put(env)
    env.connection.commit()
    env.connection.execute('BEGIN')
    env.repo.tombstone(env, agent_id='alice', workspace_id='ws', max_records=4096, observed_instance_id='instance-one', expected_revision=1, state='revoked', now=NOW)
    env.connection.rollback()
    assert env.repo.get(env, observed_instance_id='instance-one')['revision'] == 1


@pytest.mark.parametrize('changed', [dict(server_id='server-b'), dict(executor_id='executor-b'), dict(session_id='another')])
def test_full_namespace_is_required_even_when_session_label_repeats(env, changed):
    put(env)
    namespace = dict(server_id='server-a', executor_id='executor-a', session_id='session-same')
    assert env.repo.get_for_session(env, observed_instance_id='instance-one', **namespace)['revision'] == 1
    assert env.repo.get_for_session(env, observed_instance_id='instance-one', **dict(namespace, **changed)) is None


def test_canonical_and_observation_deletion_do_not_delete_tombstone_highwater(env):
    put(env)
    env.connection.execute("DELETE FROM execution_sessions WHERE server_id='server-a' AND executor_id='executor-a' AND session_id='session-same'")
    env.connection.execute("DELETE FROM observation_instances WHERE observed_instance_id='instance-one'")
    assert env.repo.get(env, observed_instance_id='instance-one')['revision'] == 1
    assert list(env.connection.execute('PRAGMA foreign_key_list(observation_correlations)')) == []
    assert env.repo.tombstone(env, agent_id='alice', workspace_id='ws', max_records=4096, observed_instance_id='instance-one', expected_revision=1, state='revoked', now=NOW)['revision'] == 2
    assert list(env.connection.execute('PRAGMA foreign_key_check')) == []


@pytest.mark.parametrize('part, field, value', [
    ('selection', 'expected_correlation_revision', True), ('selection', 'generation', 0),
    ('selection', 'session_id', 'x' * 161), ('selection', 'observed_instance_id', '../bad'),
    ('proof', 'pid', True), ('proof', 'creation_filetime', MAX_INT64 + 1),
    ('proof', 'native_birth_provenance', 'operator_claim'), ('proof', 'image_path', 'SYNTHETIC_PRIVATE_PATH'),
])
def test_closed_bounded_inputs_refuse_without_persisting_or_echoing(env, part, field, value):
    selected, supplied = selection(), proof()
    (selected if part == 'selection' else supplied)[field] = value
    with pytest.raises(OktoNexusError) as error:
        env.repo.replace_selection(env, agent_id='alice', workspace_id='ws', max_records=4096, selection=selected, proof=supplied, verified_at=NOW, now=NOW)
    assert error.value.code == 'VALIDATION_ERROR' and 'SYNTHETIC_PRIVATE_PATH' not in str(error.value)
    assert env.connection.execute('SELECT count(*) FROM observation_correlations').fetchone()[0] == 0


@pytest.mark.parametrize('column, payload', [('selection_json', dict(selection(), padding='x' * 8192)), ('proof_json', dict(proof(), padding='x' * 2048))])
def test_database_byte_bounds_reject_oversized_documents(env, column, payload):
    put(env)
    with pytest.raises(sqlite3.IntegrityError):
        env.connection.execute('UPDATE observation_correlations SET ' + column + '=?', (json.dumps(payload),))


def test_corrupt_digest_is_a_read_error_not_a_missing_or_trusted_selection(env):
    put(env)
    env.connection.execute('UPDATE observation_correlations SET correlation_digest=?', ('sha256:' + 'e' * 64,))
    with pytest.raises(OktoNexusError) as error:
        env.repo.get(env, observed_instance_id='instance-one')
    assert error.value.code == 'DB_ERROR'


@pytest.mark.parametrize('verified, now', [(NOW, '2025-01-01T00:00:00Z'), ('invalid', NOW), (NOW[:-1], NOW)])
def test_invalid_or_future_verification_time_is_refused(env, verified, now):
    with pytest.raises(OktoNexusError) as error:
        env.repo.replace_selection(env, agent_id='alice', workspace_id='ws', max_records=4096, selection=selection(), proof=proof(), verified_at=verified, now=now)
    assert error.value.code == 'VALIDATION_ERROR'


def test_max_revision_refuses_increment_without_integer_overflow(env):
    with pytest.raises(OktoNexusError) as error:
        put(env, MAX_INT64)
    assert error.value.code == 'QUOTA_EXCEEDED'
    assert env.connection.execute('SELECT count(*) FROM observation_correlations').fetchone()[0] == 0


def test_two_connections_competing_for_zero_revision_have_one_winner(migrated_factory):
    initial = migrated_factory.get_connection()
    setup(initial)
    initial.close()
    barrier = Barrier(2)
    def write():
        connection = migrated_factory.get_connection()
        connection.row_factory = sqlite3.Row
        local = SimpleNamespace(connection=connection, repo=SqliteObservationCorrelationRepo())
        barrier.wait()
        try:
            connection.execute('BEGIN IMMEDIATE')
            row = put(local)
            connection.commit()
            return row['revision']
        except OktoNexusError as error:
            connection.rollback()
            return error.code
        finally:
            connection.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(lambda _: write(), range(2)))
    assert sorted(values, key=str) == [1, 'CONFLICT']


@pytest.mark.parametrize('state', ['selected', 'cleared', 'revoked'])
def test_all_states_consume_capacity_but_existing_cas_still_works(env, state):
    row = put(env, max_records=1)
    if state != 'selected':
        row = env.repo.tombstone(env, agent_id='alice', workspace_id='ws', observed_instance_id='instance-one', expected_revision=1,
            state=state, now=NOW, max_records=1)
    before = env.connection.total_changes
    capacity = env.repo.capacity(env, max_records=1)
    assert env.connection.total_changes == before
    assert capacity == dict(limit=1, total=1, selected=int(state == 'selected'),
        tombstones=int(state != 'selected'), available=0, full=True)
    with pytest.raises(OktoNexusError) as error:
        put(env, observed_instance_id='never-recorded', max_records=1)
    assert error.value.code == 'QUOTA_EXCEEDED'
    assert error.value.details['reason'] == 'OBSERVATION_CORRELATION_CAPACITY'
    assert env.repo.get(env, observed_instance_id='never-recorded') is None
    with pytest.raises(OktoNexusError, match='CONFLICT'):
        put(env, max_records=1)
    assert put(env, row['revision'], max_records=1)['revision'] == row['revision'] + 1
    assert env.repo.capacity(env, max_records=1)['total'] == 1


def test_full_capacity_also_refuses_new_tombstone_without_dropping_existing_one(env):
    env.repo.tombstone(env, agent_id='alice', workspace_id='ws', observed_instance_id='old', expected_revision=0,
        state='revoked', now=NOW, max_records=1)
    with pytest.raises(OktoNexusError) as error:
        env.repo.tombstone(env, agent_id='alice', workspace_id='ws', observed_instance_id='new', expected_revision=0,
            state='cleared', now=NOW, max_records=1)
    assert error.value.code == 'QUOTA_EXCEEDED'
    assert env.repo.get(env, observed_instance_id='old')['revision'] == 1
    assert env.repo.get(env, observed_instance_id='new') is None


def test_lowered_limit_freezes_new_admission_without_truncation_or_blocking_existing_cas(env):
    for index in range(3):
        put(env, observed_instance_id='instance-' + str(index), max_records=3)
    assert env.repo.capacity(env, max_records=1) == dict(limit=1, total=3, selected=3,
        tombstones=0, available=0, full=True)
    assert put(env, 1, observed_instance_id='instance-0', max_records=1)['revision'] == 2
    with pytest.raises(OktoNexusError, match='QUOTA_EXCEEDED'):
        put(env, observed_instance_id='instance-4', max_records=1)
    assert env.repo.capacity(env, max_records=1)['total'] == 3


def test_rolled_back_admission_does_not_consume_capacity_but_committed_tombstone_does(env):
    put(env, max_records=1)
    env.connection.rollback()
    assert env.repo.capacity(env, max_records=1)['total'] == 0
    env.repo.tombstone(env, agent_id='alice', workspace_id='ws', observed_instance_id='permanent', expected_revision=0,
        state='cleared', now=NOW, max_records=1)
    env.connection.commit()
    with pytest.raises(OktoNexusError, match='QUOTA_EXCEEDED'):
        put(env, max_records=1)
    assert env.repo.get(env, observed_instance_id='permanent')['revision'] == 1


@pytest.mark.parametrize('limit', [0, -1, True, 1.5, 65537, None])
def test_capacity_has_no_unlimited_or_coerced_mode(env, limit):
    with pytest.raises(OktoNexusError) as error:
        put(env, max_records=limit)
    assert error.value.code == 'VALIDATION_ERROR'
    assert env.connection.execute('SELECT count(*) FROM observation_correlations').fetchone()[0] == 0


def test_competing_distinct_instances_cannot_overbook_global_capacity(migrated_factory):
    initial = migrated_factory.get_connection()
    setup(initial)
    initial.close()
    barrier = Barrier(2)
    def write(index):
        connection = migrated_factory.get_connection()
        connection.row_factory = sqlite3.Row
        local = SimpleNamespace(connection=connection, repo=SqliteObservationCorrelationRepo())
        barrier.wait()
        try:
            connection.execute('BEGIN IMMEDIATE')
            put(local, observed_instance_id='competitor-' + str(index), max_records=1)
            connection.commit()
            return 'created'
        except OktoNexusError as error:
            connection.rollback()
            return error.code
        finally:
            connection.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(write, range(2)))
    assert sorted(values) == ['QUOTA_EXCEEDED', 'created']
    check = migrated_factory.get_connection()
    assert check.execute('SELECT count(*) FROM observation_correlations').fetchone()[0] == 1
    check.close()


def test_actual_sqlite_full_is_not_acknowledged_as_a_successful_correlation(env):
    pages = env.connection.execute('PRAGMA page_count').fetchone()[0]
    env.connection.execute('PRAGMA max_page_count=' + str(pages))
    committed = 0
    for index in range(256):
        identity = 'disk-pressure-' + str(index)
        try:
            put(env, observed_instance_id=identity, max_records=65536)
            env.connection.commit()
            committed += 1
        except sqlite3.OperationalError as error:
            assert error.sqlite_errorcode == sqlite3.SQLITE_FULL
            env.connection.rollback()
            assert env.repo.get(env, observed_instance_id=identity) is None
            break
    else:
        pytest.fail('Synthetic SQLite page budget did not reach SQLITE_FULL.')
    assert env.repo.capacity(env, max_records=65536)['total'] == committed


@pytest.mark.parametrize('state', ['selected', 'cleared', 'revoked'])
def test_lost_response_recovers_by_exact_read_without_repeating_mutation(env, state):
    selected = put(env)
    expected = 0
    if state != 'selected':
        selected = env.repo.tombstone(env, agent_id='alice', workspace_id='ws', observed_instance_id='instance-one', expected_revision=1,
            state=state, now=NOW, max_records=4096)
        expected = 1
    env.connection.commit()  # Response lost after commit; no replay marker is invented.
    before = env.connection.total_changes
    with pytest.raises(OktoNexusError, match='CONFLICT'):
        if state == 'selected':
            put(env, expected)
        else:
            env.repo.tombstone(env, agent_id='alice', workspace_id='ws', observed_instance_id='instance-one', expected_revision=expected,
                state=state, now='2026-01-01T00:00:01.000000Z', max_records=4096)
    recovered = env.repo.get(env, observed_instance_id='instance-one')
    assert recovered == selected and recovered['revision'] == expected + 1
    assert env.connection.total_changes == before
    if state == 'selected':
        assert recovered['digest'] == correlation_digest(selection(expected), proof())
    # A newer mutation is not retrospectively certified as the lost attempt.
    put(env, recovered['revision'])
    assert env.repo.get(env, observed_instance_id='instance-one')['revision'] != expected + 1


def test_empty_migration_and_dependency_wiring_are_additive(conn_factory, tmp_config):
    applied = MigrationRunner(conn_factory).apply()
    assert 166 in applied
    with conn_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM observation_correlations').fetchone()[0] == 0
        assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []
    repos, _ = build_repos(None, tmp_config)
    assert isinstance(repos.observation_correlations, SqliteObservationCorrelationRepo)
    assert MigrationRunner(conn_factory).apply() == []


def test_upgrade_165_preserves_existing_rows_and_has_no_seeded_correlation(tmp_config, tmp_path):
    old = tmp_path / 'schema165'
    old.mkdir()
    for path in _default_migrations_dir().glob('*.sql'):
        if int(path.name.split('_')[0]) <= 165:
            shutil.copyfile(path, old / path.name)
    factory = ConnectionFactory(tmp_config)
    try:
        assert MigrationRunner(factory, old).apply()[-1] == 165
        connection = factory.get_connection()
        try:
            setup(connection)
            before = other_rows(connection)
            before.pop('schema_migrations')
        finally:
            connection.close()
        expected = sorted(int(path.name.split('_')[0]) for path in _default_migrations_dir().glob('*.sql')
                          if int(path.name.split('_')[0]) > 165)
        assert expected[0] == 166
        assert MigrationRunner(factory).apply() == expected
        with factory.unit_of_work(write=False) as uow:
            after = other_rows(uow.connection)
            assert all(after[name] == rows for name, rows in before.items())
            assert uow.connection.execute('SELECT count(*) FROM observation_correlations').fetchone()[0] == 0
            assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []
    finally:
        factory.close()


@pytest.mark.parametrize('changed', [dict(agent_id='bob'), dict(workspace_id='another')])
def test_private_scope_cannot_be_read_or_transferred_by_cas(env, changed):
    first = put(env)
    original_scope = dict(agent_id='alice', workspace_id='ws')
    other_scope = dict(original_scope, **changed)
    assert env.repo.get_scoped(env, observed_instance_id='instance-one', **original_scope) == first
    assert env.repo.get_scoped(env, observed_instance_id='instance-one', **other_scope) is None
    with pytest.raises(OktoNexusError, match='CONFLICT'):
        put(env, 1, **other_scope)
    with pytest.raises(OktoNexusError, match='CONFLICT'):
        env.repo.tombstone(env, observed_instance_id='instance-one', expected_revision=1,
            state='cleared', now=NOW, max_records=4096, **other_scope)
    assert env.repo.get(env, observed_instance_id='instance-one') == first


@pytest.mark.parametrize('keep_agents', [False, True])
@pytest.mark.parametrize('state', ['selected', 'cleared', 'revoked'])
def test_both_resets_remove_proof_but_preserve_scope_revision_and_capacity(env, keep_agents, state):
    before = put(env)
    if state != 'selected':
        before = env.repo.tombstone(env, observed_instance_id='instance-one', expected_revision=1,
            state=state, now=NOW, max_records=4096, agent_id='alice', workspace_id='ws')
    env.connection.commit()
    with env.factory.unit_of_work() as uow:
        clear_operational_history(uow.connection, keep_agents=keep_agents)
    after = env.repo.get(env, observed_instance_id='instance-one')
    assert after['revision'] == before['revision'] + int(state == 'selected')
    assert after['state'] == ('revoked' if state == 'selected' else state)
    assert (after['agent_id'], after['workspace_id']) == ('alice', 'ws')
    assert all(after[key] is None for key in ('selection', 'proof', 'digest', 'provenance', 'verified_at'))
    assert env.repo.capacity(env, max_records=1)['full']
    assert env.connection.execute('SELECT count(*) FROM observation_instances').fetchone()[0] == 0
    assert env.connection.execute('PRAGMA foreign_key_check').fetchall() == []
    with pytest.raises(OktoNexusError, match='CONFLICT'):
        put(env)


def test_reset_revocation_rolls_back_with_the_callers_transaction(env):
    before = put(env)
    env.connection.commit()
    env.connection.execute('BEGIN IMMEDIATE')
    clear_operational_history(env.connection, keep_agents=False)
    assert env.repo.get(env, observed_instance_id='instance-one')['proof'] is None
    env.connection.rollback()
    assert env.repo.get(env, observed_instance_id='instance-one') == before
    assert env.connection.execute('SELECT count(*) FROM observation_instances').fetchone()[0] == 1


def test_revision_exhaustion_does_not_block_reset_or_retain_private_proof(env):
    put(env)
    saturated = selection(MAX_INT64 - 1)
    env.connection.execute('UPDATE observation_correlations SET revision=?,selection_json=?,correlation_digest=?',
        (MAX_INT64, json.dumps(saturated, sort_keys=True, ensure_ascii=False, separators=(',', ':')),
         correlation_digest(saturated, proof())))
    env.connection.commit()
    with env.factory.unit_of_work() as uow:
        clear_operational_history(uow.connection, keep_agents=True)
    row = env.repo.get(env, observed_instance_id='instance-one')
    assert row['revision'] == MAX_INT64 and row['state'] == 'revoked' and row['proof'] is None
    with pytest.raises(OktoNexusError, match='QUOTA_EXCEEDED'):
        put(env, MAX_INT64)
