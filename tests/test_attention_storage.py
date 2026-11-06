"""Migration, atomic episode anchors and concurrent viewing-state persistence."""
from concurrent.futures import ThreadPoolExecutor
import shutil
import threading

import pytest

from fake_clock import FakeClock
from okto_nexus.adapters.outbound.sqlite.attention import SqliteAttentionQueries
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner, _default_migrations_dir
from okto_nexus.bootstrap.dependencies import build_repos
from okto_nexus.errors import ErrorCode, OktoNexusError

NOW = '2026-11-06T12:00:00.000000Z'


def seed(factory, config, *, status='unread'):
    repos, _ = build_repos(FakeClock(iso=NOW), config)
    with factory.unit_of_work() as uow:
        repos.workspaces.upsert(uow, workspace_id='attention-workspace')
        repos.agents.upsert(uow, agent_id='author')
        repos.agents.upsert(uow, agent_id='recipient')
        repos.messages.create(uow, message_id='attention-message', workspace_id='attention-workspace',
            from_agent_id='author', subject='Synthetic migration', body='Do not copy this content into attention.',
            target='{"strategy":"direct","agent_id":"recipient"}', created_at=NOW)
        repos.deliveries.create(uow, delivery_id='attention-delivery', message_id='attention-message',
            recipient_agent_id='recipient', status=status, created_at=NOW)


def rows(factory, table):
    with factory.unit_of_work(write=False) as uow:
        return [dict(row) for row in uow.connection.execute('SELECT * FROM "' + table + '" ORDER BY rowid')]


def test_upgrade_from_160_preserves_canonical_rows_and_backfills_only_metadata(tmp_config, tmp_path):
    old = tmp_path / 'schema-160'
    old.mkdir()
    for path in _default_migrations_dir().glob('*.sql'):
        if int(path.name.split('_')[0]) <= 160:
            shutil.copyfile(path, old / path.name)
    factory = ConnectionFactory(tmp_config)
    try:
        assert MigrationRunner(factory, migrations_dir=old).apply()[-1] == 160
        seed(factory, tmp_config, status='parked')
        tables = ('workspaces', 'agents', 'messages', 'message_deliveries', 'handoffs', 'approvals',
                  'events', 'execution_operations', 'execution_receipts', 'coordination_requests')
        before = {table: rows(factory, table) for table in tables}
        assert MigrationRunner(factory).apply() == [161]
        assert {table: rows(factory, table) for table in tables} == before
        anchors = rows(factory, 'attention_operation_epochs')
        assert len(anchors) == 1
        assert anchors[0]['source_type'] == 'message_delivery'
        assert anchors[0]['source_id'] == 'attention-delivery' and anchors[0]['state'] == 'parked'
        assert anchors[0]['episode'] == 1
        assert anchors[0]['first_detected_at'] == anchors[0]['last_changed_at']
        assert rows(factory, 'attention_preferences') == []
        assert MigrationRunner(factory).apply() == []
        assert rows(factory, 'attention_operation_epochs') == anchors
        # Keeping additive schema is required for rollback; old code refuses a
        # destructive downgrade rather than deleting preferences or receipts.
        with pytest.raises(OktoNexusError) as error:
            MigrationRunner(factory, migrations_dir=old).apply()
        assert error.value.code == ErrorCode.MIGRATION_ERROR
        assert {table: rows(factory, table) for table in tables} == before
    finally:
        factory.close()


def test_episode_transition_and_canonical_change_rollback_together(migrated_factory, tmp_config):
    factory = migrated_factory
    seed(factory, tmp_config)
    before = rows(factory, 'attention_operation_epochs')
    with pytest.raises(RuntimeError, match='before commit'):
        with factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE message_deliveries SET status='parked' WHERE delivery_id='attention-delivery'")
            assert uow.connection.execute("SELECT episode FROM attention_operation_epochs WHERE source_id='attention-delivery'").fetchone()[0] == 2
            raise RuntimeError('Synthetic crash before commit')
    assert rows(factory, 'attention_operation_epochs') == before
    assert rows(factory, 'message_deliveries')[0]['status'] == 'unread'


