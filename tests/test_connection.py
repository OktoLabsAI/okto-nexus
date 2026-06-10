"""Behavioral tests for unit-of-work transaction modes and retryable errors.

Covers the M1 concurrency contract of
:mod:`okto_nexus.adapters.outbound.sqlite.connection` and the error taxonomy
additions in :mod:`okto_nexus.errors`:

* ``unit_of_work()`` (default ``write=True``) opens ``BEGIN IMMEDIATE`` - the
  write lock is taken at BEGIN, so concurrent read-then-write scopes serialise
  instead of dying with ``SQLITE_BUSY_SNAPSHOT`` mid-transaction;
* ``unit_of_work(write=False)`` stays a deferred snapshot read that does NOT
  queue behind writers;
* genuine lock contention surfaces as ``DB_ERROR`` with ``retryable=True``,
  propagated into the MCP failure envelope's ``details``.
"""

from __future__ import annotations

import sqlite3
import threading

import pytest

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from okto_nexus.config import NexusConfig
from okto_nexus.envelope import tool_envelope
from okto_nexus.errors import (
    ERROR_CODES,
    ErrorCode,
    OktoNexusError,
    db_error_from_exception,
    is_retryable_db_exception,
)


def make_migrated_factory(tmp_path, **cfg) -> ConnectionFactory:
    factory = ConnectionFactory(NexusConfig(home_dir=tmp_path / "home", **cfg))
    MigrationRunner(factory).apply()
    return factory


# --------------------------------------------------------------------------- #
# Transaction modes
# --------------------------------------------------------------------------- #
def test_concurrent_read_then_write_uows_lose_no_update_and_raise_no_db_error(
    tmp_path,
):
    # THE pre-fix failure mode: two deferred transactions both read, then both
    # write -> the second writer dies with SQLITE_BUSY_SNAPSHOT (which
    # busy_timeout never resolves) or silently loses the update. With the
    # default write=True (BEGIN IMMEDIATE) the scopes serialise at BEGIN:
    # every increment lands, no retry compensation needed.
    factory = make_migrated_factory(tmp_path)
    conn = factory.get_connection()
    try:
        conn.execute("CREATE TABLE counters (id INTEGER PRIMARY KEY, value INTEGER)")
        conn.execute("INSERT INTO counters (id, value) VALUES (1, 0)")
    finally:
        conn.close()

    n = 4
    barrier = threading.Barrier(n)
    errors: list[BaseException] = []
    lock = threading.Lock()

    def bump():
        barrier.wait()
        try:
            with factory.unit_of_work() as uow:  # default write=True
                value = uow.connection.execute(
                    "SELECT value FROM counters WHERE id = 1"
                ).fetchone()[0]
                uow.connection.execute(
                    "UPDATE counters SET value = ? WHERE id = 1", (value + 1,)
                )
        except BaseException as exc:  # noqa: BLE001 - recorded for the assert
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=bump) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    conn = factory.get_connection()
    try:
        final = conn.execute("SELECT value FROM counters WHERE id = 1").fetchone()[0]
    finally:
        conn.close()
    assert final == n  # zero lost updates, zero BUSY_SNAPSHOT casualties


def test_second_writer_gets_retryable_db_error_at_begin(tmp_path):
    # write=True acquires the write lock AT BEGIN: with a 1ms busy_timeout the
    # second writer fails immediately - as a structured, retryable DB_ERROR
    # (never a raw sqlite3 exception leaking through).
    factory = make_migrated_factory(tmp_path, busy_timeout_ms=1)
    with factory.unit_of_work():  # first writer holds the lock from BEGIN
        with pytest.raises(OktoNexusError) as ei:
            with factory.unit_of_work():
                pass  # pragma: no cover - BEGIN itself must raise
    err = ei.value
    assert err.code == ErrorCode.DB_ERROR.value
    assert err.retryable is True
    assert "retry" in err.message.lower()
    assert err.to_error_dict()["details"]["retryable"] is True


