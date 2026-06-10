"""Tests for the Event Log slice (event_get / event_wait).

Hexagonal unit/integration tests: the application service runs over the real
SQLite adapters (via ``migrated_factory``); the ``Sleeper``/monotonic clock used
by the long-poll loop are injected as deterministic fakes so timeout/poll paths
run instantly and assert sleep counts. Coverage spans:

* cursor pagination (ascending, next_cursor, has_more) and the boundary N==L;
* long-poll: immediate return (0 sleeps), timeout (events=[], entry cursor
  unchanged, timed_out=True), single-shot ``timeout_seconds<=0``, and observing
  a concurrent append within one poll interval;
* visibility applied BEFORE the envelope with cursor advancing past hidden
  events (no re-scan), including capability-targeted visibility via the agents
  repo;
* the canonical error catalogue (INVALID_STREAM, WORKSPACE_REQUIRED,
  WORKSPACE_UNRESOLVED, VALIDATION_ERROR for cursor/limit/timeout/filters);
* AND-combined equality filters with cursor advance (incl. payload task_id);
* clamp of ``limit`` and ``timeout_seconds`` to configured ceilings;
* append-only invariants and concurrent writers allocating distinct, strictly
  increasing event_ids with no lost write / reuse;
* cross-workspace isolation; and the MCP tool envelope (no exception escapes).
"""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.mcp.tools.events import (
    MAX_EVENT_LIMIT_ENV,
    _resolve_max_limit,
    build_service,
    register,
)
from okto_nexus.adapters.outbound.sqlite.events_repo import (
    SqliteEventEmitter,
    SqliteEventRepo,
)
from okto_nexus.adapters.outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteWorkspaceRepo,
)
from okto_nexus.application.events import (
    DEFAULT_EVENT_LIMIT,
    MAX_EVENT_LIMIT,
    EventService,
)
from okto_nexus.application.ports import Repos
from okto_nexus.config import NexusConfig
from okto_nexus.domain.ids import resolve_workspace_id
from okto_nexus.errors import ErrorCode, OktoNexusError


# --------------------------------------------------------------------------- #
# Test doubles & helpers
# --------------------------------------------------------------------------- #
class StubClock:
    """Deterministic Clock implementing the port (now_iso/now_epoch)."""

    def __init__(self, iso: str = "2026-06-07T00:00:00Z", epoch: float = 1_780_000_000.0):
        self._iso = iso
        self._epoch = epoch

    def now_iso(self) -> str:
        return self._iso

    def now_epoch(self) -> float:
        return self._epoch


class ManualSleeper:
    """Fake Sleeper + monotonic clock: records sleeps, advances a virtual time."""

    def __init__(self) -> None:
        self.calls: list[float] = []
        self.t = 0.0

    def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.t += seconds

    def monotonic(self) -> float:
        return self.t


class TriggerSleeper(ManualSleeper):
    """Like ManualSleeper but fires ``trigger`` on the Nth sleep call."""

    def __init__(self, trigger, at_call: int = 1) -> None:
        super().__init__()
        self._trigger = trigger
        self._at = at_call

    def sleep(self, seconds: float) -> None:
        super().sleep(seconds)
        if len(self.calls) == self._at:
            self._trigger()


class ExplodingSleeper:
    """A Sleeper that must never be called (asserts immediate return)."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def sleep(self, seconds: float) -> None:  # pragma: no cover - failure path
        self.calls.append(seconds)
        raise AssertionError("sleep must not be called when events already exist")

    def monotonic(self) -> float:
        return 0.0


class FakeServer:
    """Captures FastMCP-style ``@server.tool()`` registrations by name."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def cfg(tmp_path, **overrides) -> NexusConfig:
    base = dict(home_dir=tmp_path / "okto_home")
    base.update(overrides)
    return NexusConfig(**base)


def make_ws(factory, tmp_path, name: str = "P") -> tuple[str, str]:
    """Create a real dir + its workspaces row; return (project_root, workspace_id)."""
    d = tmp_path / name
    d.mkdir()
    ws = resolve_workspace_id(str(d))
    with factory.unit_of_work() as uow:
        SqliteWorkspaceRepo(StubClock()).upsert(
            uow, workspace_id=ws, root_realpath=os.path.realpath(str(d))
        )
    return str(d), ws


