"""Tests for the retention slice (M7): prune windows, protected lanes, batching,
dry-run, the ``admin prune`` CLI, ``--vacuum`` and the ``auto_prune_on_start``
opportunistic reaper.

Every test asserts the OBSERVABLE effect on the store (rows present/absent via
SQL counts, report fields, exit codes) - never the implementation source. The
hard invariants under test:

* windows respected per table (events 30d / read deliveries 14d / closed
  sessions 7d by default, overridable per call and via config);
* protected lanes are NEVER deleted, even with 0-day windows: unread /
  delivered / parked deliveries, active sessions, and every handoff/message;
* ``dry_run`` counts without deleting; ``--vacuum`` compacts the file;
* deletes happen in bounded batches and ``max_batches`` caps the work
  (the cheap incremental reaper used by ``auto_prune_on_start``).
"""

from __future__ import annotations

import io
import json
import os

import pytest

from okto_nexus.adapters.inbound.cli.admin import run_admin
from okto_nexus.adapters.inbound.mcp import server as server_module
from okto_nexus.adapters.inbound.mcp.server import bootstrap, main, maybe_auto_prune
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.events_repo import SqliteEventRepo
from okto_nexus.adapters.outbound.sqlite.handoff_repo import SqliteHandoffRepo
from okto_nexus.adapters.outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteSessionRepo,
    SqliteWorkspaceRepo,
)
from okto_nexus.adapters.outbound.sqlite.messages_repo import (
    SqliteMessageDeliveryRepo,
    SqliteMessageRepo,
)
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from okto_nexus.application.retention import RetentionService
from okto_nexus.config import NexusConfig, load_config
from okto_nexus.domain.base import iso_plus, utc_now_iso
from okto_nexus.domain.ids import resolve_workspace_id
from okto_nexus.errors import ErrorCode, OktoNexusError

from conftest import FakeClock

#: The deterministic "now" every service-level test prunes at (canonical form).
NOW = "2026-06-07T00:00:00.000000Z"

#: A messages window so wide the messages reaper (D-EMB-6) is a no-op: the
#: pre-existing reaper tests below exercise the events/deliveries/sessions
#: windows in ISOLATION, so they hold messages out of scope explicitly. The
#: message reaper has its own dedicated tests (test_embeddings.py).
MESSAGES_HELD = 36500


def days_ago(days: float, base: str = NOW) -> str:
    return iso_plus(base, -days * 86400.0)


# --------------------------------------------------------------------------- #
# Seeding helpers (real repos over the migrated store)
# --------------------------------------------------------------------------- #
def seed_workspace(factory, tmp_path, name="P") -> tuple[str, str]:
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    ws = resolve_workspace_id(str(d))
    with factory.unit_of_work() as uow:
        SqliteWorkspaceRepo(FakeClock()).upsert(
            uow, workspace_id=ws, root_realpath=os.path.realpath(str(d))
        )
    return str(d), ws


def seed_agent(factory, agent_id: str) -> None:
    with factory.unit_of_work() as uow:
        SqliteAgentRepo(FakeClock()).upsert(uow, agent_id=agent_id)


def seed_event(factory, ws: str, *, created_at: str, type: str = "evt") -> int:
    clock = FakeClock(iso=created_at)
    with factory.unit_of_work() as uow:
        return SqliteEventRepo(clock).append(
            uow, workspace_id=ws, stream="workspace", type=type
        )


def seed_events_bulk(factory, ws: str, *, created_at: str, count: int) -> None:
    """Insert ``count`` events in ONE transaction (fast bulk seeding)."""
    repo = SqliteEventRepo(FakeClock(iso=created_at))
    with factory.unit_of_work() as uow:
        for i in range(count):
            repo.append(uow, workspace_id=ws, stream="workspace", type=f"bulk{i}")


def seed_delivery(
    factory,
    ws: str,
    *,
    delivery_id: str,
    status: str,
    created_at: str,
    read_at: str | None = None,
) -> None:
    """One message + one delivery row in the given lane, timestamped as asked."""
    with factory.unit_of_work() as uow:
        SqliteMessageRepo(FakeClock()).create(
            uow,
            message_id=f"msg_{delivery_id}",
            workspace_id=ws,
            from_agent_id="sender",
            created_at=created_at,
        )
        SqliteMessageDeliveryRepo(FakeClock()).create(
            uow,
            delivery_id=delivery_id,
            message_id=f"msg_{delivery_id}",
            recipient_agent_id="recipient",
            status="unread",
            created_at=created_at,
        )
        # Drive the row into the target lane (status machine is exercised by
        # the inbox tests; here only the LANE + timestamps matter for prune).
        uow.connection.execute(
            "UPDATE message_deliveries SET status = ?, read_at = ? "
            "WHERE delivery_id = ?",
            (status, read_at, delivery_id),
        )