def test_reentry_has_a_new_episode_under_the_same_storage_timestamp(migrated_factory, tmp_config):
    factory = migrated_factory
    seed(factory, tmp_config)
    with factory.unit_of_work() as uow:
        # Exercise the storage transition clock at a fixed instant. Episode
        # uniqueness must not depend on subsecond clock advancement.
        uow.connection.create_function('strftime', -1, lambda *args: NOW)
        for status, expected in (('parked', 2), ('unread', 3), ('parked', 4)):
            uow.connection.execute('UPDATE message_deliveries SET status=? WHERE delivery_id=?',
                                   (status, 'attention-delivery'))
            row = uow.connection.execute("SELECT * FROM attention_operation_epochs WHERE source_id='attention-delivery'").fetchone()
            assert row['episode'] == expected and row['state'] == status
            assert row['first_detected_at'] == row['last_changed_at'] == NOW
        uow.connection.execute("UPDATE message_deliveries SET status='parked',attempts=attempts+1 WHERE delivery_id='attention-delivery'")
        assert uow.connection.execute("SELECT episode FROM attention_operation_epochs WHERE source_id='attention-delivery'").fetchone()[0] == 4


def test_source_retention_removes_its_anchor_but_not_other_preferences(migrated_factory, tmp_config):
    factory = migrated_factory
    seed(factory, tmp_config)
    query = SqliteAttentionQueries()
    with factory.unit_of_work() as uow:
        query.save_preference(uow, attention_id='att_retained_viewing', seen_at=NOW, snoozed_until=None,
                              expected_revision=0, now=NOW)
        # Canonical message retention removes deliveries before their parent;
        # the message FK deliberately does not cascade.
        uow.connection.execute("DELETE FROM message_deliveries WHERE delivery_id='attention-delivery'")
        uow.connection.execute("DELETE FROM messages WHERE message_id='attention-message'")
    assert rows(factory, 'message_deliveries') == []
    assert rows(factory, 'attention_operation_epochs') == []
    assert rows(factory, 'attention_preferences')[0]['seen_at'] == NOW


def test_concurrent_devices_cannot_overwrite_the_same_preference_revision(migrated_factory, tmp_config):
    barrier = threading.Barrier(6)
    def writer(index):
        factory = ConnectionFactory(tmp_config)
        try:
            barrier.wait(timeout=10)
            with factory.unit_of_work() as uow:
                SqliteAttentionQueries().save_preference(uow, attention_id='att_concurrent',
                    seen_at=NOW, snoozed_until=None, expected_revision=0, now=NOW)
            return 'saved'
        except OktoNexusError as error:
            assert error.code == ErrorCode.CONFLICT
            return 'conflict'
        finally:
            factory.close()
    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(writer, range(6)))
    assert outcomes.count('saved') == 1 and outcomes.count('conflict') == 5
    saved = rows(migrated_factory, 'attention_preferences')
    assert len(saved) == 1 and saved[0]['revision'] == 1
    with migrated_factory.unit_of_work() as uow:
        SqliteAttentionQueries().save_preference(uow, attention_id='att_concurrent', seen_at=NOW,
            snoozed_until='2026-11-06T13:00:00.000000Z', expected_revision=1, now=NOW)
    with pytest.raises(OktoNexusError) as error:
        with migrated_factory.unit_of_work() as uow:
            SqliteAttentionQueries().save_preference(uow, attention_id='att_concurrent', seen_at=None,
                snoozed_until=None, expected_revision=1, now=NOW)
    assert error.value.code == ErrorCode.CONFLICT
    assert rows(migrated_factory, 'attention_preferences')[0]['revision'] == 2
    assert rows(migrated_factory, 'attention_preferences')[0]['seen_at'] == NOW


def test_preference_write_rollback_keeps_no_partial_mark(migrated_factory):
    with pytest.raises(RuntimeError):
        with migrated_factory.unit_of_work() as uow:
            SqliteAttentionQueries().save_preference(uow, attention_id='att_abort', seen_at=NOW,
                snoozed_until=None, expected_revision=0, now=NOW)
            raise RuntimeError('Synthetic cut before commit')
    assert rows(migrated_factory, 'attention_preferences') == []
