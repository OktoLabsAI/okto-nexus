"""Effective Server policy is durable evidence, never inferred configuration."""
import shutil
import sqlite3

import pytest

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner, _default_migrations_dir
from okto_nexus.application.database_reset import clear_operational_history
from okto_nexus.application.server_effective_policy import publish_effective_policy, read_effective_policy
from okto_nexus.config import NexusConfig


NOW = '2026-11-06T15:00:00.000000Z'
LATER = '2026-11-06T16:00:00.000000Z'
VALUES = {'feature_harness_integrations': False, 'feature_hitl': True}


def test_migration_and_settings_writes_do_not_infer_effective_server_policy(migrated_factory):
    with migrated_factory.unit_of_work() as uow:
        assert read_effective_policy(uow) == {}
        uow.connection.execute('INSERT INTO settings(key,value,updated_at) VALUES(?,?,?)',
            ('feature_harness_integrations', 'true', NOW))
        uow.connection.execute('UPDATE settings SET value=?,updated_at=? WHERE key=?',
            ('false', LATER, 'feature_harness_integrations'))
        changes = uow.connection.total_changes
        assert read_effective_policy(uow) == {}
        assert uow.connection.total_changes == changes
    with migrated_factory.unit_of_work(write=False) as uow:
        assert read_effective_policy(uow) == {}


def test_publish_only_material_changes_even_at_same_clock_and_after_restart(migrated_factory, tmp_config):
    with migrated_factory.unit_of_work() as uow:
        first = publish_effective_policy(uow, values=VALUES, now=NOW)
        assert first == {key: dict(value=value, generation=1, changed_at=NOW) for key, value in VALUES.items()}
        changes = uow.connection.total_changes
        assert publish_effective_policy(uow, values=VALUES, now=NOW) == first
        assert publish_effective_policy(uow, values=VALUES, now=LATER) == first
        assert uow.connection.total_changes == changes
        second = publish_effective_policy(uow, values={'feature_harness_integrations': True}, now=NOW)
        assert second['feature_harness_integrations'] == dict(value=True, generation=2, changed_at=NOW)
        third = publish_effective_policy(uow, values={'feature_harness_integrations': False}, now=NOW)
        assert third['feature_harness_integrations'] == dict(value=False, generation=3, changed_at=NOW)
        assert third['feature_hitl'] == first['feature_hitl']
    restarted = ConnectionFactory(tmp_config)
    with restarted.unit_of_work() as uow:
        changes = uow.connection.total_changes
        assert publish_effective_policy(uow, values=VALUES, now=LATER) == third
        assert uow.connection.total_changes == changes