def seed_session(
    factory,
    ws: str,
    *,
    session_id: str,
    status: str,
    started_at: str,
    closed_at: str | None = None,
) -> None:
    repo = SqliteSessionRepo(FakeClock())
    with factory.unit_of_work() as uow:
        repo.create(
            uow,
            session_id=session_id,
            agent_id="recipient",
            workspace_id=ws,
            status="active",
            started_at=started_at,
        )
        if status == "closed":
            repo.close(uow, session_id=session_id, at=closed_at or started_at)
        elif status != "active":
            uow.connection.execute(
                "UPDATE sessions SET status = ? WHERE session_id = ?",
                (status, session_id),
            )


def seed_handoff(factory, ws: str, *, handoff_id: str, status: str, created_at: str):
    with factory.unit_of_work() as uow:
        SqliteHandoffRepo(FakeClock()).create(
            uow,
            handoff_id=handoff_id,
            workspace_id=ws,
            status=status,
            created_at=created_at,
        )


def count_rows(factory, table: str, where: str = "", params: tuple = ()) -> int:
    conn = factory.get_connection()
    try:
        sql = f"SELECT COUNT(*) FROM {table}"
        if where:
            sql += f" WHERE {where}"
        return int(conn.execute(sql, params).fetchone()[0])
    finally:
        conn.close()


def ids_in(factory, table: str, id_col: str) -> set[str]:
    conn = factory.get_connection()
    try:
        rows = conn.execute(f"SELECT {id_col} FROM {table}").fetchall()
        return {str(r[0]) for r in rows}
    finally:
        conn.close()


