"""Real SQLite qualification of external observation fences and bounded storage."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import hashlib
import json
import shutil
import sqlite3
import threading

import pytest

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.events_repo import SqliteEventEmitter, SqliteEventRepo
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner, _default_migrations_dir
from okto_nexus.adapters.outbound.sqlite.observations_repo import SqliteObservationRepo, MAX_INTEGER
from okto_nexus.application.database_reset import clear_operational_history
from okto_nexus.bootstrap.dependencies import build_repos
from okto_nexus.domain.observations import parse_report, report_hash
from okto_nexus.errors import ErrorCode, OktoNexusError


NOW = '2026-11-06T15:00:00.000000Z'
PERMISSIONS = {'observations': {'manage_self': True, 'publish': True}}
REPO = SqliteObservationRepo()


def later(seconds):
    return (datetime.fromisoformat(NOW.replace('Z', '+00:00')) + timedelta(seconds=seconds)).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def digest(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def seed(uow, agent='a'):
    uow.connection.execute('INSERT OR IGNORE INTO workspaces(workspace_id,created_at) VALUES(?,?)', ('w', NOW))
    uow.connection.execute('INSERT OR IGNORE INTO workspaces(workspace_id,created_at) VALUES(?,?)', ('other', NOW))
    uow.connection.execute('INSERT INTO agents(agent_id,created_at,is_active,api_key_hash,permissions) VALUES(?,?,1,?,?)',
                           (agent, NOW, 'synthetic-' + agent, json.dumps(PERMISSIONS)))


def setup_source(uow, *, agent='a', registration='registration', external='terminal:1', token='first'):
    source = REPO.create_source(uow, agent_id=agent, source_kind='custom', workspace_ids=['w'], registration_ref=registration, now=NOW)
    instance = REPO.create_instance(uow, source_id=source['source_id'], expected_revision=source['revision'],
        workspace_id='w', external_instance_ref=external, now=NOW)
    minted = REPO.issue_token(uow, source_id=source['source_id'], expected_revision=source['revision'], token_hash=digest(token),
        instance_grants=[{key: instance[key] for key in ('observed_instance_id', 'generation')}],
        issuer_agent_id=None, now=NOW, expires_at=later(900))
    return source, instance, minted


@pytest.fixture
def stored(migrated_factory):
    with migrated_factory.unit_of_work() as uow:
        seed(uow)
        source, instance, token = setup_source(uow)
    return migrated_factory, source, instance, token


def report_for(source, instance, sequence=1, **extra):
    return parse_report(dict(schema_version=1, source_id=source['source_id'],
        observed_instance_id=instance['observed_instance_id'], generation=instance['generation'],
        sequence=sequence, state='working', evidence='reported', observed_at=NOW, **extra))


def save(uow, source, instance, token, sequence=1, *, received=NOW, valid=later(90), **extra):
    report = report_for(source, instance, sequence, **extra)
    return REPO.store_report(uow, report=report.to_dict(), report_hash=report_hash(report),
        source_revision=source['revision'], publisher_token_id=token['token_id'], received_at=received, valid_until=valid)


def snapshot(factory):
    with factory.unit_of_work(write=False) as uow:
        tables = [row[0] for row in uow.connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {table: sorted([tuple(row) for row in uow.connection.execute('SELECT * FROM "' + table + '"')], key=repr) for table in tables}


def test_upgrade_163_additive_no_seed_authority_and_repository_wiring(tmp_config, tmp_path):
    old = tmp_path / 'schema163'
    old.mkdir()
    for path in _default_migrations_dir().glob('*.sql'):
        if int(path.name.split('_')[0]) <= 163:
            shutil.copyfile(path, old / path.name)
    factory = ConnectionFactory(tmp_config)
    try:
        assert MigrationRunner(factory, old).apply()[-1] == 163
        with factory.unit_of_work() as uow:
            seed(uow)
        before = snapshot(factory)
        expected = sorted(int(path.name.split('_')[0]) for path in _default_migrations_dir().glob('*.sql')
                          if int(path.name.split('_')[0]) > 163)
        assert expected[:2] == [164, 165]
        assert MigrationRunner(factory).apply() == expected
        after = snapshot(factory)
        for name in before:
            if name != 'schema_migrations':
                assert before[name] == after[name]
        assert after['observation_installation'] == [(1, 0)]
        assert all(not rows for name, rows in after.items() if name.startswith('observation_') and name != 'observation_installation')
        with factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []
        repos, _ = build_repos(None, tmp_config)
        assert isinstance(repos.observations, SqliteObservationRepo)
        assert MigrationRunner(factory).apply() == []
    finally:
        factory.close()


def test_missing_and_current_reads_are_passive_and_queries_bounded(stored):
    factory, source, instance, token = stored
    with factory.unit_of_work() as uow:
        save(uow, source, instance, token)
    before = snapshot(factory)
    with factory.unit_of_work(write=False) as uow:
        statements = []
        uow.connection.set_trace_callback(statements.append)
        facts = REPO.get_publish_facts(uow, token_hash=digest('first'))
        uow.connection.set_trace_callback(None)
        assert len([sql for sql in statements if sql.lstrip().upper().startswith('SELECT')]) == 4
        assert facts['agent']['permissions'] == PERMISSIONS
        assert facts['source']['allowed_workspace_ids'] == ['w']
        assert facts['heads'][instance['observed_instance_id']]['sequence'] == 1
        changes = uow.connection.total_changes
        assert REPO.get_publish_facts(uow, token_hash=digest('absent')) is None
        assert REPO.get_source(uow, source_id='absent') is None
        assert REPO.get_head(uow, observed_instance_id='absent') is None
        current, = REPO.list_current(uow, agent_id='a', workspace_id='w')
        assert current['head']['publisher_token_id'] == token['token_id']
        assert current['publisher_revoked'] is False
        assert REPO.list_current(uow, workspace_id='other') == []
        assert 'token_hash' not in REPO.list_tokens(uow, source_id=source['source_id'])[0]
        assert uow.connection.total_changes == changes
    assert snapshot(factory) == before


def test_registration_retry_same_source_and_external_ref_never_resets_sequence(stored):
    factory, source, instance, token = stored
    with factory.unit_of_work() as uow:
        receipt = save(uow, source, instance, token)
        repeated = REPO.create_source(uow, agent_id='a', source_kind='custom', workspace_ids=['w'], registration_ref='registration', now=later(30))
        assert repeated == source
        repeated_instance = REPO.create_instance(uow, source_id=source['source_id'], expected_revision=1,
            workspace_id='w', external_instance_ref='terminal:1', now=later(30))
        assert repeated_instance == instance
        assert REPO.check_sequence(uow, observed_instance_id=instance['observed_instance_id'], generation=instance['generation'],
            sequence=1, report_hash=receipt['report_hash']) == receipt
        with pytest.raises(OktoNexusError) as error:
            REPO.create_source(uow, agent_id='a', source_kind='herdr', workspace_ids=['w'], registration_ref='registration', now=NOW)
        assert error.value.code == ErrorCode.CONFLICT


def test_replay_is_exact_after_validity_and_does_not_renew_or_emit(stored):
    factory, source, instance, token = stored
    with factory.unit_of_work() as uow:
        receipt = save(uow, source, instance, token)
    before = snapshot(factory)
    with factory.unit_of_work() as uow:
        assert save(uow, source, instance, token, received=later(120), valid=later(210)) == receipt
    assert snapshot(factory) == before


@pytest.mark.parametrize('sequence,extra', [(1, {'reason_code': 'external_error'}), (1, {'valid_for_seconds': 60}), (1, {})])
def test_changed_or_older_sequence_conflicts_without_mutation(stored, sequence, extra):
    factory, source, instance, token = stored
    with factory.unit_of_work() as uow:
        save(uow, source, instance, token, sequence=2 if not extra else 1)
    before = snapshot(factory)
    with pytest.raises(OktoNexusError) as error:
        with factory.unit_of_work() as uow:
            save(uow, source, instance, token, sequence, **extra)
    assert error.value.code == ErrorCode.CONFLICT
    assert snapshot(factory) == before


def test_last_completion_survives_omission_without_changing_canonical_payload(stored):
    factory, source, instance, token = stored
    with factory.unit_of_work() as uow:
        save(uow, source, instance, token, current_completion_ref='result:A')
        save(uow, source, instance, token, sequence=2, received=later(5))
        head = REPO.get_head(uow, observed_instance_id=instance['observed_instance_id'])
        assert 'current_completion_ref' not in head
        assert head['last_completion_ref'] == 'result:A' and head['last_completion_received_at'] == NOW
        save(uow, source, instance, token, sequence=3, received=later(10), current_completion_ref='result:A')
        assert REPO.get_head(uow, observed_instance_id=instance['observed_instance_id'])['last_completion_received_at'] == NOW
        save(uow, source, instance, token, sequence=4, received=later(20), current_completion_ref='result:B')
        assert REPO.get_head(uow, observed_instance_id=instance['observed_instance_id'])['last_completion_received_at'] == later(20)


def test_source_cas_noop_scope_change_and_reenable_never_restore_old_token(stored):
    factory, source, instance, token = stored
    with factory.unit_of_work() as uow:
        save(uow, source, instance, token)
        changes = uow.connection.total_changes
        assert REPO.update_source(uow, source_id=source['source_id'], expected_revision=1, workspace_ids=['w'], enabled=True, now=later(1)) == source
        assert uow.connection.total_changes == changes
        changed = REPO.update_source(uow, source_id=source['source_id'], expected_revision=1, workspace_ids=['w', 'other'], now=later(2))
        assert changed['revision'] == 2
        assert REPO.get_token_by_hash(uow, token_hash=digest('first'))['revoked_at'] == later(2)
        current, = REPO.list_current(uow)
        assert current['publisher_revoked'] is True and current['head']['source_revision'] == 1
        with pytest.raises(OktoNexusError):
            REPO.revoke_source(uow, source_id=source['source_id'], expected_revision=1, now=later(3))
        revoked = REPO.revoke_source(uow, source_id=source['source_id'], expected_revision=2, now=later(3))
        assert revoked['revision'] == 3
        restored = REPO.update_source(uow, source_id=source['source_id'], expected_revision=3, enabled=True, now=later(4))
        assert restored['revision'] == 4 and restored['revoked_at'] is None
        assert REPO.get_token_by_hash(uow, token_hash=digest('first'))['revoked_at'] == later(2)


def test_rotation_requires_explicit_new_generation_grant_and_retirement_never_reuses_ids(stored):
    factory, source, instance, token = stored
    with factory.unit_of_work() as uow:
        save(uow, source, instance, token)
        rotated = REPO.rotate_instance(uow, source_id=source['source_id'], expected_revision=1,
            observed_instance_id=instance['observed_instance_id'], expected_generation=instance['generation'], now=later(1))
        assert rotated['generation'] > instance['generation']
        assert REPO.get_head(uow, observed_instance_id=instance['observed_instance_id']) is None
        with pytest.raises(OktoNexusError) as error:
            REPO.issue_token(uow, source_id=source['source_id'], expected_revision=1, token_hash=digest('stale-consent'),
                instance_grants=[{key: instance[key] for key in ('observed_instance_id', 'generation')}],
                issuer_agent_id=None, now=later(1), expires_at=later(901))
        assert error.value.code == ErrorCode.CONFLICT
        assert REPO.get_token_by_hash(uow, token_hash=digest('first'))['revoked_at'] == later(1)
        with pytest.raises(OktoNexusError):
            save(uow, source, instance, token, sequence=2)
        REPO.retire_instance(uow, source_id=source['source_id'], expected_revision=1,
            observed_instance_id=rotated['observed_instance_id'], expected_generation=rotated['generation'], now=later(2))
        replacement = REPO.create_instance(uow, source_id=source['source_id'], expected_revision=1,
            workspace_id='w', external_instance_ref='terminal:1', now=later(3))
        assert replacement['generation'] > rotated['generation']
        assert replacement['observed_instance_id'] != instance['observed_instance_id']
        assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('column,value', [
    ('is_active', 0), ('api_key_hash', 'rotated'), ('deleted_at', later(1)),
    ('permissions', json.dumps({'observations': {'manage_self': False, 'publish': True}})),
    ('permissions', json.dumps({'observations': {'manage_self': True, 'publish': False}})),
    ('permissions', '{malformed'), ('permissions', json.dumps({'observations': {'manage_self': 1, 'publish': 'true'}})),
])
def test_agent_material_authority_revokes_durably_and_projects_unavailable(stored, column, value):
    factory, source, instance, token = stored
    with factory.unit_of_work() as uow:
        save(uow, source, instance, token)
        original = uow.connection.execute('SELECT ' + column + ' FROM agents WHERE agent_id=?', ('a',)).fetchone()[0]
        uow.connection.execute('UPDATE agents SET ' + column + '=? WHERE agent_id=?', (value, 'a'))
        revoked = REPO.get_token_by_hash(uow, token_hash=digest('first'))['revoked_at']
        assert revoked is not None
        uow.connection.execute('UPDATE agents SET ' + column + '=? WHERE agent_id=?', (original, 'a'))
        assert REPO.get_token_by_hash(uow, token_hash=digest('first'))['revoked_at'] == revoked
        assert REPO.list_current(uow)[0]['publisher_revoked'] is True


def test_noop_or_unrelated_permission_changes_do_not_revoke(stored):
    factory, _, _, _ = stored
    with factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE agents SET is_active=is_active,api_key_hash=api_key_hash,deleted_at=deleted_at,permissions=permissions')
        uow.connection.execute('UPDATE agents SET permissions=?,color=? WHERE agent_id=?',
            (json.dumps(dict(PERMISSIONS, inbox={'read': False})), '#ff0000', 'a'))
        assert REPO.get_token_by_hash(uow, token_hash=digest('first'))['revoked_at'] is None
        # Malformed and omitted are both false, not a spurious NULL->0 change.
        uow.connection.execute('UPDATE agents SET permissions=?', ('{}',))
        uow.connection.execute('UPDATE observation_tokens SET revoked_at=NULL')
        uow.connection.execute('UPDATE agents SET permissions=?', ('malformed',))
        assert REPO.get_token_by_hash(uow, token_hash=digest('first'))['revoked_at'] is None


def test_issuer_rotation_revokes_foreign_source_and_physical_agent_delete_restricted(stored):
    factory, source, instance, _ = stored
    with factory.unit_of_work() as uow:
        seed(uow, 'issuer')
        issued = REPO.issue_token(uow, source_id=source['source_id'], expected_revision=1, token_hash=digest('delegated'),
            instance_grants=[{key: instance[key] for key in ('observed_instance_id', 'generation')}],
            issuer_agent_id='issuer', now=NOW, expires_at=later(900))
        uow.connection.execute("UPDATE agents SET api_key_hash='new' WHERE agent_id='issuer'")
        assert REPO.get_token_by_hash(uow, token_hash=digest('delegated'))['revoked_at'] is not None
        with pytest.raises(sqlite3.IntegrityError):
            uow.connection.execute("DELETE FROM agents WHERE agent_id='a'")
        assert issued['source_id'] == source['source_id']


@pytest.mark.parametrize('keep_agents', [False, True])
def test_reset_replay_and_quota_fences_survive_and_old_tokens_do_not(stored, keep_agents):
    factory, source, instance, token = stored
    with factory.unit_of_work() as uow:
        save(uow, source, instance, token)
        assert REPO.consume_budget(uow, source_id=source['source_id'], agent_id='a', cost=20, now=NOW)['allowed']
        allocator = uow.connection.execute('SELECT last_generation FROM observation_installation').fetchone()[0]
        buckets = [tuple(row) for row in uow.connection.execute('SELECT * FROM observation_rate_buckets ORDER BY scope_kind')]
        clear_operational_history(uow.connection, keep_agents=keep_agents)
        assert REPO.get_token_by_hash(uow, token_hash=digest('first')) is None
        assert REPO.list_current(uow) == []
        assert uow.connection.execute('SELECT last_generation FROM observation_installation').fetchone()[0] == allocator
        expected_buckets = buckets if keep_agents else [row for row in buckets if row[0] == 'installation']
        assert [tuple(row) for row in uow.connection.execute('SELECT * FROM observation_rate_buckets ORDER BY scope_kind')] == expected_buckets
        assert bool(REPO.get_source(uow, source_id=source['source_id'])) is keep_agents
        if not keep_agents:
            seed(uow)
        replacement_source, replacement, _ = setup_source(uow, token='replacement')
        assert replacement['generation'] > allocator
        assert replacement['observed_instance_id'] != instance['observed_instance_id']
        assert (replacement_source['source_id'] == source['source_id']) is keep_agents
        with pytest.raises(OktoNexusError):
            REPO.check_sequence(uow, observed_instance_id=instance['observed_instance_id'], generation=instance['generation'], sequence=2, report_hash=digest('old'))
        assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []


def test_writer_rollback_includes_tokens_budget_heads_and_atomic_event(stored):
    factory, source, instance, token = stored
    before = snapshot(factory)
    with pytest.raises(RuntimeError):
        with factory.unit_of_work() as uow:
            assert REPO.consume_budget(uow, source_id=source['source_id'], agent_id='a', cost=1, now=NOW)['allowed']
            save(uow, source, instance, token)
            SqliteEventEmitter(SqliteEventRepo()).emit(uow, workspace_id='w', stream='workspace',
                type='observation.state_changed', payload={'source_id': source['source_id']})
            REPO.rotate_instance(uow, source_id=source['source_id'], expected_revision=1,
                observed_instance_id=instance['observed_instance_id'], expected_generation=instance['generation'], now=later(1))
            raise RuntimeError('rollback qualification')
    assert snapshot(factory) == before


@pytest.mark.parametrize('different_hash', [False, True])
def test_concurrent_publish_has_one_event_and_one_replay_or_conflict(stored, different_hash):
    factory, source, instance, token = stored
    gate = threading.Barrier(2)

    def writer(index):
        candidate = report_for(source, instance, reason_code='external_error' if different_hash and index else 'external_activity')
        gate.wait(timeout=5)
        try:
            with factory.unit_of_work() as uow:
                replay = REPO.check_sequence(uow, observed_instance_id=instance['observed_instance_id'],
                    generation=instance['generation'], sequence=1, report_hash=report_hash(candidate))
                if replay is not None:
                    return 'replay'
                REPO.store_report(uow, report=candidate.to_dict(), report_hash=report_hash(candidate), source_revision=1,
                    publisher_token_id=token['token_id'], received_at=NOW, valid_until=later(90))
                SqliteEventEmitter(SqliteEventRepo()).emit(uow, workspace_id='w', stream='workspace', type='observation.state_changed')
                return 'accepted'
        except OktoNexusError as error:
            assert error.code == ErrorCode.CONFLICT
            return 'conflict'

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(writer, [0, 1]))
    assert results == ['accepted', 'conflict' if different_hash else 'replay']
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM observation_heads').fetchone()[0] == 1
        assert uow.connection.execute("SELECT count(*) FROM events WHERE type GLOB 'observation.*'").fetchone()[0] == 1


def test_rate_refill_exact_restart_clock_regression_and_denial_no_write(stored, tmp_config):
    factory, source, _, _ = stored
    with factory.unit_of_work() as uow:
        assert REPO.consume_budget(uow, source_id=source['source_id'], agent_id='a', cost=20, now=NOW)['allowed']
    before = snapshot(factory)
    restarted = ConnectionFactory(tmp_config)
    try:
        with restarted.unit_of_work() as uow:
            assert REPO.consume_budget(uow, source_id=source['source_id'], agent_id='a', cost=1, now=NOW) == {'allowed': False, 'retry_after_seconds': 1}
            assert not REPO.consume_budget(uow, source_id=source['source_id'], agent_id='a', cost=1, now=later(-5))['allowed']
        assert snapshot(factory) == before
        with restarted.unit_of_work() as uow:
            assert REPO.consume_budget(uow, source_id=source['source_id'], agent_id='a', cost=1, now=later(1))['allowed']
            assert not REPO.consume_budget(uow, source_id=source['source_id'], agent_id='a', cost=1, now=later(1))['allowed']
    finally:
        restarted.close()


def test_agent_aggregate_prevents_multiple_source_amplification(stored):
    factory, source, _, _ = stored
    with factory.unit_of_work() as uow:
        sources = [source]
        for index in range(4):
            sources.append(REPO.create_source(uow, agent_id='a', source_kind='custom', workspace_ids=['w'], registration_ref=str(index), now=NOW))
        for item in sources[:4]:
            assert REPO.consume_budget(uow, source_id=item['source_id'], agent_id='a', cost=20, now=NOW)['allowed']
        assert not REPO.consume_budget(uow, source_id=sources[4]['source_id'], agent_id='a', cost=1, now=NOW)['allowed']
        assert uow.connection.execute("SELECT count(*) FROM observation_rate_buckets WHERE scope_kind='source'").fetchone()[0] == 4


def test_installation_aggregate_and_management_without_source(stored):
    factory, source, _, _ = stored
    rates = {'source': (60, 20), 'agent': (60, 20), 'installation': (60, 2)}
    with factory.unit_of_work() as uow:
        seed(uow, 'b')
        seed(uow, 'c')
        assert REPO.consume_budget(uow, source_id=None, agent_id='a', cost=1, now=NOW, rates=rates)['allowed']
        assert REPO.consume_budget(uow, source_id=None, agent_id='b', cost=1, now=NOW, rates=rates)['allowed']
        assert not REPO.consume_budget(uow, source_id=None, agent_id='c', cost=1, now=NOW, rates=rates)['allowed']
        assert uow.connection.execute("SELECT count(*) FROM observation_rate_buckets WHERE scope_id='c'").fetchone()[0] == 0


def test_source_instance_token_cardinality_and_referenced_expired_token_retention(stored):
    factory, source, instance, token = stored
    with factory.unit_of_work() as uow:
        save(uow, source, instance, token)
        for index in range(7):
            REPO.issue_token(uow, source_id=source['source_id'], expected_revision=1, token_hash=digest(index),
                instance_grants=[{key: instance[key] for key in ('observed_instance_id', 'generation')}],
                issuer_agent_id=None, now=NOW, expires_at=later(900))
        with pytest.raises(OktoNexusError) as error:
            REPO.issue_token(uow, source_id=source['source_id'], expected_revision=1, token_hash=digest('ninth'),
                instance_grants=[{key: instance[key] for key in ('observed_instance_id', 'generation')}],
                issuer_agent_id=None, now=NOW, expires_at=later(900))
        assert error.value.code == ErrorCode.QUOTA_EXCEEDED
        assert REPO.count_prunable(uow, now=later(901)) == {'tokens': 7, 'rate_buckets': 0}
        assert REPO.prune(uow, now=later(901), limit=3)['tokens'] == 3
        assert REPO.prune(uow, now=later(901), limit=100)['tokens'] == 4
        assert REPO.get_token_by_hash(uow, token_hash=digest('first')) is not None
        assert REPO.get_head(uow, observed_instance_id=instance['observed_instance_id'])['sequence'] == 1
        assert REPO.list_current(uow)[0]['publisher_revoked'] is False
        with pytest.raises(OktoNexusError):
            REPO.create_instance(uow, source_id=source['source_id'], expected_revision=1, workspace_id='w', external_instance_ref='second', now=NOW, instance_limit=1)
        with pytest.raises(OktoNexusError):
            REPO.create_source(uow, agent_id='a', source_kind='custom', workspace_ids=['w'], registration_ref='second', now=NOW, source_limit=1)


def test_events_age_and_count_bounds_only_remove_observation_family(stored):
    factory, _, _, _ = stored
    with factory.unit_of_work() as uow:
        for index in range(10):
            uow.connection.execute('INSERT INTO events(workspace_id,stream,type,created_at) VALUES(?,?,?,?)',
                                   ('w', 'workspace', 'observation.state_changed', later(index)))
        uow.connection.execute('INSERT INTO events(workspace_id,stream,type,created_at) VALUES(?,?,?,?)', ('w', 'workspace', 'message.sent', NOW))
        assert REPO.count_prunable_events(uow, cutoff=later(2), max_events=5) == 5
        assert REPO.prune_events(uow, cutoff=later(2), max_events=5, limit=3) == 3
        assert REPO.prune_events(uow, cutoff=later(2), max_events=5, limit=3) == 2
        assert REPO.count_prunable_events(uow, cutoff=later(2), max_events=5) == 0
        assert uow.connection.execute("SELECT count(*) FROM events WHERE type='message.sent'").fetchone()[0] == 1


def test_signed64_generation_and_sequence_limits_fail_without_wrap(stored):
    factory, source, instance, token = stored
    with factory.unit_of_work() as uow:
        save(uow, source, instance, token, sequence=MAX_INTEGER)
        uow.connection.execute('UPDATE observation_installation SET last_generation=?', (MAX_INTEGER,))
        with pytest.raises(OktoNexusError) as error:
            REPO.rotate_instance(uow, source_id=source['source_id'], expected_revision=1,
                observed_instance_id=instance['observed_instance_id'], expected_generation=instance['generation'], now=NOW)
        assert error.value.code == ErrorCode.QUOTA_EXCEEDED
        assert REPO.get_head(uow, observed_instance_id=instance['observed_instance_id'])['sequence'] == MAX_INTEGER
        with pytest.raises(sqlite3.IntegrityError):
            uow.connection.execute('UPDATE observation_instances SET generation=1.5')
        with pytest.raises(sqlite3.IntegrityError):
            uow.connection.execute('UPDATE observation_heads SET sequence=0')


@pytest.mark.parametrize('change', ['revoked', 'workspace_removed'])
def test_retire_is_cleanup_after_authority_loss_but_keeps_cas(stored, change):
    factory, source, instance, token = stored
    with factory.unit_of_work() as uow:
        save(uow, source, instance, token)
        changed = REPO.update_source(uow, source_id=source['source_id'], expected_revision=1, now=later(1),
            **({'enabled': False} if change == 'revoked' else {'workspace_ids': ['other']}))
        with pytest.raises(OktoNexusError):
            REPO.retire_instance(uow, source_id=source['source_id'], expected_revision=1,
                observed_instance_id=instance['observed_instance_id'], expected_generation=instance['generation'], now=later(2))
        REPO.retire_instance(uow, source_id=source['source_id'], expected_revision=changed['revision'],
            observed_instance_id=instance['observed_instance_id'], expected_generation=instance['generation'], now=later(2))
        assert REPO.list_current(uow) == []


def test_page_sentinel_and_source_continuity_use_other_instance(stored):
    factory, source, instance, token = stored
    with factory.unit_of_work() as uow:
        save(uow, source, instance, token)
        second = REPO.create_instance(uow, source_id=source['source_id'], expected_revision=1,
            workspace_id='w', external_instance_ref='second', now=NOW, instance_limit=65536)
        second_token = REPO.issue_token(uow, source_id=source['source_id'], expected_revision=1, token_hash=digest('second'),
            instance_grants=[{key: second[key] for key in ('observed_instance_id', 'generation')}],
            issuer_agent_id=None, now=NOW, expires_at=later(900), max_live=64)
        save(uow, source, second, second_token, received=later(30))
        page = REPO.list_current(uow, limit=1)
        assert page[0]['instance']['observed_instance_id'] == instance['observed_instance_id']
        assert page[0]['head']['received_at'] == NOW
        assert page[0]['source_last_received_at'] == later(30)
        assert len(REPO.list_current(uow, limit=201)) == 2
        assert len(REPO.list_sources(uow, limit=201)) == 1
        assert len(REPO.list_instances(uow, source_id=source['source_id'], limit=201)) == 2
        assert len(REPO.list_tokens(uow, source_id=source['source_id'], limit=201)) == 2
        REPO.create_source(uow, agent_id='a', source_kind='custom', workspace_ids=['w'],
            registration_ref='configured-higher', now=NOW, source_limit=1024, installation_limit=65536)


def test_injected_sqlite_commit_failure_does_not_persist_receipt_or_event(stored, monkeypatch):
    """Inject the storage failure at the real UoW commit boundary, not a service stub."""
    factory, source, instance, token = stored
    before = snapshot(factory)
    uow = factory.unit_of_work()

    def failed_commit():
        raise sqlite3.OperationalError('database or disk is full')

    monkeypatch.setattr(uow, 'commit', failed_commit)
    with pytest.raises(sqlite3.OperationalError, match='disk is full'):
        with uow:
            save(uow, source, instance, token)
            SqliteEventEmitter(SqliteEventRepo()).emit(uow, workspace_id='w', stream='workspace', type='observation.state_changed')
    assert snapshot(factory) == before


@pytest.mark.parametrize('keep_agents', [False, True])
def test_reset_rollback_restores_all_replay_and_authority_fences(stored, keep_agents):
    factory, source, instance, token = stored
    with factory.unit_of_work() as uow:
        save(uow, source, instance, token)
        REPO.consume_budget(uow, source_id=source['source_id'], agent_id='a', cost=20, now=NOW)
    before = snapshot(factory)
    with pytest.raises(RuntimeError, match='cancel reset'):
        with factory.unit_of_work() as uow:
            clear_operational_history(uow.connection, keep_agents=keep_agents)
            raise RuntimeError('cancel reset')
    assert snapshot(factory) == before


def test_rotation_and_publication_race_never_admits_old_generation_after_rotation(stored):
    factory, source, instance, token = stored
    gate = threading.Barrier(2)

    def rotate():
        gate.wait(timeout=5)
        with factory.unit_of_work() as uow:
            return REPO.rotate_instance(uow, source_id=source['source_id'], expected_revision=1,
                observed_instance_id=instance['observed_instance_id'], expected_generation=instance['generation'], now=later(1))

    def publish():
        gate.wait(timeout=5)
        try:
            with factory.unit_of_work() as uow:
                save(uow, source, instance, token)
                SqliteEventEmitter(SqliteEventRepo()).emit(uow, workspace_id='w', stream='workspace', type='observation.state_changed')
                return 'accepted_before_rotation'
        except OktoNexusError as error:
            assert error.code == ErrorCode.CONFLICT
            return 'fenced_after_rotation'

    with ThreadPoolExecutor(max_workers=2) as pool:
        rotation = pool.submit(rotate)
        publication = pool.submit(publish)
        current, outcome = rotation.result(), publication.result()
    with factory.unit_of_work(write=False) as uow:
        assert current['generation'] > instance['generation']
        assert REPO.get_head(uow, observed_instance_id=instance['observed_instance_id']) is None
        assert REPO.get_token_by_hash(uow, token_hash=digest('first'))['revoked_at'] == later(1)
        events = uow.connection.execute("SELECT count(*) FROM events WHERE type GLOB 'observation.*'").fetchone()[0]
        assert events == int(outcome == 'accepted_before_rotation')


def test_rate_policy_reduction_and_prune_never_restore_existing_entity_budget(stored):
    factory, source, _, _ = stored
    slower = {'source': (1, 20), 'agent': (1920, 80), 'installation': (8192, 512)}
    with factory.unit_of_work() as uow:
        assert REPO.consume_budget(uow, source_id=source['source_id'], agent_id='a', cost=20, now=NOW)['allowed']
        assert REPO.count_prunable(uow, now=later(20))['rate_buckets'] == 0
        assert REPO.prune(uow, now=later(20))['rate_buckets'] == 0
        assert REPO.consume_budget(uow, source_id=source['source_id'], agent_id='a', cost=1, now=later(20), rates=slower) == {
            'allowed': False, 'retry_after_seconds': 40}
        # Existing actors without an OBS source still retain management quota.
        seed(uow, 'manager-only')
        assert REPO.consume_budget(uow, source_id=None, agent_id='manager-only', cost=1, now=NOW)['allowed']
        assert REPO.prune(uow, now=later(10000))['rate_buckets'] == 0
        assert uow.connection.execute("SELECT 1 FROM observation_rate_buckets WHERE scope_kind='agent' AND scope_id='manager-only'").fetchone()


def test_prune_removes_only_orphan_buckets_with_shared_batch_bound(stored):
    factory, source, _, _ = stored
    with factory.unit_of_work() as uow:
        assert REPO.consume_budget(uow, source_id=source['source_id'], agent_id='a', cost=20, now=NOW)['allowed']
        uow.connection.executemany('INSERT INTO observation_rate_buckets VALUES(?,?,0,0,?)',
            [('source', 'removed-source', MAX_INTEGER), ('agent', 'removed-agent', MAX_INTEGER)])
        assert REPO.count_prunable(uow, now=NOW)['rate_buckets'] == 2
        assert REPO.prune(uow, now=NOW, limit=1) == {'tokens': 0, 'rate_buckets': 1}
        assert REPO.prune(uow, now=NOW, limit=1) == {'tokens': 0, 'rate_buckets': 1}
        assert REPO.count_prunable(uow, now=later(10000))['rate_buckets'] == 0
        assert uow.connection.execute('SELECT count(*) FROM observation_rate_buckets').fetchone()[0] == 3