def register_agent(factory, agent_id, role=None, capabilities=None) -> None:
    with factory.unit_of_work() as uow:
        SqliteAgentRepo(StubClock()).upsert(
            uow, agent_id=agent_id, role=role, capabilities=capabilities
        )


def emit(
    factory,
    ws,
    *,
    stream="workspace",
    type="evt",
    payload=None,
    actor_agent_id=None,
    visibility=None,
    target=None,
) -> int:
    with factory.unit_of_work() as uow:
        return SqliteEventRepo().append(
            uow,
            workspace_id=ws,
            stream=stream,
            type=type,
            payload=payload,
            actor_agent_id=actor_agent_id,
            visibility=visibility,
            target=target,
        )


def make_service(
    factory,
    config,
    *,
    agents=None,
    sleeper=None,
    monotonic=None,
    default_limit=DEFAULT_EVENT_LIMIT,
    max_limit=MAX_EVENT_LIMIT,
) -> EventService:
    clock = StubClock()
    return EventService(
        connection_factory=factory,
        events=SqliteEventRepo(clock),
        clock=clock,
        config=config,
        agents=agents,
        default_limit=default_limit,
        max_limit=max_limit,
        sleeper=sleeper,
        monotonic=monotonic,
    )


def count(factory, table: str) -> int:
    conn = factory.get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def retry_db(fn, attempts: int = 40, delay: float = 0.02):
    last = None
    for _ in range(attempts):
        try:
            return fn()
        except OktoNexusError as exc:
            if exc.code != ErrorCode.DB_ERROR.value:
                raise
            last = exc
            time.sleep(delay)
    raise last  # pragma: no cover


# --------------------------------------------------------------------------- #
# event_get: pagination
# --------------------------------------------------------------------------- #
def test_event_get_ascending_pagination_next_cursor_has_more(
    migrated_factory, tmp_path
):
    config = cfg(tmp_path)
    pr, ws = make_ws(migrated_factory, tmp_path)
    ids = [emit(migrated_factory, ws, type=f"e{i}") for i in range(5)]
    assert ids == [1, 2, 3, 4, 5]
    svc = make_service(migrated_factory, config)

    p1 = svc.event_get(project_root=pr, agent_id="alice", stream="workspace", limit=2)
    assert p1["timed_out"] is False
    assert [e["event_id"] for e in p1["events"]] == [1, 2]
    assert p1["next_cursor"] == 2
    assert p1["has_more"] is True

    p2 = svc.event_get(
        project_root=pr, agent_id="alice", stream="workspace", cursor=2, limit=2
    )
    assert [e["event_id"] for e in p2["events"]] == [3, 4]
    assert p2["next_cursor"] == 4 and p2["has_more"] is True

    p3 = svc.event_get(
        project_root=pr, agent_id="alice", stream="workspace", cursor=4, limit=2
    )
    assert [e["event_id"] for e in p3["events"]] == [5]
    assert p3["next_cursor"] == 5 and p3["has_more"] is False


def test_event_get_n_equals_l_has_more_false(migrated_factory, tmp_path):
    config = cfg(tmp_path)
    pr, ws = make_ws(migrated_factory, tmp_path)
    emit(migrated_factory, ws)
    emit(migrated_factory, ws)
    svc = make_service(migrated_factory, config)
    page = svc.event_get(project_root=pr, agent_id="a", stream="workspace", limit=2)
    assert [e["event_id"] for e in page["events"]] == [1, 2]
    assert page["has_more"] is False and page["next_cursor"] == 2


def test_event_get_empty_beyond_cursor(migrated_factory, tmp_path):
    config = cfg(tmp_path)
    pr, ws = make_ws(migrated_factory, tmp_path)
    emit(migrated_factory, ws)
    svc = make_service(migrated_factory, config)
    page = svc.event_get(project_root=pr, agent_id="a", stream="workspace", cursor=9)
    assert page["events"] == []
    assert page["next_cursor"] == 9 and page["has_more"] is False
    assert page["timed_out"] is False