def make_service(factory, tmp_path, *, config: NexusConfig | None = None, **kwargs):
    return RetentionService(
        connection_factory=factory,
        clock=FakeClock(iso=NOW),
        config=config or NexusConfig(home_dir=tmp_path / "okto_home"),
        events=SqliteEventRepo(FakeClock(iso=NOW)),
        deliveries=SqliteMessageDeliveryRepo(FakeClock(iso=NOW)),
        sessions=SqliteSessionRepo(FakeClock(iso=NOW)),
        messages=SqliteMessageRepo(FakeClock(iso=NOW)),
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# Windows are respected per table
# --------------------------------------------------------------------------- #
def test_prune_deletes_events_past_window_and_keeps_recent(
    migrated_factory, tmp_path
):
    _, ws = seed_workspace(migrated_factory, tmp_path)
    old_id = seed_event(migrated_factory, ws, created_at=days_ago(40), type="old")
    fresh_id = seed_event(migrated_factory, ws, created_at=days_ago(5), type="fresh")

    report = make_service(migrated_factory, tmp_path).prune()  # default 30d

    assert report["tables"]["events"] == {"deleted": 1, "complete": True}
    assert report["total_deleted"] == 1
    remaining = ids_in(migrated_factory, "events", "event_id")
    assert remaining == {str(fresh_id)}
    assert str(old_id) not in remaining


def test_prune_deletes_old_read_deliveries_and_keeps_recent_read(
    migrated_factory, tmp_path
):
    _, ws = seed_workspace(migrated_factory, tmp_path)
    seed_agent(migrated_factory, "recipient")
    seed_delivery(
        migrated_factory, ws, delivery_id="d_read_old", status="read",
        created_at=days_ago(60), read_at=days_ago(20),
    )
    seed_delivery(
        migrated_factory, ws, delivery_id="d_read_fresh", status="read",
        created_at=days_ago(60), read_at=days_ago(2),
    )

    # Hold messages out of scope: this test isolates the read-deliveries window.
    report = make_service(migrated_factory, tmp_path).prune(
        messages_keep_days=MESSAGES_HELD
    )  # default 14d for read deliveries

    assert report["tables"]["message_deliveries"] == {"deleted": 1, "complete": True}
    assert ids_in(migrated_factory, "message_deliveries", "delivery_id") == {
        "d_read_fresh"
    }


def test_prune_deletes_old_closed_sessions_keeps_recent_closed_and_active(
    migrated_factory, tmp_path
):
    _, ws = seed_workspace(migrated_factory, tmp_path)
    seed_agent(migrated_factory, "recipient")
    seed_session(
        migrated_factory, ws, session_id="s_closed_old", status="closed",
        started_at=days_ago(400), closed_at=days_ago(10),
    )
    seed_session(
        migrated_factory, ws, session_id="s_closed_fresh", status="closed",
        started_at=days_ago(400), closed_at=days_ago(2),
    )
    seed_session(
        migrated_factory, ws, session_id="s_active_ancient", status="active",
        started_at=days_ago(400),
    )

    report = make_service(migrated_factory, tmp_path).prune()  # default 7d

    assert report["tables"]["sessions"] == {"deleted": 1, "complete": True}
    assert ids_in(migrated_factory, "sessions", "session_id") == {
        "s_closed_fresh",
        "s_active_ancient",
    }


# --------------------------------------------------------------------------- #
# Protected lanes: NEVER deleted, even with zero-day windows
# --------------------------------------------------------------------------- #
def test_prune_never_deletes_unread_delivered_or_parked_deliveries(
    migrated_factory, tmp_path
):
    _, ws = seed_workspace(migrated_factory, tmp_path)
    seed_agent(migrated_factory, "recipient")
    for lane in ("unread", "delivered", "parked"):
        seed_delivery(
            migrated_factory, ws, delivery_id=f"d_{lane}_ancient", status=lane,
            created_at=days_ago(500),
        )
    seed_delivery(
        migrated_factory, ws, delivery_id="d_read_ancient", status="read",
        created_at=days_ago(500), read_at=days_ago(500),
    )

    # Most aggressive possible windows: everything older than NOW is eligible.
    # Messages held out (MESSAGES_HELD) so the message reaper does not cascade
    # into these deliveries - this test isolates the DELIVERY lane protection.
    report = make_service(migrated_factory, tmp_path).prune(
        events_keep_days=0, read_deliveries_keep_days=0, closed_sessions_keep_days=0,
        messages_keep_days=MESSAGES_HELD,
    )

    # Only the read row went; every protected lane survived 500 days of age.
    assert report["tables"]["message_deliveries"]["deleted"] == 1
    assert ids_in(migrated_factory, "message_deliveries", "delivery_id") == {
        "d_unread_ancient",
        "d_delivered_ancient",
        "d_parked_ancient",
    }


def test_prune_never_touches_handoffs_messages_or_open_sessions(
    migrated_factory, tmp_path
):
    _, ws = seed_workspace(migrated_factory, tmp_path)
    seed_agent(migrated_factory, "recipient")
    seed_handoff(
        migrated_factory, ws, handoff_id="h_open", status="OPEN",
        created_at=days_ago(500),
    )
    seed_handoff(
        migrated_factory, ws, handoff_id="h_done", status="COMPLETED",
        created_at=days_ago(500),
    )
    with migrated_factory.unit_of_work() as uow:
        SqliteMessageRepo(FakeClock()).create(
            uow, message_id="m_ancient", workspace_id=ws,
            from_agent_id="sender", created_at=days_ago(500),
        )
    seed_session(
        migrated_factory, ws, session_id="s_stale", status="stale",
        started_at=days_ago(500),
    )

    # Messages held out (this test asserts handoffs/open-sessions are never
    # touched; message age-out has its own coverage in test_embeddings.py).
    make_service(migrated_factory, tmp_path).prune(
        events_keep_days=0, read_deliveries_keep_days=0, closed_sessions_keep_days=0,
        messages_keep_days=MESSAGES_HELD,
    )

    assert ids_in(migrated_factory, "handoffs", "handoff_id") == {"h_open", "h_done"}
    assert count_rows(migrated_factory, "messages") == 1
    assert ids_in(migrated_factory, "sessions", "session_id") == {"s_stale"}


# --------------------------------------------------------------------------- #
# dry_run, config defaults, batching, validation
# --------------------------------------------------------------------------- #
def test_prune_dry_run_counts_without_deleting(migrated_factory, tmp_path):
    _, ws = seed_workspace(migrated_factory, tmp_path)
    seed_agent(migrated_factory, "recipient")
    seed_event(migrated_factory, ws, created_at=days_ago(40))
    seed_event(migrated_factory, ws, created_at=days_ago(35))
    seed_delivery(
        migrated_factory, ws, delivery_id="d_read_old", status="read",
        created_at=days_ago(60), read_at=days_ago(20),
    )

    report = make_service(migrated_factory, tmp_path).prune(
        dry_run=True, vacuum=True, messages_keep_days=MESSAGES_HELD
    )

    assert report["dry_run"] is True
    assert report["tables"]["events"] == {"deleted": 2, "complete": True}
    assert report["tables"]["message_deliveries"]["deleted"] == 1
    assert report["total_deleted"] == 3
    # Nothing actually left the store, and vacuum was explicitly skipped.
    assert count_rows(migrated_factory, "events") == 2
    assert count_rows(migrated_factory, "message_deliveries") == 1
    assert report["vacuum"]["ran"] is False
    assert "dry_run" in report["vacuum"]["skipped_reason"]


def test_prune_uses_config_windows_when_args_omitted(migrated_factory, tmp_path):
    _, ws = seed_workspace(migrated_factory, tmp_path)
    seed_event(migrated_factory, ws, created_at=days_ago(40))

    generous = NexusConfig(
        home_dir=tmp_path / "okto_home", retention_events_keep_days=1000
    )
    report = make_service(migrated_factory, tmp_path, config=generous).prune()
    assert report["windows_days"]["events"] == 1000
    assert report["tables"]["events"]["deleted"] == 0
    assert count_rows(migrated_factory, "events") == 1

    # An explicit override beats the config default.
    report = make_service(migrated_factory, tmp_path, config=generous).prune(
        events_keep_days=10
    )
    assert report["tables"]["events"]["deleted"] == 1
    assert count_rows(migrated_factory, "events") == 0


def test_prune_batches_drain_fully_and_max_batches_caps_work(
    migrated_factory, tmp_path
):
    _, ws = seed_workspace(migrated_factory, tmp_path)
    seed_events_bulk(migrated_factory, ws, created_at=days_ago(40), count=12)
    seed_event(migrated_factory, ws, created_at=days_ago(1), type="fresh")

    svc = make_service(migrated_factory, tmp_path, batch_size=5)

    # Budget of 1 batch: exactly batch_size rows go, backlog remains.
    report = svc.prune(max_batches=1)
    assert report["tables"]["events"] == {"deleted": 5, "complete": False}
    assert count_rows(migrated_factory, "events") == 8  # 7 old + 1 fresh

    # Unbudgeted run drains the remaining backlog and reports completion.
    report = svc.prune()
    assert report["tables"]["events"] == {"deleted": 7, "complete": True}
    assert count_rows(migrated_factory, "events") == 1  # only the fresh one


@pytest.mark.parametrize(
    "kwargs",
    [
        {"events_keep_days": -1},
        {"events_keep_days": True},
        {"read_deliveries_keep_days": "14"},
        {"closed_sessions_keep_days": -7},
        {"max_batches": 0},
        {"max_batches": True},
    ],
)
def test_prune_rejects_malformed_inputs_fail_closed(
    migrated_factory, tmp_path, kwargs
):
    _, ws = seed_workspace(migrated_factory, tmp_path)
    seed_event(migrated_factory, ws, created_at=days_ago(40))
    with pytest.raises(OktoNexusError) as ei:
        make_service(migrated_factory, tmp_path).prune(**kwargs)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert count_rows(migrated_factory, "events") == 1  # nothing was deleted


# --------------------------------------------------------------------------- #
# Config: retention section + auto_prune_on_start (fail-closed parsing)
# --------------------------------------------------------------------------- #
def test_config_retention_defaults():
    config = load_config({}, [])
    assert config.retention_events_keep_days == 30
    assert config.retention_read_deliveries_keep_days == 14
    assert config.retention_closed_sessions_keep_days == 7
    assert config.auto_prune_on_start is False


def test_config_retention_env_and_cli_precedence():
    env = {
        "OKTO_NEXUS_RETENTION_EVENTS_KEEP_DAYS": "10",
        "OKTO_NEXUS_RETENTION_READ_DELIVERIES_KEEP_DAYS": "9",
        "OKTO_NEXUS_RETENTION_CLOSED_SESSIONS_KEEP_DAYS": "8",
        "OKTO_NEXUS_AUTO_PRUNE_ON_START": "true",
    }
    config = load_config(env, [])
    assert config.retention_events_keep_days == 10
    assert config.retention_read_deliveries_keep_days == 9
    assert config.retention_closed_sessions_keep_days == 8
    assert config.auto_prune_on_start is True

    config = load_config(
        env,
        [
            "--retention-events-keep-days", "5",
            "--auto-prune-on-start", "false",
        ],
    )
    assert config.retention_events_keep_days == 5  # CLI beats env
    assert config.auto_prune_on_start is False


@pytest.mark.parametrize(
    "env",
    [
        {"OKTO_NEXUS_RETENTION_EVENTS_KEEP_DAYS": "-1"},
        {"OKTO_NEXUS_RETENTION_EVENTS_KEEP_DAYS": "soon"},
        {"OKTO_NEXUS_AUTO_PRUNE_ON_START": "sim"},
    ],
)
def test_config_retention_invalid_values_fail_closed(env):
    with pytest.raises(OktoNexusError) as ei:
        load_config(env, [])
    assert ei.value.code == ErrorCode.CONFIG_ERROR.value


# --------------------------------------------------------------------------- #
# CLI: okto-nexus admin prune (real bootstrap end-to-end)
# --------------------------------------------------------------------------- #
def _bootstrap_store(tmp_path) -> tuple[ConnectionFactory, str, str, str, str]:
    """Migrated store under tmp_path + a workspace, seeded relative to REAL now
    (the CLI/bootstrap path prunes with the system clock)."""
    home = tmp_path / "home"
    factory = ConnectionFactory(NexusConfig(home_dir=home))
    MigrationRunner(factory).apply()
    now = utc_now_iso()
    proj, ws = seed_workspace(factory, tmp_path, name="proj")
    return factory, str(home), proj, ws, now


def test_admin_prune_cli_deletes_and_prints_report(tmp_path):
    factory, home, proj, ws, now = _bootstrap_store(tmp_path)
    seed_event(factory, ws, created_at=days_ago(40, now), type="old")
    seed_event(factory, ws, created_at=days_ago(1, now), type="fresh")

    out = io.StringIO()
    code = run_admin(
        ["prune", "--project-root", proj, "--home", home],
        env={},
        out=out,
    )

    assert code == 0
    report = json.loads(out.getvalue())
    assert report["dry_run"] is False
    assert report["tables"]["events"] == {"deleted": 1, "complete": True}
    assert report["windows_days"] == {
        "events": 30, "read_deliveries": 14, "closed_sessions": 7, "messages": 30,
    }
    assert count_rows(factory, "events") == 1  # only the fresh event remains


def test_admin_prune_cli_dry_run_deletes_nothing(tmp_path):
    factory, home, proj, ws, now = _bootstrap_store(tmp_path)
    seed_event(factory, ws, created_at=days_ago(40, now))

    out = io.StringIO()
    code = run_admin(
        ["prune", "--project-root", proj, "--home", home, "--dry-run"],
        env={},
        out=out,
    )

    assert code == 0
    report = json.loads(out.getvalue())
    assert report["dry_run"] is True
    assert report["tables"]["events"]["deleted"] == 1  # WOULD be deleted
    assert count_rows(factory, "events") == 1  # ... but still present


def test_admin_prune_cli_window_override_flags(tmp_path):
    factory, home, proj, ws, now = _bootstrap_store(tmp_path)
    seed_event(factory, ws, created_at=days_ago(5, now))

    out = io.StringIO()
    code = run_admin(
        [
            "prune", "--project-root", proj, "--home", home,
            "--events-keep-days", "2",
        ],
        env={},
        out=out,
    )

    assert code == 0
    report = json.loads(out.getvalue())
    assert report["windows_days"]["events"] == 2
    assert count_rows(factory, "events") == 0  # 5-day-old event fell to the 2d window


def test_admin_prune_cli_vacuum_compacts_freed_pages(tmp_path):
    factory, home, proj, ws, now = _bootstrap_store(tmp_path)
    # Bulky old events so the prune frees whole pages inside the file.
    repo = SqliteEventRepo(FakeClock(iso=days_ago(40, now)))
    with factory.unit_of_work() as uow:
        for i in range(300):
            repo.append(
                uow, workspace_id=ws, stream="workspace", type="bulk",
                payload={"i": i, "blob": "x" * 1024},
            )

    # Prune WITHOUT vacuum: rows go, but freed pages stay inside the file.
    code = run_admin(
        ["prune", "--project-root", proj, "--home", home],
        env={}, out=io.StringIO(),
    )
    assert code == 0
    conn = factory.get_connection()
    try:
        assert int(conn.execute("PRAGMA freelist_count").fetchone()[0]) > 0
    finally:
        conn.close()

    # Second pass WITH --vacuum: the freelist is compacted away.
    out = io.StringIO()
    code = run_admin(
        ["prune", "--project-root", proj, "--home", home, "--vacuum"],
        env={}, out=out,
    )
    assert code == 0
    report = json.loads(out.getvalue())
    assert report["vacuum"] == {"requested": True, "ran": True, "skipped_reason": None}
    conn = factory.get_connection()
    try:
        assert int(conn.execute("PRAGMA freelist_count").fetchone()[0]) == 0
    finally:
        conn.close()


def test_admin_prune_cli_bad_project_root_exits_one(tmp_path, capsys):
    _, home, _, _, _ = _bootstrap_store(tmp_path)
    missing = str(tmp_path / "does_not_exist" / "child")
    code = run_admin(
        ["prune", "--project-root", missing, "--home", home],
        env={},
        out=io.StringIO(),
    )
    assert code == 1
    assert "WORKSPACE_UNRESOLVED" in capsys.readouterr().err


def test_main_dispatches_admin_prune_subcommand(tmp_path, capsys):
    factory, home, proj, ws, now = _bootstrap_store(tmp_path)
    seed_event(factory, ws, created_at=days_ago(40, now))

    code = main(["admin", "prune", "--project-root", proj, "--home", home])

    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["tables"]["events"]["deleted"] == 1
    assert count_rows(factory, "events") == 0


# --------------------------------------------------------------------------- #
# auto_prune_on_start: the opportunistic, bounded startup reaper
# --------------------------------------------------------------------------- #
def test_maybe_auto_prune_disabled_by_default_deletes_nothing(tmp_path):
    factory, home, proj, ws, now = _bootstrap_store(tmp_path)
    seed_event(factory, ws, created_at=days_ago(40, now))

    deps = bootstrap({}, ["--home", home])
    assert maybe_auto_prune(deps) is None
    assert count_rows(factory, "events") == 1  # untouched


def test_maybe_auto_prune_enabled_prunes_with_configured_windows(tmp_path, capsys):
    factory, home, proj, ws, now = _bootstrap_store(tmp_path)
    seed_event(factory, ws, created_at=days_ago(40, now), type="old")
    seed_event(factory, ws, created_at=days_ago(1, now), type="fresh")

    deps = bootstrap({}, ["--home", home, "--auto-prune-on-start", "true"])
    report = maybe_auto_prune(deps)

    assert report is not None and report["total_deleted"] == 1
    assert count_rows(factory, "events") == 1  # the fresh event survived
    assert "auto-prune deleted 1 row(s)" in capsys.readouterr().err


def test_maybe_auto_prune_is_bounded_not_a_full_drain(tmp_path):
    # The startup reaper is INCREMENTAL: per table it deletes at most
    # AUTO_PRUNE_MAX_BATCHES * batch_size rows (4 * 500 = 2000) per start,
    # leaving the rest for later starts or an explicit `admin prune`.
    factory, home, proj, ws, now = _bootstrap_store(tmp_path)
    seed_events_bulk(factory, ws, created_at=days_ago(40, now), count=2100)

    deps = bootstrap({}, ["--home", home, "--auto-prune-on-start", "true"])
    report = maybe_auto_prune(deps)

    assert report is not None
    assert report["tables"]["events"] == {"deleted": 2000, "complete": False}
    assert count_rows(factory, "events") == 100  # bounded backlog remains

    # A second start keeps converging.
    report = maybe_auto_prune(deps)
    assert report["tables"]["events"] == {"deleted": 100, "complete": True}
    assert count_rows(factory, "events") == 0


def test_main_runs_auto_prune_before_serving(tmp_path, monkeypatch):
    factory, home, proj, ws, now = _bootstrap_store(tmp_path)
    seed_event(factory, ws, created_at=days_ago(40, now), type="old")

    class _StubServer:
        def run(self) -> None:  # the real stdio loop would block forever
            return None

    monkeypatch.setattr(server_module, "create_server", lambda deps: _StubServer())

    code = server_module.main(["--home", home, "--auto-prune-on-start", "true"])

    assert code == 0
    assert count_rows(factory, "events") == 0  # pruned during startup
