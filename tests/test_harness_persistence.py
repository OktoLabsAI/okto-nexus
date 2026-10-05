"""Phase 3.5 (harness-integrations) - persistence tests for D10.

Covers migration 029 (idempotency, REG-07) and the two SQLite repos it backs:
:class:`SqliteHarnessSessionRepo` / :class:`SqliteHarnessEventRepo`. These
round-trip the FROZEN :class:`~okto_nexus.domain.harness.HarnessSession` /
:class:`~okto_nexus.domain.harness.HarnessEvent` dataclasses straight back out
of storage - there is no persistence-only shape distinct from the domain type
the connector port already speaks.
"""

from __future__ import annotations

import pytest

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.harness_repo import (
    SqliteHarnessEventRepo,
    SqliteHarnessSessionRepo,
)
from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteAgentRepo
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from okto_nexus.config import NexusConfig
from okto_nexus.domain.harness import (
    STATUS_ENDED,
    STATUS_RUNNING,
    STEER_TIMING_NEXT_TURN_BOUNDARY,
    HarnessCapabilities,
    HarnessEvent,
    HarnessSession,
    new_harness_session_id,
)


def make_factory(tmp_path, name: str = "home") -> ConnectionFactory:
    return ConnectionFactory(NexusConfig(home_dir=tmp_path / name))


def _caps(**overrides) -> HarnessCapabilities:
    defaults = dict(
        send_only=False,
        steer_timing=STEER_TIMING_NEXT_TURN_BOUNDARY,
        interrupt_requires_settle_wait=True,
        multiplexes_sessions=False,
        observes_session_end=True,
    )
    defaults.update(overrides)
    return HarnessCapabilities(**defaults)


def register_agent(factory, agent_id: str) -> None:
    with factory.unit_of_work() as uow:
        SqliteAgentRepo(None).upsert(uow, agent_id=agent_id)


# --------------------------------------------------------------------------- #
# Migration 029: applies from empty, and is idempotent (REG-07)
# --------------------------------------------------------------------------- #
def test_migration_029_applies_from_empty_and_creates_expected_tables(tmp_path):
    factory = make_factory(tmp_path)
    MigrationRunner(factory).apply()

    conn = factory.get_connection()
    try:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        conn.close()
    assert "harness_sessions" in names
    assert "harness_events" in names


def test_migration_029_is_idempotent(tmp_path):
    factory = make_factory(tmp_path)
    MigrationRunner(factory).apply()
    # Re-running the FULL runner against an already-migrated store (every
    # version, including 029, already ledgered) must be a clean no-op - no
    # exception, no duplicate/altered schema.
    MigrationRunner(factory).apply()

    register_agent(factory, "harness-agent")
    session_repo = SqliteHarnessSessionRepo()
    session = HarnessSession(
        session_id=new_harness_session_id(),
        harness_kind="pi",
        owning_agent_id="harness-agent",
        status=STATUS_RUNNING,
        capabilities=_caps(),
        started_at="2026-09-20T00:00:00.000000Z",
    )
    with factory.unit_of_work() as uow:
        session_repo.create(uow, session=session, created_at="2026-09-20T00:00:00.000000Z")
    with factory.unit_of_work() as uow:
        fetched = session_repo.get(uow, session_id=session.session_id)
    assert fetched is not None
    assert fetched.session_id == session.session_id


def test_migration_029_sql_itself_is_safe_to_execute_twice(tmp_path):
    """The ledger-based idempotency above only proves the RUNNER skips an
    already-applied version - it never actually re-executes 029's SQL, so it
    cannot catch a statement that would fail on a second run (e.g. a bare
    ``CREATE INDEX`` without ``IF NOT EXISTS``). This test runs the 029
    script's OWN statements against a connection TWICE, bypassing the
    ledger entirely, so the claim "the SQL is idempotent" is backed by
    actually re-running the SQL, not by the runner never trying to."""
    from okto_nexus.adapters.outbound.sqlite import migrations as migrations_module

    factory = make_factory(tmp_path)
    # Bring the schema up through 028 (harness_sessions' FK target - agents -
    # must exist) via the real runner, THEN apply 029's raw text twice
    # ourselves, outside the runner/ledger.
    migrations_dir = migrations_module._default_migrations_dir()
    path_029 = migrations_dir / "029_harness_sessions_and_events.sql"
    assert path_029.is_file()
    script = path_029.read_text(encoding="utf-8")
    statements = migrations_module._split_statements(script)
    assert statements, "029's script produced no statements - check the splitter/format"

    conn = factory.get_connection()
    try:
        # Apply every OTHER migration (001..028) first so the FK target and
        # baseline schema exist, without going through 029 itself yet.
        for version in range(1, 29):
            match = next(migrations_dir.glob(f"{version:03d}_*.sql"))
            for stmt in migrations_module._split_statements(
                match.read_text(encoding="utf-8")
            ):
                conn.execute(stmt)
        conn.commit()

        for stmt in statements:
            conn.execute(stmt)
        conn.commit()
        # Second run of the SAME statements: must not raise.
        for stmt in statements:
            conn.execute(stmt)
        conn.commit()

        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {"harness_sessions", "harness_events"} <= names
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# SqliteHarnessSessionRepo
# --------------------------------------------------------------------------- #
@pytest.fixture
def factory(tmp_path):
    f = make_factory(tmp_path)
    MigrationRunner(f).apply()
    register_agent(f, "harness-agent")
    return f