# --------------------------------------------------------------------------- #
# event_wait
# --------------------------------------------------------------------------- #
def test_event_wait_returns_immediately_zero_sleeps(migrated_factory, tmp_path):
    config = cfg(tmp_path)
    pr, ws = make_ws(migrated_factory, tmp_path)
    emit(migrated_factory, ws)
    sleeper = ExplodingSleeper()
    svc = make_service(
        migrated_factory, config, sleeper=sleeper.sleep, monotonic=sleeper.monotonic
    )
    page = svc.event_wait(
        project_root=pr, agent_id="a", stream="workspace", timeout_seconds=30
    )
    assert page["timed_out"] is False
    assert [e["event_id"] for e in page["events"]] == [1]
    assert sleeper.calls == []  # 0 sleeps


def test_event_wait_timeout_entry_cursor_unchanged(migrated_factory, tmp_path):
    # A hidden event exists after the cursor: the internal scan advances, but the
    # timed-out result must report the ENTRY cursor unchanged (fr_33beeba8).
    config = cfg(tmp_path, max_wait_timeout_seconds=1, poll_interval_ms=200)
    pr, ws = make_ws(migrated_factory, tmp_path)
    emit(
        migrated_factory,
        ws,
        visibility="eligible",
        target={"strategy": "direct", "agent_id": "bob"},
    )
    sleeper = ManualSleeper()
    svc = make_service(
        migrated_factory, config, sleeper=sleeper.sleep, monotonic=sleeper.monotonic
    )
    page = svc.event_wait(
        project_root=pr, agent_id="alice", stream="workspace", cursor=0
    )
    assert page["events"] == []
    assert page["next_cursor"] == 0  # unchanged, NOT advanced to the hidden event
    assert page["has_more"] is False
    assert page["timed_out"] is True
    # Bounded by clamp(timeout) + at most one poll interval.
    assert sleeper.calls  # at least one sleep happened
    assert sleeper.t <= 1 + (config.poll_interval_ms / 1000.0) + 1e-9


def test_event_wait_single_shot_timeout_zero(migrated_factory, tmp_path):
    config = cfg(tmp_path)
    pr, ws = make_ws(migrated_factory, tmp_path)
    sleeper = ManualSleeper()
    svc = make_service(
        migrated_factory, config, sleeper=sleeper.sleep, monotonic=sleeper.monotonic
    )
    # No events + timeout_seconds<=0 -> single event_get, no sleeping.
    page = svc.event_wait(
        project_root=pr, agent_id="a", stream="workspace", timeout_seconds=0
    )
    assert page["events"] == [] and page["timed_out"] is True
    assert page["next_cursor"] == 0
    assert sleeper.calls == []

    # With an event present, the single shot returns it immediately.
    emit(migrated_factory, ws)
    page2 = svc.event_wait(
        project_root=pr, agent_id="a", stream="workspace", timeout_seconds=-5
    )
    assert [e["event_id"] for e in page2["events"]] == [1]
    assert page2["timed_out"] is False
    assert sleeper.calls == []


def test_event_wait_observes_concurrent_append_within_one_interval(
    migrated_factory, tmp_path
):
    config = cfg(tmp_path, max_wait_timeout_seconds=30, poll_interval_ms=200)
    pr, ws = make_ws(migrated_factory, tmp_path)

    def append_during_sleep():
        emit(migrated_factory, ws, type="late")

    sleeper = TriggerSleeper(append_during_sleep, at_call=1)
    svc = make_service(
        migrated_factory, config, sleeper=sleeper.sleep, monotonic=sleeper.monotonic
    )
    page = svc.event_wait(
        project_root=pr, agent_id="a", stream="workspace", timeout_seconds=10
    )
    assert page["timed_out"] is False
    assert [e["type"] for e in page["events"]] == ["late"]
    assert len(sleeper.calls) == 1  # observed after exactly one poll interval


