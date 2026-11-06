"""161→162 preserves viewing state across native/handoff identity unification."""
import json
import shutil
import sqlite3
from types import SimpleNamespace

import pytest

import test_attention_operations as operations
from fake_clock import FakeClock
from okto_nexus.adapters.outbound.sqlite.attention import SqliteAttentionQueries
from okto_nexus.adapters.outbound.sqlite.attention_results import SOURCE_SQL
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import (
    MigrationRunner, _attention_id_v1, _default_migrations_dir,
)
from okto_nexus.application.attention import AttentionService
from okto_nexus.bootstrap.dependencies import build_repos
from okto_nexus.bootstrap.execution_authority import build_execution_access
from okto_nexus.domain.attention import occurrence, stamp
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError

NOW, LATER = operations.NOW, operations.LATER
OPERATOR = RuntimeRequestContext(None, 'http_loopback', trusted_local_operator=True)


def attention_id(source, identity, episode):
    return occurrence(kind='result_unseen', source_type=source, source_id=identity, episode=episode,
        source_revision=1, first_detected_at=NOW, last_changed_at=NOW)['attention_id']


OLD_ID = attention_id('execution_result', 'op', ['s', 'e', 'stream', 1])
NEW_ID = attention_id('handoff_result', 'h', 1)


@pytest.fixture
def legacy(tmp_config, tmp_path):
    old = tmp_path / 'schema161'
    old.mkdir()
    for path in _default_migrations_dir().glob('*.sql'):
        if int(path.name.split('_')[0]) <= 161:
            shutil.copyfile(path, old / path.name)
    factory = ConnectionFactory(tmp_config)
    try:
        assert MigrationRunner(factory, old).apply()[-1] == 161
        with factory.unit_of_work() as uow:
            operations.seed(uow.connection)
            operations.managed_operation(uow.connection)
            uow.connection.execute("INSERT INTO execution_domain_deliveries VALUES('s','e','op','domain-op')")
            operations.canonical_result(uow.connection, terminal=1)
        clock = FakeClock(iso=LATER)
        repos, _ = build_repos(clock, tmp_config)
        deps = SimpleNamespace(config=tmp_config, connection_factory=factory, repos=repos,
                               clock=clock, runtime_admission_fence=None)
        tmp_config.feature_attention = True
        attention = AttentionService(factory=factory, access=build_execution_access(deps),
            queries=SqliteAttentionQueries(), clock=clock, config=tmp_config)
        yield factory, attention
    finally:
        factory.close()


def snapshot(factory, *, canonical=False):
    with factory.unit_of_work(write=False) as uow:
        names = [row[0] for row in uow.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {name: sorted((tuple(row) for row in uow.connection.execute('SELECT * FROM "' + name + '"')), key=repr)
                for name in names if not canonical or name not in
                {'schema_migrations', 'attention_preferences', 'attention_operation_epochs'}}


def preference(factory, identity=OLD_ID, *, seen=None, snooze=None, revision=1, updated=NOW):
    with factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO attention_preferences VALUES('operator',?,?,?,?,?)",
            (identity, seen, snooze, revision, updated))


