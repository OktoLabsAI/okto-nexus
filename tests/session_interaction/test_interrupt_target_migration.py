"""An additive target link preserves old controls, barriers and receipts."""

import pytest

from okto_nexus.adapters.outbound.sqlite import migrations
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from okto_nexus.adapters.outbound.sqlite.session_interaction_queue_controls import (
    set_input_queue_paused,
)
from okto_nexus.errors import ErrorCode, OktoNexusError
from tests.session_interaction.test_queue_storage import ALICE
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
        # Seed data through the old schema shape, independently of the current writer.
        uow.connection.execute("""
            INSERT INTO session_interaction_queues (server_id,executor_id,session_id,next_sequence,revision)
            VALUES (?,?,?,2,1)
        """, (*key, scope.session.session_id))
        uow.connection.execute("""
            INSERT INTO session_interaction_inputs (server_id,executor_id,session_id,owner_generation,binding_id,
                workspace_id,workspace_binding_id,agent_id,input_id,authority_ref,surface,client_intent_id,fingerprint,
                enqueue_sequence,capability_revision,content,status,created_at,expires_at)
            VALUES (?,?,?,?,?,?,?,?,'prior-input',?,?,'prior-intent','prior-fingerprint',1,'prior-capability',
                'The retained input.','QUEUED','2026-01-01T00:00:00+00:00','2026-01-02T00:00:00+00:00')
        """, (*key, scope.session.session_id, scope.generation.value, scope.binding_id, scope.workspace_id,
              scope.workspace_binding_id, scope.agent_id, ALICE.authority_ref, ALICE.surface))
        _store_operation(uow, scope, 'old-interrupt', 'turn.interrupt')
        uow.connection.execute("""
            INSERT INTO session_interaction_controls (server_id,executor_id,session_id,operation_id,owner_generation,
                authority_ref,surface,capability_revision,native_turn_id)
            VALUES (?,?,?,'old-interrupt',?,?,?,'prior-capability','prior-opaque-turn')
        """, (*key, scope.session.session_id, scope.generation.value, ALICE.authority_ref, ALICE.surface))
        assert set_input_queue_paused(uow, scope=scope, paused=True, expected_queue_revision=1,
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
    assert MigrationRunner(factory, migrations_dir=_partial_migrations_dir(tmp_path, 178)).apply() == [178]
    assert retained() == original
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT input_id FROM session_interaction_pending_inputs').fetchone()[0] == 'prior-input'
    assert MigrationRunner(factory, migrations_dir=_partial_migrations_dir(tmp_path, 179)).apply() == [179]
    assert retained() == original
    with factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        assert conn.execute('SELECT native_launch_build_json FROM execution_sessions WHERE session_id=?',
                            (scope.session.session_id,)).fetchone()[0] is None
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    assert MigrationRunner(factory, migrations_dir=_partial_migrations_dir(tmp_path, 180)).apply() == [180]
    assert retained() == original
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM session_attachments').fetchone()[0] == 0
        assert not uow.connection.execute('PRAGMA foreign_key_check').fetchall()
    schema_181 = MigrationRunner(factory, migrations_dir=_partial_migrations_dir(tmp_path, 181))
    assert schema_181.apply() == [181]
    assert schema_181.apply() == []
    assert retained() == original
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM embedded_codex_saved_contexts').fetchone()[0] == 0
        assert not uow.connection.execute('PRAGMA foreign_key_check').fetchall()