# --------------------------------------------------------------------------- #
# Visibility (applied before envelope; cursor advances past hidden events)
# --------------------------------------------------------------------------- #
def test_visibility_excludes_and_cursor_advances_no_rescan(
    migrated_factory, tmp_path
):
    config = cfg(tmp_path)
    pr, ws = make_ws(migrated_factory, tmp_path)
    emit(migrated_factory, ws, type="v1")  # public
    emit(
        migrated_factory,
        ws,
        type="hidden",
        visibility="eligible",
        target={"strategy": "direct", "agent_id": "bob"},
    )
    emit(migrated_factory, ws, type="v2")  # public
    svc = make_service(migrated_factory, config)

    p1 = svc.event_get(project_root=pr, agent_id="alice", stream="workspace", limit=10)
    assert [e["event_id"] for e in p1["events"]] == [1, 3]
    assert p1["next_cursor"] == 3  # advanced past hidden event 2
    assert p1["has_more"] is False

    # Re-call with the returned next_cursor: hidden event is never re-returned.
    p2 = svc.event_get(
        project_root=pr, agent_id="alice", stream="workspace", cursor=p1["next_cursor"]
    )
    assert p2["events"] == [] and p2["next_cursor"] == 3


def test_visibility_capability_targeted_uses_agents_repo(migrated_factory, tmp_path):
    config = cfg(tmp_path)
    pr, ws = make_ws(migrated_factory, tmp_path)
    register_agent(migrated_factory, "alice", capabilities=["py"])
    register_agent(migrated_factory, "bob", capabilities=[])
    emit(
        migrated_factory,
        ws,
        type="needs_py",
        visibility="eligible",
        target={"strategy": "capability", "capability": "py"},
    )
    agents = SqliteAgentRepo(StubClock())
    svc = make_service(migrated_factory, config, agents=agents)

    seen = svc.event_get(project_root=pr, agent_id="alice", stream="workspace")
    assert [e["type"] for e in seen["events"]] == ["needs_py"]

    not_seen = svc.event_get(project_root=pr, agent_id="bob", stream="workspace")
    assert not_seen["events"] == []
    assert not_seen["next_cursor"] == 1  # advanced past the non-visible event


# --------------------------------------------------------------------------- #
# Streams / workspace resolution errors
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad_stream", ["bogus", "", "WORKSPACE", "session", None])
def test_invalid_stream_no_scan(migrated_factory, tmp_path, bad_stream):
    config = cfg(tmp_path)
    pr, _ws = make_ws(migrated_factory, tmp_path)
    svc = make_service(migrated_factory, config)
    with pytest.raises(OktoNexusError) as ei:
        svc.event_get(project_root=pr, agent_id="a", stream=bad_stream)
    assert ei.value.code == ErrorCode.INVALID_STREAM.value
    with pytest.raises(OktoNexusError) as ei2:
        svc.event_wait(project_root=pr, agent_id="a", stream=bad_stream)
    assert ei2.value.code == ErrorCode.INVALID_STREAM.value


def test_workspace_required_and_unresolved(migrated_factory, tmp_path):
    config = cfg(tmp_path)
    svc = make_service(migrated_factory, config)
    for missing in (None, "", "   "):
        with pytest.raises(OktoNexusError) as ei:
            svc.event_get(project_root=missing, agent_id="a", stream="workspace")
        assert ei.value.code == ErrorCode.WORKSPACE_REQUIRED.value

    broken = str(tmp_path / "does_not_exist" / "child")
    with pytest.raises(OktoNexusError) as ei2:
        svc.event_get(project_root=broken, agent_id="a", stream="workspace")
    assert ei2.value.code == ErrorCode.WORKSPACE_UNRESOLVED.value


def test_agent_id_required(migrated_factory, tmp_path):
    config = cfg(tmp_path)
    pr, _ws = make_ws(migrated_factory, tmp_path)
    svc = make_service(migrated_factory, config)
    for bad in (None, "", "  "):
        with pytest.raises(OktoNexusError) as ei:
            svc.event_get(project_root=pr, agent_id=bad, stream="workspace")
        assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


