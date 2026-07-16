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

import json
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


def test_lock_retry_exhausted_raises_actionable_migration_error(tmp_path, monkeypatch):
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


# --------------------------------------------------------------------------- #
# Migration 022 backfill parity (spec 80624c1a, D-MIG) - TS2 / TS3
#
# 022 is forward-only and one-time: it converts the two PRE-existing per-agent
# control axes into the new policy model WITHOUT changing behaviour. We seed the
# schema exactly as it stood before 022 (apply 001..021), insert the old-world
# rows, then apply ONLY 022 on top and assert the conversion.
# --------------------------------------------------------------------------- #
def _partial_migrations_dir(tmp_path, upto: int):
    """A migrations dir holding every real migration file with version <= upto."""
    real_dir = _default_migrations_dir()
    partial = tmp_path / f"partial_{upto}"
    partial.mkdir()
    for f in real_dir.glob("*.sql"):
        if int(f.name.split("_", 1)[0]) <= upto:
            shutil.copy(f, partial)
    return partial


def test_ts2_migration_022_backfills_comm_scope_into_inline_binding(tmp_path):
    """TS2: 022 converts every DETACHED comm_scope into an INLINE binding
    (audience = the old comm_scope verbatim, governance = []), so reachability is
    preserved bit-for-bit; an agent with no comm_scope gets NO binding."""
    from okto_nexus.domain.policy import audience_permits, resolve_effective_sources
    from okto_nexus.domain.tag_selector import scope_selector, selector_matches

    # 1. Bootstrap the schema as it stood BEFORE 022 (migrations 001..021).
    partial = _partial_migrations_dir(tmp_path, 21)
    factory = make_factory(tmp_path)
    assert MigrationRunner(factory, migrations_dir=partial).apply() == list(
        range(1, 22)
    )

    # 2. Seed a pre-022 agent that owns a comm_scope, and one that does not.
    comm_scope = {"outbound": {"team": ["backend"]}, "inbound": {"tier": ["gold"]}}
    conn = factory.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO agents (agent_id, role, created_at, comm_scope) "
            "VALUES (?, ?, ?, ?)",
            ("scoped", "builder", "2026-06-01T00:00:00Z", json.dumps(comm_scope)),
        )
        conn.execute(
            "INSERT INTO agents (agent_id, role, created_at, comm_scope) "
            "VALUES (?, ?, ?, ?)",
            ("plain", "reviewer", "2026-06-01T00:00:00Z", None),
        )
        conn.execute("COMMIT")
    finally:
        conn.close()

    # 3. Apply ONLY migration 022 on top.
    shutil.copy(next(_default_migrations_dir().glob("022_*.sql")), partial)
    assert MigrationRunner(factory, migrations_dir=partial).apply() == [22]

    # 4. The scoped agent gained EXACTLY one inline binding at position 0; the
    #    unrestricted agent gained none.
    conn = factory.get_connection()
    try:
        rows = conn.execute(
            "SELECT position, source, policy_id, mode, pinned_version, audience, "
            "governance FROM agent_policy_bindings WHERE agent_id = 'scoped' "
            "ORDER BY position"
        ).fetchall()
        plain_count = conn.execute(
            "SELECT COUNT(*) FROM agent_policy_bindings WHERE agent_id = 'plain'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert len(rows) == 1
    row = rows[0]
    assert row["position"] == 0
    assert row["source"] == "inline"
    assert row["policy_id"] is None and row["mode"] is None
    assert row["pinned_version"] is None
    assert json.loads(row["audience"]) == comm_scope  # audience = old comm_scope
    assert row["governance"] == "[]"  # governance defaults empty
    assert plain_count == 0  # no comm_scope -> no binding (unchanged)

    # 5. Reachability parity: the migrated inline source evaluates BIT-FOR-BIT
    #    like the raw comm_scope through the real matchers - only the store moved.
    sources = resolve_effective_sources(
        [
            {
                "source": "inline",
                "audience": json.loads(row["audience"]),
                "governance": [],
            }
        ],
        {},
    )
    for tags in ({"team": ["backend"]}, {"team": ["frontend"]}, {}):
        pre = selector_matches(scope_selector(comm_scope, "outbound"), tags)
        assert audience_permits(sources, "outbound", tags) == pre
    for tags in ({"tier": ["gold"]}, {"tier": ["silver"]}, {}):
        pre = selector_matches(scope_selector(comm_scope, "inbound"), tags)
        assert audience_permits(sources, "inbound", tags) == pre


def test_ts3_migration_022_converts_governance_policies_to_detached_globals(tmp_path):
    """TS3: 022 converts each existing governance_policy into a DETACHED,
    governance-only global policy (catalog row + immutable v1) with NO binding -
    so nothing becomes enforced (feature_governance was OFF; a binding would be a
    regression)."""
    partial = _partial_migrations_dir(tmp_path, 21)
    factory = make_factory(tmp_path)
    assert MigrationRunner(factory, migrations_dir=partial).apply() == list(
        range(1, 22)
    )

    # Seed two pre-022 governance policies: a categorical deny and a windowed
    # quota (to prove limit_value + window fold through verbatim).
    conn = factory.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO governance_policies (policy_id, subject_kind, "
            "subject_value, action, limit_kind, limit_value, time_window, "
            "enabled, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "pol_deny",
                "role",
                "reviewer",
                "message_create",
                "deny",
                None,
                None,
                1,
                "2026-06-01T00:00:00Z",
            ),
        )
        conn.execute(
            "INSERT INTO governance_policies (policy_id, subject_kind, "
            "subject_value, action, limit_kind, limit_value, time_window, "
            "enabled, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "pol_quota",
                "star",
                None,
                "broadcast",
                "max_count",
                5,
                "1h",
                1,
                "2026-06-01T00:00:00Z",
            ),
        )
        conn.execute("COMMIT")
    finally:
        conn.close()

    shutil.copy(next(_default_migrations_dir().glob("022_*.sql")), partial)
    assert MigrationRunner(factory, migrations_dir=partial).apply() == [22]

    conn = factory.get_connection()
    try:
        deny_pol = conn.execute(
            "SELECT name, description FROM policies WHERE policy_id = 'pol_deny'"
        ).fetchone()
        deny_v = conn.execute(
            "SELECT version, audience, governance FROM policy_versions "
            "WHERE policy_id = 'pol_deny'"
        ).fetchall()
        quota_v = conn.execute(
            "SELECT version, governance FROM policy_versions "
            "WHERE policy_id = 'pol_quota'"
        ).fetchall()
        bound = conn.execute(
            "SELECT COUNT(*) FROM agent_policy_bindings "
            "WHERE policy_id IN ('pol_deny', 'pol_quota')"
        ).fetchone()[0]
    finally:
        conn.close()

    # A NAMED global policy: the name folds in the old subject clause; the
    # description declares it DETACHED.
    assert deny_pol is not None
    assert "migrated role:reviewer message_create/deny" in deny_pol["name"]
    assert "DETACHED" in (deny_pol["description"] or "")
    # A single immutable v1 body: audience NULL (governance-only), the rule
    # SUBJECT-LESS (the binding is the subject).
    assert len(deny_v) == 1 and deny_v[0]["version"] == 1
    assert deny_v[0]["audience"] is None
    assert json.loads(deny_v[0]["governance"]) == [
        {
            "action": "message_create",
            "limit_kind": "deny",
            "limit_value": None,
            "window": None,
        }
    ]
    # The quota policy folds limit_value + window through verbatim.
    assert len(quota_v) == 1
    assert json.loads(quota_v[0]["governance"]) == [
        {
            "action": "broadcast",
            "limit_kind": "max_count",
            "limit_value": 5,
            "window": "1h",
        }
    ]
    # CRUCIALLY no binding is created -> nothing is enforced (unenforced state
    # preserved); the operator re-attaches consciously later.
    assert bound == 0