def test_session_repo_create_and_get_roundtrips_domain_type(factory):
    repo = SqliteHarnessSessionRepo()
    session = HarnessSession(
        session_id=new_harness_session_id(),
        harness_kind="codex",
        owning_agent_id="harness-agent",
        status=STATUS_RUNNING,
        capabilities=_caps(send_only=False, steer_timing=None, multiplexes_sessions=True),
        started_at="2026-09-20T00:00:00.000000Z",
        metadata={"thread_id": "t1"},
    )
    with factory.unit_of_work() as uow:
        repo.create(uow, session=session, created_at="2026-09-20T00:00:00.000000Z")

    with factory.unit_of_work() as uow:
        fetched = repo.get(uow, session_id=session.session_id)

    assert fetched is not None
    assert fetched.session_id == session.session_id
    assert fetched.harness_kind == "codex"
    assert fetched.owning_agent_id == "harness-agent"
    assert fetched.status == STATUS_RUNNING
    assert fetched.capabilities == session.capabilities
    assert fetched.metadata == {"thread_id": "t1"}
    assert fetched.ended_at is None


def test_session_repo_get_unknown_returns_none(factory):
    repo = SqliteHarnessSessionRepo()
    with factory.unit_of_work() as uow:
        assert repo.get(uow, session_id="hsess_missing") is None


def test_session_repo_update_status_transitions_and_stamps_ended_at(factory):
    repo = SqliteHarnessSessionRepo()
    session = HarnessSession(
        session_id=new_harness_session_id(),
        harness_kind="pi",
        owning_agent_id="harness-agent",
        status=STATUS_RUNNING,
        capabilities=_caps(),
        started_at="2026-09-20T00:00:00.000000Z",
    )
    with factory.unit_of_work() as uow:
        repo.create(uow, session=session, created_at="2026-09-20T00:00:00.000000Z")

    with factory.unit_of_work() as uow:
        updated = repo.update_status(
            uow,
            session_id=session.session_id,
            status=STATUS_ENDED,
            updated_at="2026-09-20T00:05:00.000000Z",
            ended_at="2026-09-20T00:05:00.000000Z",
        )
    assert updated is True

    with factory.unit_of_work() as uow:
        fetched = repo.get(uow, session_id=session.session_id)
    assert fetched.status == STATUS_ENDED
    assert fetched.ended_at == "2026-09-20T00:05:00.000000Z"


def test_session_repo_update_status_unknown_session_returns_false(factory):
    repo = SqliteHarnessSessionRepo()
    with factory.unit_of_work() as uow:
        updated = repo.update_status(
            uow,
            session_id="hsess_missing",
            status=STATUS_ENDED,
            updated_at="2026-09-20T00:05:00.000000Z",
        )
    assert updated is False


def test_session_repo_list_filters_by_status(factory):
    repo = SqliteHarnessSessionRepo()
    running = HarnessSession(
        session_id=new_harness_session_id(),
        harness_kind="pi",
        owning_agent_id="harness-agent",
        status=STATUS_RUNNING,
        capabilities=_caps(),
        started_at="2026-09-20T00:00:00.000000Z",
    )
    ended = HarnessSession(
        session_id=new_harness_session_id(),
        harness_kind="pi",
        owning_agent_id="harness-agent",
        status=STATUS_ENDED,
        capabilities=_caps(),
        started_at="2026-09-20T00:01:00.000000Z",
        ended_at="2026-09-20T00:02:00.000000Z",
    )
    with factory.unit_of_work() as uow:
        repo.create(uow, session=running, created_at="2026-09-20T00:00:00.000000Z")
        repo.create(uow, session=ended, created_at="2026-09-20T00:01:00.000000Z")

    with factory.unit_of_work() as uow:
        only_running = repo.list(uow, status=STATUS_RUNNING)
        everything = repo.list(uow)

    assert [s.session_id for s in only_running] == [running.session_id]
    assert {s.session_id for s in everything} == {running.session_id, ended.session_id}