@pytest.mark.parametrize('path', ['upgrade', 'insert', 'update'])
@pytest.mark.parametrize('status', ['COMPLETED', 'REJECTED'])
def test_nullable_handoff_update_time_preserves_canonical_data_and_result(legacy, path, status):
    """The schema permits terminal handoffs without an update timestamp."""
    factory, attention = legacy
    if path != 'upgrade':
        assert MigrationRunner(factory).apply() == [162]
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "INSERT INTO handoffs(handoff_id,workspace_id,from_agent_id,target,visibility,"
            "status,created_at,claimed_by,result,rejected_reason) "
            "VALUES('nullable-terminal','ws','creator','{}','public',?,?,'worker',?,?)",
            ('OPEN' if path == 'update' else status, NOW,
             '{"summary":"stored result"}' if status == 'COMPLETED' else None,
             'stored rejection' if status == 'REJECTED' else None))
        if path == 'update':
            assert uow.connection.execute(
                "SELECT 1 FROM attention_operation_epochs WHERE source_type='handoff_result' "
                "AND source_id=json_array('nullable-terminal',0)").fetchone() is None
            uow.connection.execute("UPDATE handoffs SET status=? WHERE handoff_id='nullable-terminal'", (status,))
    canonical = snapshot(factory, canonical=True)
    if path == 'upgrade':
        assert MigrationRunner(factory).apply() == [162]
        assert snapshot(factory, canonical=True) == canonical
    before_read = snapshot(factory)
    with factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute(
            "SELECT created_at,updated_at,status,result,rejected_reason FROM handoffs "
            "WHERE handoff_id='nullable-terminal'").fetchone()
        assert tuple(row) == (NOW, None, status,
            '{"summary":"stored result"}' if status == 'COMPLETED' else None,
            'stored rejection' if status == 'REJECTED' else None)
        facts = [json.loads(row['facts']) for row in uow.connection.execute(
            SOURCE_SQL, dict(now=LATER, workspace_id=None, agent_id=None))]
        terminal, = [fact for fact in facts if fact.get('handoff_id') == 'nullable-terminal']
        assert terminal['terminal_at'] == terminal['first_detected_at'] == terminal['last_changed_at'] == NOW
        assert terminal['terminal_status'] == status
    item, = [item for item in attention.read(context=OPERATOR,
        filters={'kind': 'result_unseen', 'state': 'all'})['items'] if item['source_id'] == 'nullable-terminal']
    assert item['attention_id'] == attention_id('handoff_result', 'nullable-terminal', 0)
    assert item['first_detected_at'] == item['last_changed_at'] == stamp(NOW)
    assert item['resolution'] == 'resolved' and item['active']
    assert item['allowed_actions'] == ['inspect_handoff']
    assert 'stored result' not in json.dumps(item) and 'stored rejection' not in json.dumps(item)
    assert snapshot(factory) == before_read


@pytest.mark.parametrize('mode', ['seen', 'snoozed'])
def test_upgrade_preserves_seen_or_snooze_across_projection_and_retention(legacy, mode):
    factory, attention = legacy
    preference(factory, seen=NOW if mode == 'seen' else None,
               snooze='2026-11-06T11:00:00.000001-03:00' if mode == 'snoozed' else None, revision=3)
    before = snapshot(factory, canonical=True)
    assert MigrationRunner(factory).apply() == [162]
    assert snapshot(factory, canonical=True) == before
    assert attention.read(context=OPERATOR, filters={'kind': 'result_unseen'})['total'] == 0
    item, = attention.read(context=OPERATOR, filters={'kind': 'result_unseen', 'state': 'all'})['items']
    assert item['attention_id'] == NEW_ID
    assert item['seen_state'][mode if mode == 'seen' else 'snoozed'] is True
    assert item['seen_state']['revision'] == 4
    # Completion and native-result retention cannot resurrect the merged card.
    with factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE handoffs SET status='COMPLETED',updated_at=? WHERE handoff_id='h'", (LATER,))
        uow.connection.execute('DELETE FROM execution_results')
        assert uow.connection.execute('SELECT revision FROM attention_preferences WHERE attention_id=?', (OLD_ID,)).fetchone()[0] == 3
    assert attention.read(context=OPERATOR, filters={'kind': 'result_unseen'})['total'] == 0
    item, = attention.read(context=OPERATOR, filters={'kind': 'result_unseen', 'state': 'all'})['items']
    assert item['attention_id'] == NEW_ID and item['seen_state']['revision'] == 4
    after = snapshot(factory)
    assert MigrationRunner(factory).apply() == []
    assert snapshot(factory) == after


