"""Behavioral tests for the migration runner's concurrency and durability.

Covers the M1 hardening of :mod:`okto_nexus.adapters.outbound.sqlite.migrations`:

* per-migration ``BEGIN IMMEDIATE`` transactions (a failing migration rolls
  back ONLY itself; earlier ones stay committed);
* concurrent bootstrap (N processes/threads racing ``apply()``) applies each
  version exactly once, with a short lock-retry instead of an opaque failure;
* the FAIL-CLOSED guard: a ledger recording a version newer than the code
  knows aborts with a prescriptive ``MIGRATION_ERROR`` (update the package)
  and applies NOTHING.
"""

from __future__ import annotations

import shutil
import threading
import time

import pytest

from okto_nexus.adapters.outbound.sqlite import migrations as migrations_module
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import (
    MigrationRunner,
    _default_migrations_dir,
)
from okto_nexus.config import NexusConfig
from okto_nexus.errors import ErrorCode, OktoNexusError


def make_factory(tmp_path, name: str = "home", **cfg) -> ConnectionFactory:
    return ConnectionFactory(NexusConfig(home_dir=tmp_path / name, **cfg))


def ledger_versions(factory: ConnectionFactory) -> list[int]:
    conn = factory.get_connection()
    try:
        rows = conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def table_names(factory: ConnectionFactory) -> set[str]:
    conn = factory.get_connection()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


def insert_ledger_row(factory: ConnectionFactory, version: int) -> None:
    conn = factory.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, "2026-06-09T00:00:00Z"),
        )
        conn.execute("COMMIT")
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Fail-closed guard: ledger ahead of the code
# --------------------------------------------------------------------------- #
def test_unknown_ledger_version_fails_closed_before_applying_anything(tmp_path):
    # Bootstrap ONLY migration 001 (copy of the real file), then record a
    # version far beyond what the code ships. The full runner must refuse to
    # run - and must NOT apply the pending 002..N first.
    real_dir = _default_migrations_dir()
    partial = tmp_path / "partial"
    partial.mkdir()
    shutil.copy(next(real_dir.glob("001_*.sql")), partial)

    factory = make_factory(tmp_path)
    assert MigrationRunner(factory, migrations_dir=partial).apply() == [1]
    insert_ledger_row(factory, 999)

    with pytest.raises(OktoNexusError) as ei:
        MigrationRunner(factory).apply()
    err = ei.value
    assert err.code == ErrorCode.MIGRATION_ERROR.value
    assert err.details["max_applied_version"] == 999
    assert err.details["max_known_version"] >= 5
    # Prescriptive: the operator is told to update the package.
    assert "update the okto-nexus package" in err.message.lower()
    # Nothing was applied: the ledger still holds exactly {1, 999}.
    assert ledger_versions(factory) == [1, 999]


# --------------------------------------------------------------------------- #
# Per-migration transactions: durability of earlier migrations
# --------------------------------------------------------------------------- #
def test_failed_migration_rolls_back_only_itself(tmp_path):
    migs = tmp_path / "migs"
    migs.mkdir()
    (migs / "001_alpha.sql").write_text(
        "CREATE TABLE alpha (id INTEGER PRIMARY KEY);\n", encoding="utf-8"
    )
    (migs / "002_bad.sql").write_text(
        "CREATE TABLE beta (id INTEGER PRIMARY KEY);\n"
        "INSERT INTO no_such_table VALUES (1);\n",
        encoding="utf-8",
    )
    factory = make_factory(tmp_path)
    runner = MigrationRunner(factory, migrations_dir=migs)

    with pytest.raises(OktoNexusError) as ei:
        runner.apply()
    err = ei.value
    assert err.code == ErrorCode.MIGRATION_ERROR.value
    # The error pinpoints the failing migration.
    assert err.details["version"] == 2
    assert err.details["file"] == "002_bad.sql"

    # Migration 1 stayed committed; migration 2 rolled back atomically.
    assert "alpha" in table_names(factory)
    assert "beta" not in table_names(factory)
    assert ledger_versions(factory) == [1]

    # Fixing the bad file resumes from exactly where it stopped.
    (migs / "002_bad.sql").write_text(
        "CREATE TABLE beta (id INTEGER PRIMARY KEY);\n", encoding="utf-8"
    )
    assert runner.apply() == [2]
    assert "beta" in table_names(factory)
    assert ledger_versions(factory) == [1, 2]


# --------------------------------------------------------------------------- #
# Concurrent bootstrap
# --------------------------------------------------------------------------- #
def test_concurrent_bootstrap_applies_each_migration_exactly_once(tmp_path):
    config = NexusConfig(home_dir=tmp_path / "home")
    racers = 4
    barrier = threading.Barrier(racers)
    results: list[list[int]] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker():
        factory = ConnectionFactory(config)
        runner = MigrationRunner(factory)
        barrier.wait()
        try:
            applied = runner.apply()
            with lock:
                results.append(applied)
        except BaseException as exc:  # noqa: BLE001 - recorded for the assert
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(racers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    factory = ConnectionFactory(config)
    ledger = ledger_versions(factory)
    assert len(ledger) == len(set(ledger)) and ledger  # unique versions
    # Each version was applied by exactly ONE racer; the union is the full set.
    applied_by_racers = sorted(v for r in results for v in r)
    assert applied_by_racers == ledger
    # The schema is actually usable afterwards.
    assert {"workspaces", "handoffs", "events"} <= table_names(factory)
    # And a follow-up apply is a no-op.
    assert MigrationRunner(factory).apply() == []


def test_bootstrap_retries_while_another_process_holds_the_lock(tmp_path):
    # busy_timeout is dropped to 1ms so BEGIN IMMEDIATE fails fast and the
    # runner's own retry loop (not busy_timeout) must absorb the contention.
    factory = make_factory(tmp_path, busy_timeout_ms=1)
    locked = threading.Event()

    def hold_lock_briefly():
        conn = factory.get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")  # simulates a process mid-migration
            locked.set()
            time.sleep(0.35)
            conn.execute("COMMIT")
        finally:
            conn.close()

    holder = threading.Thread(target=hold_lock_briefly)
    holder.start()
    assert locked.wait(5)
    try:
        applied = MigrationRunner(factory).apply()
    finally:
        holder.join()
    # The bootstrap succeeded despite the held lock (retry, not failure).
    assert 1 in applied
    assert "handoffs" in table_names(factory)


def test_lock_retry_exhausted_raises_actionable_migration_error(
    tmp_path, monkeypatch
):
    # Shrink the retry budget so the test stays fast, then never release the
    # lock: the runner must give up with a prescriptive MIGRATION_ERROR.
    monkeypatch.setattr(migrations_module, "_LOCK_RETRY_ATTEMPTS", 2)
    monkeypatch.setattr(migrations_module, "_LOCK_RETRY_SLEEP_SECONDS", 0.01)
    factory = make_factory(tmp_path, busy_timeout_ms=1)
    locked = threading.Event()
    release = threading.Event()

    def hold_lock_until_released():
        conn = factory.get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            locked.set()
            release.wait(10)
            conn.execute("ROLLBACK")
        finally:
            conn.close()

    holder = threading.Thread(target=hold_lock_until_released)
    holder.start()
    assert locked.wait(5)
    try:
        with pytest.raises(OktoNexusError) as ei:
            MigrationRunner(factory).apply()
    finally:
        release.set()
        holder.join()
    err = ei.value
    assert err.code == ErrorCode.MIGRATION_ERROR.value
    assert "migration lock" in err.message.lower()
    assert "retry" in err.message.lower()