# --------------------------------------------------------------------------- #
# SqliteHarnessEventRepo
# --------------------------------------------------------------------------- #
def _make_session_row(factory, session_id: str) -> None:
    with factory.unit_of_work() as uow:
        SqliteHarnessSessionRepo().create(
            uow,
            session=HarnessSession(
                session_id=session_id,
                harness_kind="pi",
                owning_agent_id="harness-agent",
                status=STATUS_RUNNING,
                capabilities=_caps(),
                started_at="2026-09-20T00:00:00.000000Z",
            ),
            created_at="2026-09-20T00:00:00.000000Z",
        )


def test_event_repo_append_assigns_monotonic_per_session_sequence(factory):
    session_id = new_harness_session_id()
    _make_session_row(factory, session_id)
    repo = SqliteHarnessEventRepo()

    sequences = []
    for i in range(3):
        event = HarnessEvent(
            session_id=session_id,
            harness_kind="pi",
            kind="output_delta",
            native_event=f"native/{i}",
            occurred_at=f"2026-09-20T00:0{i}:00.000000Z",
            payload={"i": i},
        )
        with factory.unit_of_work() as uow:
            sequences.append(
                repo.append(
                    uow,
                    event_id=f"hevt_{i}",
                    event=event,
                    created_at="2026-09-20T00:00:00.000000Z",
                )
            )
    assert sequences == [1, 2, 3]


def test_event_repo_append_is_independent_per_session(factory):
    a, b = new_harness_session_id(), new_harness_session_id()
    _make_session_row(factory, a)
    _make_session_row(factory, b)
    repo = SqliteHarnessEventRepo()

    def push(session_id, i):
        event = HarnessEvent(
            session_id=session_id,
            harness_kind="pi",
            kind="output_delta",
            native_event=f"native/{i}",
            occurred_at="2026-09-20T00:00:00.000000Z",
        )
        with factory.unit_of_work() as uow:
            return repo.append(uow, event_id=f"hevt_{session_id}_{i}", event=event, created_at="x")

    assert push(a, 0) == 1
    assert push(b, 0) == 1
    assert push(a, 1) == 2
    assert push(b, 1) == 2


def test_event_repo_list_for_session_carries_native_event_verbatim(factory):
    session_id = new_harness_session_id()
    _make_session_row(factory, session_id)
    repo = SqliteHarnessEventRepo()
    event = HarnessEvent(
        session_id=session_id,
        harness_kind="codex",
        kind="turn_completed",
        native_event="turn.completed",
        occurred_at="2026-09-20T00:00:00.000000Z",
        payload={"threadId": "t1", "nested": {"a": 1}},
        thread_id="t1",
        turn_id="u1",
    )
    with factory.unit_of_work() as uow:
        repo.append(uow, event_id="hevt_1", event=event, created_at="2026-09-20T00:00:00.000000Z")

    with factory.unit_of_work() as uow:
        rows = repo.list_for_session(uow, session_id=session_id)

    assert len(rows) == 1
    fetched = rows[0]
    assert fetched.native_event == "turn.completed"
    assert fetched.kind == "turn_completed"
    assert fetched.harness_kind == "codex"
    assert fetched.payload == {"threadId": "t1", "nested": {"a": 1}}
    assert fetched.thread_id == "t1"
    assert fetched.turn_id == "u1"


def test_event_repo_list_for_session_respects_after_sequence_and_order(factory):
    session_id = new_harness_session_id()
    _make_session_row(factory, session_id)
    repo = SqliteHarnessEventRepo()
    for i in range(5):
        event = HarnessEvent(
            session_id=session_id,
            harness_kind="pi",
            kind="output_delta",
            native_event=f"native/{i}",
            occurred_at="2026-09-20T00:00:00.000000Z",
        )
        with factory.unit_of_work() as uow:
            repo.append(uow, event_id=f"hevt_{i}", event=event, created_at="x")

    with factory.unit_of_work() as uow:
        rows = repo.list_for_session(uow, session_id=session_id, after_sequence=2)
    assert [r.native_event for r in rows] == ["native/2", "native/3", "native/4"]


def test_event_repo_cascade_deletes_with_session(factory):
    session_id = new_harness_session_id()
    _make_session_row(factory, session_id)
    repo = SqliteHarnessEventRepo()
    event = HarnessEvent(
        session_id=session_id,
        harness_kind="pi",
        kind="output_delta",
        native_event="native/0",
        occurred_at="2026-09-20T00:00:00.000000Z",
    )
    with factory.unit_of_work() as uow:
        repo.append(uow, event_id="hevt_0", event=event, created_at="x")

    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "DELETE FROM harness_sessions WHERE session_id = ?", (session_id,)
        )

    with factory.unit_of_work() as uow:
        rows = repo.list_for_session(uow, session_id=session_id)
    assert rows == []