def test_multiple_native_turn_preferences_merge_conservatively_with_existing_claim(legacy):
    factory, attention = legacy
    second_id = attention_id('execution_result', 'op2', ['s', 'e', 'stream', 2])
    with factory.unit_of_work() as uow:
        c = uow.connection
        operations.execution(c, 'op2')
        c.execute("UPDATE execution_operations SET session_id='session-op' WHERE operation_id='op2'")
        c.execute("INSERT INTO execution_domain_deliveries VALUES('s','e','op2','domain-op')")
        c.execute("INSERT INTO execution_event_ingress SELECT server_id,executor_id,session_id,stream_epoch,2,"
            "'second','turn_state','{}',received_at FROM execution_event_ingress")
        c.execute("INSERT INTO execution_results(server_id,executor_id,operation_id,session_id,stream_epoch,"
            "output_text,delivery_outcome,captured_at,terminal_sequence) SELECT server_id,executor_id,'op2',session_id,stream_epoch,"
            "output_text,delivery_outcome,captured_at,2 FROM execution_results")
    preference(factory, seen='2026-11-06T12:00:00.000002Z', snooze='2026-11-06T14:00:00Z', revision=8)
    preference(factory, second_id, seen='2026-11-06T09:00:00.000001-03:00',
               snooze='2026-11-06T11:00:00.000001-03:00', revision=5, updated='2026-11-06T12:30:00Z')
    preference(factory, NEW_ID, snooze='2026-11-06T13:30:00Z', revision=4, updated=LATER)
    assert MigrationRunner(factory).apply() == [162]
    item, = attention.read(context=OPERATOR, filters={'kind': 'result_unseen', 'state': 'all'})['items']
    assert item['seen_state'] == dict(seen=True, seen_at='2026-11-06T09:00:00.000001-03:00',
        snoozed=True, snoozed_until='2026-11-06T11:00:00.000001-03:00', revision=9)
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM attention_preferences').fetchone()[0] == 3
        assert uow.connection.execute('SELECT updated_at FROM attention_preferences WHERE attention_id=?', (NEW_ID,)).fetchone()[0] == LATER


def test_upgrade_does_not_transfer_a_cross_workspace_unproven_link(legacy):
    factory, attention = legacy
    with factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_operations SET workspace_id='other' WHERE operation_id='op'")
    preference(factory, seen=NOW)
    assert MigrationRunner(factory).apply() == [162]
    item, = attention.read(context=OPERATOR, filters={'kind': 'result_unseen', 'state': 'all'})['items']
    assert item['attention_id'] == OLD_ID and item['seen_state']['seen']
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM attention_preferences').fetchone()[0] == 1


def test_upgrade_preference_merge_and_anchors_roll_back_together_and_udfs_are_removed(legacy, tmp_path):
    factory, _ = legacy
    preference(factory, seen=NOW)
    original = next(_default_migrations_dir().glob('162_*.sql'))
    failing = tmp_path / original.name
    failing.write_text(original.read_text(encoding='utf-8') + '\nSELECT * FROM synthetic_missing_table;\n', encoding='utf-8')
    before = snapshot(factory)
    conn = factory.get_connection()
    try:
        with pytest.raises(OktoNexusError):
            MigrationRunner(factory)._apply_one(conn, 162, failing)
        assert not conn.in_transaction
        for sql in ("SELECT nexus_attention_id_v1('k','s','id','1')", "SELECT nexus_attention_stamp_v1('2026-11-06T12:00:00Z')"):
            with pytest.raises(sqlite3.OperationalError):
                conn.execute(sql).fetchone()
    finally:
        conn.close()
    assert snapshot(factory) == before
    assert MigrationRunner(factory).apply() == [162]


def test_frozen_migration_identity_matches_v1_unicode_and_does_not_import_future_version(monkeypatch):
    from okto_nexus.domain import attention
    expected = attention_id('handoff_result', 'tarefa-ação', 3)
    monkeypatch.setattr(attention, 'VERSION', 999)
    assert _attention_id_v1('result_unseen', 'handoff_result', 'tarefa-ação', json.dumps(3)) == expected