# --------------------------------------------------------------------------- #
# Filters (AND equality) with cursor advance
# --------------------------------------------------------------------------- #
def test_filters_and_equality_cursor_advances_past_nonmatching(
    migrated_factory, tmp_path
):
    config = cfg(tmp_path)
    pr, ws = make_ws(migrated_factory, tmp_path)
    emit(migrated_factory, ws, type="A", actor_agent_id="x")  # 1 match
    emit(migrated_factory, ws, type="B", actor_agent_id="y")  # 2 no
    emit(migrated_factory, ws, type="A", actor_agent_id="x")  # 3 match
    emit(migrated_factory, ws, type="A", actor_agent_id="z")  # 4 no (agent)
    svc = make_service(migrated_factory, config)

    page = svc.event_get(
        project_root=pr,
        agent_id="caller",
        stream="workspace",
        filters={"type": "A", "agent_id": "x"},
        limit=10,
    )
    assert [e["event_id"] for e in page["events"]] == [1, 3]
    # next_cursor advances past the trailing non-matching event 4.
    assert page["next_cursor"] == 4
    assert page["has_more"] is False


def test_filters_task_id_from_payload(migrated_factory, tmp_path):
    config = cfg(tmp_path)
    pr, ws = make_ws(migrated_factory, tmp_path, name="T")
    emit(migrated_factory, ws, stream="task", type="task.x", payload={"task_id": "t1"})
    emit(migrated_factory, ws, stream="task", type="task.y", payload={"task_id": "t2"})
    svc = make_service(migrated_factory, config)
    page = svc.event_get(
        project_root=pr,
        agent_id="a",
        stream="task",
        filters={"task_id": "t1"},
    )
    assert [e["event_id"] for e in page["events"]] == [1]
    assert page["events"][0]["task_id"] == "t1"
    assert page["next_cursor"] == 2  # advanced past the non-matching event


def test_invalid_filter_key_rejected(migrated_factory, tmp_path):
    config = cfg(tmp_path)
    pr, _ws = make_ws(migrated_factory, tmp_path)
    svc = make_service(migrated_factory, config)
    with pytest.raises(OktoNexusError) as ei:
        svc.event_get(
            project_root=pr, agent_id="a", stream="workspace", filters={"foo": "bar"}
        )
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


# --------------------------------------------------------------------------- #
# Clamp of limit / timeout
# --------------------------------------------------------------------------- #
def test_limit_clamped_to_max(migrated_factory, tmp_path):
    config = cfg(tmp_path)
    pr, ws = make_ws(migrated_factory, tmp_path)
    for _ in range(5):
        emit(migrated_factory, ws)
    svc = make_service(migrated_factory, config, max_limit=2)
    page = svc.event_get(project_root=pr, agent_id="a", stream="workspace", limit=10_000)
    assert len(page["events"]) == 2  # clamped to max
    assert page["has_more"] is True


def test_timeout_clamped_to_ceiling(migrated_factory, tmp_path):
    config = cfg(tmp_path, max_wait_timeout_seconds=1, poll_interval_ms=200)
    pr, _ws = make_ws(migrated_factory, tmp_path)
    sleeper = ManualSleeper()
    svc = make_service(
        migrated_factory, config, sleeper=sleeper.sleep, monotonic=sleeper.monotonic
    )
    page = svc.event_wait(
        project_root=pr, agent_id="a", stream="workspace", timeout_seconds=10_000
    )
    assert page["timed_out"] is True
    # Effective wait never exceeds the ceiling (+ one poll interval).
    assert sleeper.t <= 1 + (config.poll_interval_ms / 1000.0) + 1e-9


@pytest.mark.parametrize("bad_cursor", [-1, "5", 1.0, True, [1]])
def test_invalid_cursor_validation_error(migrated_factory, tmp_path, bad_cursor):
    config = cfg(tmp_path)
    pr, _ws = make_ws(migrated_factory, tmp_path)
    svc = make_service(migrated_factory, config)
    with pytest.raises(OktoNexusError) as ei:
        svc.event_get(
            project_root=pr, agent_id="a", stream="workspace", cursor=bad_cursor
        )
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


@pytest.mark.parametrize("bad_limit", [0, -3, "10", 2.5, True])
def test_invalid_limit_validation_error(migrated_factory, tmp_path, bad_limit):
    config = cfg(tmp_path)
    pr, _ws = make_ws(migrated_factory, tmp_path)
    svc = make_service(migrated_factory, config)
    with pytest.raises(OktoNexusError) as ei:
        svc.event_get(
            project_root=pr, agent_id="a", stream="workspace", limit=bad_limit
        )
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


