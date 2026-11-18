"""An additive target link preserves old controls, barriers and receipts."""

import pytest

from okto_nexus.adapters.outbound.sqlite import migrations
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from okto_nexus.adapters.outbound.sqlite.session_interaction_queue_controls import (
    set_input_queue_paused,
)
from okto_nexus.errors import ErrorCode, OktoNexusError
from tests.session_interaction.test_queue_storage import ALICE, enqueue
from tests.session_interaction.test_queue_storage import database as queue_database
from tests.session_interaction.test_receipt_lookup import _store_operation
from tests.test_migrations import _partial_migrations_dir

database = queue_database


@pytest.fixture
def legacy_store(tmp_path, monkeypatch, request):
    legacy = _partial_migrations_dir(tmp_path, 176)
    with monkeypatch.context() as patch:
        patch.setattr(migrations, '_default_migrations_dir', lambda: legacy)
        factory, scopes = request.getfixturevalue('database')
    return factory, scopes[0], legacy


def test_upgrade_preserves_preexisting_interrupt_and_paused_messages(legacy_store, tmp_path):
    factory, scope, legacy = legacy_store
    schema_177 = _partial_migrations_dir(tmp_path, 177)
    key = (scope.session.server_id, scope.session.executor_id)
    with factory.unit_of_work() as uow:
        first = enqueue(uow, scope)
        _store_operation(uow, scope, 'old-interrupt', 'turn.interrupt')
        uow.connection.execute("""
            INSERT INTO session_interaction_controls (server_id,executor_id,session_id,operation_id,owner_generation,
                authority_ref,surface,capability_revision,native_turn_id)
            VALUES (?,?,?,'old-interrupt',?,?,?,'prior-capability','prior-opaque-turn')
        """, (*key, scope.session.session_id, scope.generation.value, ALICE.authority_ref, ALICE.surface))
        assert set_input_queue_paused(uow, scope=scope, paused=True, expected_queue_revision=first.queue_revision,
            capability_revision='pause', verify_authority=lambda: 'pause').paused

    def retained():
        with factory.unit_of_work(write=False) as uow:
            conn = uow.connection
            return (
                tuple(conn.execute('SELECT * FROM session_interaction_controls').fetchone()),
                tuple(conn.execute('SELECT * FROM session_interaction_inputs').fetchone()),
                tuple(conn.execute('SELECT * FROM session_interaction_queues').fetchone()),
            )

    original = retained()
    assert MigrationRunner(factory, migrations_dir=schema_177).apply() == [177]
    assert retained() == original
    with factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        assert conn.execute('SELECT COUNT(*) FROM session_interaction_interrupt_targets').fetchone()[0] == 0
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    assert MigrationRunner(factory, migrations_dir=schema_177).apply() == []
    with pytest.raises(OktoNexusError) as refused:
        MigrationRunner(factory, migrations_dir=legacy).apply()
    assert refused.value.code == ErrorCode.MIGRATION_ERROR
    assert retained() == original
