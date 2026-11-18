"""SQLite queue barriers using seeded session and lease state only."""

from dataclasses import replace
from sqlite3 import IntegrityError

import pytest

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.session_interaction_queue_controls import (
    QueuePauseReceipt,
    is_input_queue_paused,
    set_input_queue_paused,
)
from okto_nexus.domain.execution.keys import SessionOwnerGeneration
from okto_nexus.domain.session_interaction import MAX_SQLITE_INTEGER, InputDeliveryState
from okto_nexus.errors import ErrorCode, OktoNexusError
from tests.session_interaction.test_queue_storage import database as queue_database
from tests.session_interaction.test_queue_storage import enqueue

database = queue_database


def _control(uow, scope, revision, *, paused=True, verify_authority=lambda: "fixture-capability"):
    return set_input_queue_paused(
        uow, scope=scope, paused=paused, expected_queue_revision=revision,
        capability_revision="fixture-capability", verify_authority=verify_authority,
    )


def _set_active_lease(uow, scope):
    uow.connection.execute("UPDATE execution_sessions SET lease_state='ACTIVE' WHERE executor_id=?",
                           (scope.session.executor_id,))


def test_pause_before_first_input_is_durable_and_keeps_fifo_and_quota(database, monkeypatch):
    factory, (scope, sibling) = database
    monkeypatch.setattr("okto_nexus.adapters.outbound.sqlite.session_interaction.MAX_PENDING", 1)
    with factory.unit_of_work() as uow:
        conn = uow.connection
        assert not is_input_queue_paused(conn, scope.session)
        assert _control(uow, scope, 0) == QueuePauseReceipt(1, 1)
        assert tuple(conn.execute("SELECT next_sequence, revision FROM session_interaction_queues").fetchone()) == (1, 1)
        assert _control(uow, scope, 1) == QueuePauseReceipt(1, 1)
        first = enqueue(uow, scope, intent="first", text="Keep this text exactly.")
        assert first.sequence == 1 and first.status is InputDeliveryState.QUEUED and first.queue_revision == 2
        with pytest.raises(OktoNexusError) as error:
            enqueue(uow, scope, intent="over-quota")
        assert error.value.details["reason"] == "INPUT_QUEUE_FULL"
        assert is_input_queue_paused(conn, scope.session)
        assert not is_input_queue_paused(conn, sibling.session)
        assert enqueue(uow, sibling, intent="sibling-first").sequence == 1

    reopened = ConnectionFactory(factory.config)
    try:
        with reopened.unit_of_work(write=False) as uow:
            assert is_input_queue_paused(uow.connection, scope.session)
            assert not is_input_queue_paused(uow.connection, sibling.session)
    finally:
        reopened.close()
    with factory.unit_of_work() as uow:
        assert enqueue(uow, scope, intent="first", text="Keep this text exactly.") == first


def test_pause_survives_owner_change_until_explicit_resume_with_current_lease(database):
    factory, (scope, sibling) = database
    current_scope = replace(scope, generation=SessionOwnerGeneration(2))
    with factory.unit_of_work() as uow:
        first = enqueue(uow, scope, intent="first")
        conn = uow.connection
        before_pause = conn.execute("SELECT * FROM execution_sessions").fetchall()
        assert _control(uow, scope, first.queue_revision) == QueuePauseReceipt(2, 1)
        assert conn.execute("SELECT * FROM execution_sessions").fetchall() == before_pause
        conn.execute("UPDATE execution_sessions SET owner_generation=2 WHERE executor_id=?", (scope.session.executor_id,))
        assert is_input_queue_paused(conn, scope.session)
        with pytest.raises(OktoNexusError) as error:
            _control(uow, current_scope, 2, paused=False)
        assert error.value.details["reason"] == "INPUT_SESSION_CHANGED"
        _set_active_lease(uow, current_scope)
        with pytest.raises(OktoNexusError) as error:
            _control(uow, scope, 2, paused=False)
        assert error.value.details["reason"] == "INPUT_SESSION_CHANGED"
        assert is_input_queue_paused(conn, current_scope.session)
        assert not is_input_queue_paused(conn, sibling.session)

        unchanged_tables = ("session_interaction_inputs", "execution_sessions", "execution_bindings", "execution_executors",
                            "runtime_execution_grants", "execution_leases", "execution_operations", "execution_dispatch_outbox")
        before = {table: conn.execute(f"SELECT * FROM {table}").fetchall() for table in unchanged_tables}
        assert _control(uow, current_scope, 2, paused=False) == QueuePauseReceipt(3, None)
        assert _control(uow, current_scope, 3, paused=False) == QueuePauseReceipt(3, None)
        assert not is_input_queue_paused(conn, scope.session)
        assert {table: conn.execute(f"SELECT * FROM {table}").fetchall() for table in unchanged_tables} == before


def test_pause_and_resume_refuse_stale_revisions_wrong_scope_and_missing_authority(database):
    factory, (scope, sibling) = database
    with factory.unit_of_work() as uow:
        for wrong in (replace(scope, workspace_id=sibling.workspace_id),
                      replace(scope, binding_id=sibling.binding_id),
                      replace(scope, generation=SessionOwnerGeneration(2))):
            with pytest.raises(OktoNexusError) as error:
                _control(uow, wrong, 0)
            assert error.value.details["reason"] == "INPUT_SESSION_CHANGED"
        with pytest.raises(OktoNexusError) as error:
            _control(uow, scope, 0, verify_authority=lambda: "stale-capability")
        assert error.value.details["reason"] == "INPUT_CAPABILITY_CHANGED"

        def deny():
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Fixture control authority was revoked.", {})

        with pytest.raises(OktoNexusError) as error:
            _control(uow, scope, 0, verify_authority=deny)
        assert error.value.code == ErrorCode.PERMISSION_DENIED
        conn = uow.connection
        assert conn.execute("SELECT count(*) FROM session_interaction_queues").fetchone()[0] == 0

        assert _control(uow, scope, 0).paused
        _set_active_lease(uow, scope)
        for paused in (True, False):
            with pytest.raises(OktoNexusError) as error:
                _control(uow, scope, 0, paused=paused)
            assert error.value.details["reason"] == "INPUT_REVISION_CHANGED"
        assert is_input_queue_paused(conn, scope.session)
        assert _control(uow, scope, 1, paused=False) == QueuePauseReceipt(2, None)


def test_pause_revision_limit_and_positive_generation_constraint(database):
    factory, (scope, _) = database
    with factory.unit_of_work() as uow:
        _set_active_lease(uow, scope)
        assert _control(uow, scope, 0).paused
        conn = uow.connection
        conn.execute("UPDATE session_interaction_queues SET revision=?", (MAX_SQLITE_INTEGER,))
        with pytest.raises(OktoNexusError) as error:
            _control(uow, scope, MAX_SQLITE_INTEGER, paused=False)
        assert error.value.details["reason"] == "INPUT_REVISION_LIMIT"
        for malformed in (0, -1, 1.5):
            with pytest.raises(IntegrityError):
                conn.execute("UPDATE session_interaction_queues SET paused_owner_generation=?", (malformed,))
        assert _control(uow, scope, MAX_SQLITE_INTEGER) == QueuePauseReceipt(MAX_SQLITE_INTEGER, 1)
        assert tuple(conn.execute("SELECT next_sequence, paused_owner_generation FROM session_interaction_queues").fetchone()) == (1, 1)