def test_read_uow_is_deferred_and_does_not_queue_behind_writers(tmp_path):
    factory = make_migrated_factory(tmp_path, busy_timeout_ms=1)
    with factory.unit_of_work() as seed:
        seed.connection.execute(
            "INSERT INTO workspaces (workspace_id, created_at) VALUES ('w1', 't1')"
        )

    with factory.unit_of_work() as writer:
        writer.connection.execute(
            "INSERT INTO workspaces (workspace_id, created_at) VALUES ('w2', 't2')"
        )
        # While the writer holds the IMMEDIATE lock (and busy_timeout is 1ms,
        # so any lock wait would fail instantly), a read-only UoW still opens
        # and sees the last COMMITTED snapshot - proof it stayed deferred.
        with factory.unit_of_work(write=False) as reader:
            rows = reader.connection.execute(
                "SELECT workspace_id FROM workspaces ORDER BY workspace_id"
            ).fetchall()
            assert [r[0] for r in rows] == ["w1"]


# --------------------------------------------------------------------------- #
# Retryable classification + envelope propagation
# --------------------------------------------------------------------------- #
def test_db_error_helper_classifies_lock_as_retryable():
    locked = sqlite3.OperationalError("database is locked")
    err = db_error_from_exception("claiming handoff", locked)
    assert err.code == ErrorCode.DB_ERROR.value
    assert err.retryable is True
    assert err.details["reason"] == "database is locked"

    # Non-lock OperationalErrors and non-OperationalErrors stay non-retryable.
    schema = db_error_from_exception("reading", sqlite3.OperationalError("no such table: x"))
    assert schema.retryable is False
    assert "retryable" not in (schema.to_error_dict().get("details") or {})
    assert is_retryable_db_exception(ValueError("database is locked")) is False


def test_retryable_flag_reaches_the_mcp_envelope():
    @tool_envelope
    def boom():
        raise db_error_from_exception(
            "writing a row", sqlite3.OperationalError("database is locked")
        )

    env = boom()
    assert env["ok"] is False
    assert env["error"]["code"] == "DB_ERROR"
    assert env["error"]["details"]["retryable"] is True


def test_default_errors_are_not_retryable_and_envelope_is_unchanged():
    err = OktoNexusError(ErrorCode.NOT_FOUND, "nope", {"id": "x"})
    assert err.retryable is False
    assert err.to_error_dict() == {
        "code": "NOT_FOUND",
        "message": "nope",
        "details": {"id": "x"},
    }


@pytest.mark.parametrize(
    "module_name",
    [
        "okto_nexus.adapters.outbound.sqlite.events_repo",
        "okto_nexus.adapters.outbound.sqlite.identity_repo",
        "okto_nexus.adapters.outbound.sqlite.artifacts_repo",
        "okto_nexus.adapters.outbound.sqlite.messages_repo",
        "okto_nexus.adapters.outbound.sqlite.handoff_repo",
    ],
)
def test_every_sqlite_repo_classifies_lock_contention_as_retryable(module_name):
    # Integration gate (wave 1): EVERY sqlite repo funnels its driver failures
    # through the single classification point, so transient lock/busy
    # contention surfaces as a retryable DB_ERROR regardless of which repo the
    # statement ran in - not only in handoff_repo.
    import importlib

    module = importlib.import_module(module_name)
    locked = module._db_error(
        "doing repo work", sqlite3.OperationalError("database is locked")
    )
    assert locked.code == ErrorCode.DB_ERROR.value
    assert locked.retryable is True
    assert locked.to_error_dict()["details"]["retryable"] is True
    assert "retry" in locked.message.lower()

    # Non-transient driver failures in the same repo stay non-retryable.
    broken = module._db_error(
        "doing repo work", sqlite3.OperationalError("no such table: x")
    )
    assert broken.code == ErrorCode.DB_ERROR.value
    assert broken.retryable is False
    assert "retryable" not in (broken.to_error_dict().get("details") or {})


def test_error_catalogue_includes_migrated_code():
    # Reserved for shims of removed/renamed tools (consumed by the tool layer).
    assert ErrorCode.MIGRATED.value == "MIGRATED"
    assert "MIGRATED" in ERROR_CODES