@pytest.mark.parametrize("bad_timeout", ["5", 2.5, True, [1]])
def test_invalid_timeout_validation_error(migrated_factory, tmp_path, bad_timeout):
    config = cfg(tmp_path)
    pr, _ws = make_ws(migrated_factory, tmp_path)
    svc = make_service(migrated_factory, config)
    with pytest.raises(OktoNexusError) as ei:
        svc.event_wait(
            project_root=pr,
            agent_id="a",
            stream="workspace",
            timeout_seconds=bad_timeout,
        )
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


# --------------------------------------------------------------------------- #
# Append-only & cross-workspace isolation
# --------------------------------------------------------------------------- #
def test_log_is_append_only_reads_never_mutate(migrated_factory, tmp_path):
    config = cfg(tmp_path)
    pr, ws = make_ws(migrated_factory, tmp_path)
    id1 = emit(migrated_factory, ws, type="a")
    id2 = emit(migrated_factory, ws, type="b")
    assert id2 > id1
    svc = make_service(migrated_factory, config)

    before = _snapshot_events(migrated_factory)
    for _ in range(3):
        svc.event_get(project_root=pr, agent_id="x", stream="workspace")
        svc.event_wait(
            project_root=pr, agent_id="x", stream="workspace", timeout_seconds=0
        )
    after = _snapshot_events(migrated_factory)
    assert before == after  # no row updated/deleted by any read
    assert count(migrated_factory, "events") == 2


def _snapshot_events(factory) -> list[tuple]:
    conn = factory.get_connection()
    try:
        rows = conn.execute(
            "SELECT event_id, type, created_at FROM events ORDER BY event_id"
        ).fetchall()
        return [(r["event_id"], r["type"], r["created_at"]) for r in rows]
    finally:
        conn.close()


def test_cross_workspace_isolation(migrated_factory, tmp_path):
    config = cfg(tmp_path)
    pr_a, ws_a = make_ws(migrated_factory, tmp_path, name="A")
    pr_b, ws_b = make_ws(migrated_factory, tmp_path, name="B")
    emit(migrated_factory, ws_b, type="b-only")
    emit(migrated_factory, ws_a, type="a-only")
    svc = make_service(migrated_factory, config)

    page_a = svc.event_get(project_root=pr_a, agent_id="a", stream="workspace")
    assert [e["type"] for e in page_a["events"]] == ["a-only"]
    assert all(e["workspace_id"] == ws_a for e in page_a["events"])

    page_b = svc.event_get(project_root=pr_b, agent_id="a", stream="workspace")
    assert [e["type"] for e in page_b["events"]] == ["b-only"]


# --------------------------------------------------------------------------- #
# Concurrency: monotonic event_id under concurrent writers
# --------------------------------------------------------------------------- #
def test_concurrent_writers_distinct_monotonic_ids(migrated_factory, tmp_path):
    _pr, ws = make_ws(migrated_factory, tmp_path)
    n = 16
    ids: list[int] = []
    lock = threading.Lock()
    barrier = threading.Barrier(n)

    def worker(i):
        barrier.wait()
        eid = retry_db(lambda: emit(migrated_factory, ws, type=f"e{i}"))
        with lock:
            ids.append(eid)

    with ThreadPoolExecutor(max_workers=n) as ex:
        futures = [ex.submit(worker, i) for i in range(n)]
        for f in futures:
            f.result()

    assert len(ids) == n
    assert len(set(ids)) == n  # no reuse
    assert sorted(ids) == list(range(min(ids), min(ids) + n))  # gapless, monotonic
    assert count(migrated_factory, "events") == n  # no lost write