def test_publication_remains_in_callers_transaction_including_partial_sql_failure(migrated_factory):
    with pytest.raises(RuntimeError, match='abort initial publication'):
        with migrated_factory.unit_of_work() as uow:
            publish_effective_policy(uow, values=VALUES, now=NOW)
            raise RuntimeError('abort initial publication')
    with migrated_factory.unit_of_work() as uow:
        assert read_effective_policy(uow) == {}
        initial = publish_effective_policy(uow, values=VALUES, now=NOW)
        uow.connection.execute("""CREATE TRIGGER reject_second_policy BEFORE UPDATE ON server_effective_policy
            WHEN NEW.key='feature_hitl' BEGIN SELECT RAISE(ABORT,'synthetic second policy failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match='synthetic second policy failure'):
        with migrated_factory.unit_of_work() as uow:
            publish_effective_policy(uow, values={key: not value for key, value in VALUES.items()}, now=LATER)
    with migrated_factory.unit_of_work(write=False) as uow:
        assert read_effective_policy(uow) == initial


def test_invalid_publication_is_rejected_before_any_write(migrated_factory):
    with migrated_factory.unit_of_work() as uow:
        before = publish_effective_policy(uow, values=VALUES, now=NOW)
        changes = uow.connection.total_changes
        invalid = [None, [], {'unrecognized_flag': True},
            {'feature_harness_integrations': True, 'feature_hitl': 1},
            {'feature_harness_integrations': 'false'}, {'feature_hitl': None}]
        for values in invalid:
            with pytest.raises(ValueError, match='known keys and boolean values'):
                publish_effective_policy(uow, values=values, now=LATER)
        for timestamp in (None, True, '', 'invalid', '2026-11-06T16:00:00'):
            with pytest.raises(ValueError, match='timestamp with timezone'):
                publish_effective_policy(uow, values={'feature_harness_integrations': True}, now=timestamp)
        assert read_effective_policy(uow) == before
        assert uow.connection.total_changes == changes


def test_sql_constraints_keep_closed_keys_boolean_values_and_positive_integer_generations(migrated_factory):
    with migrated_factory.unit_of_work() as uow:
        invalid = [
            ('unknown', 1, 1, NOW), (None, 1, 1, NOW),
            ('feature_hitl', 2, 1, NOW), ('feature_hitl', 'true', 1, NOW),
            ('feature_hitl', 0.5, 1, NOW), ('feature_hitl', None, 1, NOW),
            ('feature_hitl', 1, 0, NOW), ('feature_hitl', 1, 1.5, NOW),
            ('feature_hitl', 1, 'generation', NOW), ('feature_hitl', 1, 1, None),
        ]
        for row in invalid:
            with pytest.raises(sqlite3.IntegrityError):
                uow.connection.execute('INSERT INTO server_effective_policy VALUES(?,?,?,?)', row)
        assert read_effective_policy(uow) == {}


@pytest.mark.parametrize('keep_agents', [False, True])
def test_reset_preserves_published_policy_generations_and_does_not_reseed(migrated_factory, keep_agents):
    with migrated_factory.unit_of_work() as uow:
        publish_effective_policy(uow, values=VALUES, now=NOW)
        before = publish_effective_policy(uow, values={'feature_hitl': False}, now=LATER)
        uow.connection.execute("INSERT INTO attention_preferences VALUES('operator','att_fixture',?,NULL,1,?)", (NOW, NOW))
        counts = clear_operational_history(uow.connection, keep_agents=keep_agents)
        assert 'server_effective_policy' not in counts
        assert counts['attention_preferences'] == 1
        assert read_effective_policy(uow) == before
    with migrated_factory.unit_of_work() as uow:
        assert publish_effective_policy(uow, values={key: row['value'] for key, row in before.items()}, now=LATER) == before


@pytest.mark.parametrize('start_version', [161, 162])
def test_163_additive_upgrade_preserves_prior_schema_and_attention_history(tmp_path, start_version):
    directory = tmp_path / 'migrations'
    directory.mkdir()
    source = _default_migrations_dir()
    for path in source.glob('*.sql'):
        if int(path.name.split('_', 1)[0]) <= start_version:
            shutil.copyfile(path, directory / path.name)
    factory = ConnectionFactory(NexusConfig(home_dir=tmp_path / 'home',
        feature_harness_integrations=True, feature_hitl=True))
    runner = MigrationRunner(factory, migrations_dir=directory)
    assert runner.apply()[-1] == start_version
    with factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO attention_preferences VALUES('operator','att_fixture',?,NULL,4,?)", (NOW, NOW))
    if start_version == 161:
        path = next(source.glob('162_*.sql'))
        shutil.copyfile(path, directory / path.name)
        assert runner.apply() == [162]
    with factory.unit_of_work(write=False) as uow:
        before_schema = [tuple(row) for row in uow.connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]
        before_rows = {table: [tuple(row) for row in uow.connection.execute('SELECT * FROM ' + table)]
            for table in ('attention_preferences', 'attention_operation_epochs', 'settings', 'runtime_policy_defaults')}
        old_ledger = [tuple(row) for row in uow.connection.execute('SELECT * FROM schema_migrations ORDER BY version')]
    path = next(source.glob('163_*.sql'))
    shutil.copyfile(path, directory / path.name)
    assert runner.apply() == [163]
    assert runner.apply() == []
    with factory.unit_of_work(write=False) as uow:
        assert read_effective_policy(uow) == {}
        assert [tuple(row) for row in uow.connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' "
            "AND name<>'server_effective_policy' ORDER BY type,name")] == before_schema
        for table, rows in before_rows.items():
            assert [tuple(row) for row in uow.connection.execute('SELECT * FROM ' + table)] == rows
        assert [tuple(row) for row in uow.connection.execute(
            'SELECT * FROM schema_migrations WHERE version<=162 ORDER BY version')] == old_ledger