# --------------------------------------------------------------------------- #
# list_after: stream=None selects ALL streams (M2 regression - the adapter used
# to compile stream=None to ``WHERE stream = NULL``, matching nothing)
# --------------------------------------------------------------------------- #
def test_list_after_stream_none_returns_all_streams(migrated_factory, tmp_path):
    _pr, ws = make_ws(migrated_factory, tmp_path)
    emit(migrated_factory, ws, stream="workspace", type="w.1")
    emit(migrated_factory, ws, stream="task", type="t.1")
    emit(migrated_factory, ws, stream="handoff", type="h.1")
    emit(migrated_factory, ws, stream="agent", type="a.1")

    repo = SqliteEventRepo(StubClock())
    with migrated_factory.unit_of_work() as uow:
        all_streams = repo.list_after(uow, workspace_id=ws, stream=None)
        only_task = repo.list_after(uow, workspace_id=ws, stream="task")
        after_cursor = repo.list_after(uow, workspace_id=ws, stream=None, cursor=2)

    assert [e.event_id for e in all_streams] == [1, 2, 3, 4]  # every stream, ascending
    assert [e.type for e in all_streams] == ["w.1", "t.1", "h.1", "a.1"]
    assert [e.type for e in only_task] == ["t.1"]  # a str stream still filters
    assert [e.event_id for e in after_cursor] == [3, 4]  # cursor honoured with None


def test_list_after_stream_none_is_workspace_scoped(migrated_factory, tmp_path):
    _pa, ws_a = make_ws(migrated_factory, tmp_path, name="A")
    _pb, ws_b = make_ws(migrated_factory, tmp_path, name="B")
    emit(migrated_factory, ws_a, stream="workspace", type="a.evt")
    emit(migrated_factory, ws_b, stream="task", type="b.evt")

    repo = SqliteEventRepo(StubClock())
    with migrated_factory.unit_of_work() as uow:
        rows = repo.list_after(uow, workspace_id=ws_a, stream=None)
    assert [e.type for e in rows] == ["a.evt"]  # all-streams never crosses workspaces


# --------------------------------------------------------------------------- #
# Fail-closed emit vocabulary (M2): garbage stream/visibility/type never persists
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "bad_kwargs",
    [
        {"stream": "session"},  # the exact production bug (identity slice)
        {"stream": "messages"},
        {"stream": ""},
        {"stream": None},
        {"visibility": "workspace"},  # the exact production bug (identity slice)
        {"visibility": "loud"},
        {"type": ""},
        {"type": "   "},
        {"type": None},
    ],
)
def test_append_rejects_out_of_vocabulary_fail_closed(
    migrated_factory, tmp_path, bad_kwargs
):
    _pr, ws = make_ws(migrated_factory, tmp_path)
    kwargs = {"stream": "workspace", "type": "evt", "visibility": None}
    kwargs.update(bad_kwargs)
    with pytest.raises(OktoNexusError) as ei:
        emit(migrated_factory, ws, **kwargs)
    assert ei.value.code == ErrorCode.INTERNAL_ERROR.value
    assert count(migrated_factory, "events") == 0  # nothing persisted (fail-closed)


def test_emit_facade_inherits_vocabulary_gate(migrated_factory, tmp_path):
    _pr, ws = make_ws(migrated_factory, tmp_path)
    emitter = SqliteEventEmitter(SqliteEventRepo(StubClock()))
    with pytest.raises(OktoNexusError) as ei:
        with migrated_factory.unit_of_work() as uow:
            emitter.emit(
                uow, workspace_id=ws, stream="session", type="session.opened"
            )
    assert ei.value.code == ErrorCode.INTERNAL_ERROR.value
    assert count(migrated_factory, "events") == 0


@pytest.mark.parametrize("visibility", [None, "public", "eligible", "private"])
def test_append_accepts_canonical_visibilities(migrated_factory, tmp_path, visibility):
    _pr, ws = make_ws(migrated_factory, tmp_path)
    eid = emit(migrated_factory, ws, visibility=visibility)
    assert eid == 1
    assert count(migrated_factory, "events") == 1


def test_emitter_facade_appends_monotonic_and_readable(migrated_factory, tmp_path):
    config = cfg(tmp_path)
    pr, ws = make_ws(migrated_factory, tmp_path)
    emitter = SqliteEventEmitter(SqliteEventRepo(StubClock()))
    with migrated_factory.unit_of_work() as uow:
        a = emitter.emit(uow, workspace_id=ws, stream="agent", type="agent.x")
        b = emitter.emit(uow, workspace_id=ws, stream="agent", type="agent.y")
    assert (a, b) == (1, 2)
    svc = make_service(migrated_factory, config)
    page = svc.event_get(project_root=pr, agent_id="a", stream="agent")
    assert [e["event_id"] for e in page["events"]] == [1, 2]


# --------------------------------------------------------------------------- #
# MCP tool registration + canonical envelope
# --------------------------------------------------------------------------- #
def _make_deps(factory, config):
    return SimpleNamespace(
        config=config,
        connection_factory=factory,
        clock=StubClock(),
        repos=Repos(),
        event_emitter=None,
    )


def test_register_wires_deps_and_envelope(migrated_factory, tmp_path):
    config = cfg(tmp_path)
    pr, ws = make_ws(migrated_factory, tmp_path)
    emit(migrated_factory, ws, type="hello")
    deps = _make_deps(migrated_factory, config)
    server = FakeServer()
    register(server, deps)

    assert set(server.tools) == {"event_get", "event_wait"}
    assert deps.repos.events is not None
    assert deps.repos.agents is not None
    assert deps.event_emitter is not None  # published for peer slices

    ok = server.tools["event_get"](project_root=pr, agent_id="a", stream="workspace")
    assert ok["ok"] is True
    assert [e["type"] for e in ok["data"]["events"]] == ["hello"]
    assert ok["data"]["timed_out"] is False

    bad_stream = server.tools["event_get"](
        project_root=pr, agent_id="a", stream="nope"
    )
    assert bad_stream["ok"] is False
    assert bad_stream["error"]["code"] == "INVALID_STREAM"

    missing_ws = server.tools["event_wait"](
        project_root="", agent_id="a", stream="workspace", timeout_seconds=0
    )
    assert missing_ws["ok"] is False
    assert missing_ws["error"]["code"] == "WORKSPACE_REQUIRED"

    bad_cursor = server.tools["event_get"](
        project_root=pr, agent_id="a", stream="workspace", cursor=-1
    )
    assert bad_cursor["ok"] is False
    assert bad_cursor["error"]["code"] == "VALIDATION_ERROR"


def test_register_reuses_existing_repos(migrated_factory, tmp_path):
    config = cfg(tmp_path)
    deps = _make_deps(migrated_factory, config)
    existing = SqliteEventRepo(StubClock())
    deps.repos.events = existing
    build_service(deps, env={})
    assert deps.repos.events is existing  # not overwritten
    assert deps.event_emitter is not None


def test_resolve_max_limit_env():
    assert _resolve_max_limit({}) == MAX_EVENT_LIMIT
    assert _resolve_max_limit({MAX_EVENT_LIMIT_ENV: "50"}) == 50
    assert _resolve_max_limit({MAX_EVENT_LIMIT_ENV: "  "}) == MAX_EVENT_LIMIT
    assert _resolve_max_limit({MAX_EVENT_LIMIT_ENV: "bad"}) == MAX_EVENT_LIMIT
    assert _resolve_max_limit({MAX_EVENT_LIMIT_ENV: "0"}) == MAX_EVENT_LIMIT


def test_event_reads_touch_registered_agent_last_seen(migrated_factory, tmp_path):
    # Reading the log stamps the caller's last_seen_at when the agent_id is a
    # registered identity (monitoring is an interaction). BOTH event_get and
    # event_wait touch; an UNregistered caller is a silent no-op - the touch is
    # an UPDATE, never an INSERT, so it creates no agents row.
    config = cfg(tmp_path)
    pr, _ws = make_ws(migrated_factory, tmp_path)
    register_agent(migrated_factory, "alice")
    register_agent(migrated_factory, "bob")
    agents = SqliteAgentRepo(StubClock())
    svc = make_service(migrated_factory, config, agents=agents)

    svc.event_get(project_root=pr, agent_id="alice", stream="workspace")
    svc.event_wait(project_root=pr, agent_id="bob", stream="workspace", timeout_seconds=0)
    svc.event_get(project_root=pr, agent_id="nobody", stream="workspace")  # unregistered
    with migrated_factory.unit_of_work() as uow:
        assert agents.get(uow, "alice").last_seen_at is not None  # event_get touched
        assert agents.get(uow, "bob").last_seen_at is not None  # event_wait touched
        assert agents.get(uow, "nobody") is None  # no-op: no row created
