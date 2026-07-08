"""Tests for the handoff lifecycle slice.

Hexagonal unit/integration tests: the application service runs over the REAL
SQLite adapters owned by this slice (``SqliteHandoffRepo`` via
``migrated_factory``), while ports owned by OTHER slices are faked - the
Event Log ``EventEmitter`` and the identity ``AgentRepo`` (agent-profile port
for routing/eligibility). Covers the workspace guard, cross-workspace
isolation, create happy path + validation + 64KB boundary + D1b (direct ->
unknown agent NOT_FOUND, pool zero-match warning), directed-handoff inbox
notification fan-out, list_available visibility/eligibility filtering +
opportunistic expiry + pagination/long-poll, atomic double-claim concurrency,
claim NOT_FOUND/WORKSPACE_MISMATCH, the eligibility gate, strict lease-expiry
boundary + re-claim, complete/reject ownership + persisted outcome +
creator-inbox delivery, creator-only cancel, handoff_get access/outcome, the
explicit transition table, the MCP tool envelope, and concurrent-writer event
monotonicity.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.mcp.tools.handoff import build_service, register
from okto_nexus.adapters.outbound.sqlite.events_repo import (
    SqliteEventEmitter,
    SqliteEventRepo,
)
from okto_nexus.adapters.outbound.sqlite.handoff_repo import SqliteHandoffRepo
from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteAgentRepo
from okto_nexus.adapters.outbound.sqlite.messages_repo import (
    SqliteMessageDeliveryRepo,
    SqliteMessageRepo,
)
from okto_nexus.application.events import EventService
from okto_nexus.application.handoff import HandoffService
from okto_nexus.application.inbox import InboxService
from okto_nexus.application.ports import Repos
from okto_nexus.config import NexusConfig
from okto_nexus.domain.base import iso_plus, iso_to_epoch
from okto_nexus.domain.handoff import (
    STATUS_CANCELLED,
    STATUS_CLAIMED,
    STATUS_COMPLETED,
    STATUS_OPEN,
    STATUS_REJECTED,
    TERMINAL_STATUSES,
    can_transition,
    is_direct_target,
    normalize_visibility,
    validate_target,
)
from okto_nexus.domain.ids import resolve_workspace_id
from okto_nexus.domain.models import Agent
from okto_nexus.errors import ErrorCode, OktoNexusError


# --------------------------------------------------------------------------- #
# Test doubles & helpers
# --------------------------------------------------------------------------- #
class StubClock:
    """Deterministic, mutable clock implementing the Clock port.

    Emits the canonical fixed-width form (utc_now_iso's shape): the lease-write
    boundary (domain.base.iso_plus) rejects a non-lexicographically-comparable
    clock value by design.
    """

    def __init__(self, iso: str = "2026-06-07T00:00:00.000000Z") -> None:
        self._iso = iso

    def now_iso(self) -> str:
        return self._iso

    def now_epoch(self) -> float:
        return iso_to_epoch(self._iso)

    def set(self, iso: str) -> None:
        self._iso = iso

    def advance_seconds(self, seconds: float) -> None:
        self._iso = iso_plus(self._iso, seconds)


class ThreadSafeEmitter:
    """Fake EventEmitter recording events with a monotonic, unique event_id."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self._next = 0
        self._lock = threading.Lock()

    def emit(
        self,
        uow,
        *,
        workspace_id,
        stream,
        type,
        payload=None,
        actor_agent_id=None,
        visibility=None,
        target=None,
    ) -> int:
        with self._lock:
            self._next += 1
            event_id = self._next
            self.events.append(
                {
                    "event_id": event_id,
                    "workspace_id": workspace_id,
                    "stream": stream,
                    "type": type,
                    "payload": payload,
                    "actor_agent_id": actor_agent_id,
                    "visibility": visibility,
                    "target": target,
                }
            )
        return event_id

    def types(self) -> list[str]:
        return [e["type"] for e in self.events]


class FakeAgentRepo:
    """Fake identity AgentRepo (other slice's profile port) for routing."""

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def add(self, agent_id, role=None, capabilities=None) -> None:
        self._agents[agent_id] = Agent(
            agent_id=agent_id,
            created_at="2026-06-07T00:00:00.000000Z",
            role=role,
            capabilities=capabilities or {},
            metadata={},
        )

    def get(self, uow, agent_id):
        return self._agents.get(agent_id)

    def list(self, uow):
        return list(self._agents.values())

    def upsert(self, uow, *, agent_id, role=None, capabilities=None, metadata=None):
        self.add(agent_id, role=role, capabilities=capabilities)
        return self._agents[agent_id]

    def touch(self, uow, *, agent_id, at=None) -> bool:
        agent = self._agents.get(agent_id)
        if agent is None:
            return False
        agent.last_seen_at = at
        return True


class FakeServer:
    """Captures FastMCP-style ``@server.tool()`` registrations by name."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            # Async tools (handoff_list_available's blocking long-poll now runs
            # off the event loop) reach these direct-call tests via a sync runner.
            if inspect.iscoroutinefunction(fn):

                @functools.wraps(fn)
                def _sync(*a, **k):
                    return asyncio.run(fn(*a, **k))

                self.tools[fn.__name__] = _sync
            else:
                self.tools[fn.__name__] = fn
            return fn

        return deco


class ManualWaiter:
    """Fake Waiter (application.ports): consumes each granted window, reports
    "no store change". Deterministic stand-in for an idle bus."""

    def __init__(self) -> None:
        self.calls: list[float] = []
        self.t = 0.0

    def monotonic(self) -> float:
        return self.t

    def snapshot(self):
        return 0

    def wait_for_change(self, since, timeout_s: float) -> bool:
        self.calls.append(timeout_s)
        self.t += timeout_s
        return False


class ClockAdvancingWaiter(ManualWaiter):
    """Fake Waiter that also advances the StubClock by each granted wait -
    deterministic real-time passing with NO store writes (lease/fallback
    boundaries arrive, data_version does not move)."""

    def __init__(self, clock: "StubClock") -> None:
        super().__init__()
        self._clock = clock

    def wait_for_change(self, since, timeout_s: float) -> bool:
        self._clock.advance_seconds(timeout_s)
        return super().wait_for_change(since, timeout_s)


class CountingHandoffRepo:
    """Delegating HandoffRepo wrapper recording the ``status`` of list scans."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.list_statuses: list = []

    def list(self, uow, *, workspace_id, status=None, target=None):
        self.list_statuses.append(status)
        return self._inner.list(
            uow, workspace_id=workspace_id, status=status, target=target
        )

    def __getattr__(self, name):
        return getattr(self._inner, name)


def make_service(
    factory,
    config,
    clock,
    emitter=None,
    agents=None,
    waiter=None,
    handoffs=None,
    messages=None,
    deliveries=None,
):
    return HandoffService(
        connection_factory=factory,
        handoffs=handoffs if handoffs is not None else SqliteHandoffRepo(clock),
        clock=clock,
        config=config,
        event_emitter=emitter,
        agents=agents,
        waiter=waiter,
        messages=messages,
        deliveries=deliveries,
    )


def make_deps(factory, config, clock, emitter=None):
    return SimpleNamespace(
        config=config,
        connection_factory=factory,
        clock=clock,
        repos=Repos(),
        event_emitter=emitter,
    )


def mkdir(tmp_path, name):
    p = tmp_path / name
    p.mkdir()
    return p


def seed_workspace(factory, project_root: str, clock) -> str:
    """Insert the workspaces row (FK target) and return its workspace_id."""
    ws = resolve_workspace_id(project_root)
    conn = factory.get_connection()
    try:
        conn.execute("BEGIN")
        conn.execute(
            "INSERT OR IGNORE INTO workspaces (workspace_id, created_at) VALUES (?, ?)",
            (ws, clock.now_iso()),
        )
        conn.execute("COMMIT")
    finally:
        conn.close()
    return ws


def row_of(factory, handoff_id: str):
    conn = factory.get_connection()
    try:
        r = conn.execute(
            "SELECT status, claimed_by, lease_expires_at, workspace_id, target "
            "FROM handoffs WHERE handoff_id = ?",
            (handoff_id,),
        ).fetchone()
        return dict(r) if r is not None else None
    finally:
        conn.close()


def count(factory, table: str) -> int:
    conn = factory.get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Pure domain unit tests
# --------------------------------------------------------------------------- #
def test_validate_target_and_visibility():
    assert validate_target({"strategy": "broadcast"})["strategy"] == "broadcast"
    assert validate_target({"strategy": "direct", "agent_id": "a"})["agent_id"] == "a"
    assert validate_target('{"strategy":"role","role":"builder"}')["role"] == "builder"
    assert normalize_visibility("Public") == "public"

    for bad in (
        None,
        "",
        {"strategy": "nope"},
        {"agent_id": "a"},
        {"strategy": "direct"},
    ):
        with pytest.raises(OktoNexusError) as ei:
            validate_target(bad)
        assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    for badvis in (None, "", "loud"):
        with pytest.raises(OktoNexusError) as ev:
            normalize_visibility(badvis)
        assert ev.value.code == ErrorCode.VALIDATION_ERROR.value


def test_is_direct_target_and_transitions():
    assert is_direct_target({"strategy": "direct", "agent_id": "a"}, "a") is True
    assert is_direct_target({"strategy": "direct", "agent_id": "a"}, "b") is False
    assert is_direct_target({"strategy": "broadcast"}, "a") is False
    assert is_direct_target('{"strategy":"direct","agent_id":"a"}', "a") is True
    assert is_direct_target("not-json", "a") is False

    assert can_transition(None, STATUS_OPEN) is True
    assert can_transition(STATUS_OPEN, STATUS_CLAIMED) is True
    assert can_transition(STATUS_OPEN, STATUS_CANCELLED) is True
    assert can_transition(STATUS_CLAIMED, STATUS_OPEN) is True
    assert can_transition(STATUS_CLAIMED, STATUS_COMPLETED) is True
    assert can_transition(STATUS_COMPLETED, STATUS_OPEN) is False
    assert can_transition(STATUS_OPEN, STATUS_COMPLETED) is False
    assert can_transition(STATUS_CLAIMED, STATUS_CANCELLED) is False
    assert can_transition(STATUS_CANCELLED, STATUS_OPEN) is False


# --------------------------------------------------------------------------- #
# FR0 / TS0 - workspace guard
# --------------------------------------------------------------------------- #
def test_workspace_required_and_unresolved(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    for missing in (None, "", "   "):
        with pytest.raises(OktoNexusError) as ei:
            svc.handoff_create(
                project_root=missing,
                from_agent_id="a",
                target={"strategy": "broadcast"},
                visibility="public",
            )
        assert ei.value.code == ErrorCode.WORKSPACE_REQUIRED.value

    with pytest.raises(OktoNexusError) as eu:
        svc.handoff_list_available(
            project_root=str(tmp_path / "nope" / "child"), agent_id="a"
        )
    assert eu.value.code == ErrorCode.WORKSPACE_UNRESOLVED.value


# --------------------------------------------------------------------------- #
# FR1 / FR2 / TS2 / TS3 - create
# --------------------------------------------------------------------------- #
def test_handoff_create_happy_and_event(migrated_factory, tmp_config, tmp_path):
    clock = StubClock("2026-06-07T00:00:00.000000Z")
    emitter = ThreadSafeEmitter()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=emitter)
    proj = str(mkdir(tmp_path, "P"))
    ws = seed_workspace(migrated_factory, proj, clock)

    out = svc.handoff_create(
        project_root=proj,
        from_agent_id="creator",
        target={"strategy": "direct", "agent_id": "worker"},
        visibility="eligible",
    )
    assert out["status"] == STATUS_OPEN
    assert out["workspace_id"] == ws
    assert out["handoff_id"]
    assert out["created_at"] == "2026-06-07T00:00:00.000000Z"

    assert row_of(migrated_factory, out["handoff_id"])["status"] == STATUS_OPEN
    assert len(emitter.events) == 1
    ev = emitter.events[-1]
    assert ev["type"] == "handoff.created"
    assert ev["event_id"] == 1
    assert ev["workspace_id"] == ws
    assert ev["payload"]["handoff_id"] == out["handoff_id"]


def test_handoff_create_validation(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, StubClock())

    with pytest.raises(OktoNexusError) as e1:
        svc.handoff_create(
            project_root=proj,
            from_agent_id="c",
            target={"strategy": "telepathy"},
            visibility="public",
        )
    assert e1.value.code == ErrorCode.VALIDATION_ERROR.value

    with pytest.raises(OktoNexusError) as e2:
        svc.handoff_create(
            project_root=proj,
            from_agent_id="c",
            target={"strategy": "broadcast"},
            visibility="loud",
        )
    assert e2.value.code == ErrorCode.VALIDATION_ERROR.value

    with pytest.raises(OktoNexusError) as e3:
        svc.handoff_create(
            project_root=proj,
            from_agent_id="",
            target={"strategy": "broadcast"},
            visibility="public",
        )
    assert e3.value.code == ErrorCode.VALIDATION_ERROR.value
    assert count(migrated_factory, "handoffs") == 0


def test_handoff_create_content_boundary_inclusive(
    migrated_factory, tmp_config, tmp_path
):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, StubClock())
    limit = tmp_config.max_inline_bytes  # 65536, inclusive

    ok = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "broadcast"},
        visibility="public",
        payload="x" * limit,  # exactly 65536 bytes -> accepted
    )
    assert ok["status"] == STATUS_OPEN

    with pytest.raises(OktoNexusError) as ei:
        svc.handoff_create(
            project_root=proj,
            from_agent_id="c",
            target={"strategy": "broadcast"},
            visibility="public",
            payload="x" * (limit + 1),  # 65537 -> rejected
        )
    assert ei.value.code == ErrorCode.CONTENT_TOO_LARGE.value
    assert count(migrated_factory, "handoffs") == 1  # the oversized one not persisted


# --------------------------------------------------------------------------- #
# FR3 / TS4 - list_available filtering + pagination + long-poll
# --------------------------------------------------------------------------- #
def test_list_available_visibility_and_eligibility(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    agents = FakeAgentRepo()
    agents.add("worker", capabilities=["py"])
    agents.add("other")  # registered so the direct target below passes D1b
    svc = make_service(migrated_factory, tmp_config, clock, agents=agents)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)

    # direct->worker, eligible visibility: visible+eligible to worker only.
    h_direct = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "direct", "agent_id": "worker"},
        visibility="eligible",
    )["handoff_id"]
    # broadcast public: visible+eligible to everyone.
    h_broadcast = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    # direct->other, public: worker can SEE it but is NOT eligible -> excluded.
    svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "direct", "agent_id": "other"},
        visibility="public",
    )

    res = svc.handoff_list_available(project_root=proj, agent_id="worker")
    ids = {h["handoff_id"] for h in res["handoffs"]}
    assert ids == {h_direct, h_broadcast}
    assert res["has_more"] is False
    assert res["next_cursor"] is None
    assert res["timed_out"] is False
    # target is returned as an object, not a JSON string.
    assert any(h["target"]["strategy"] == "broadcast" for h in res["handoffs"])

    # A stranger with no eligibility only sees the broadcast.
    res2 = svc.handoff_list_available(project_root=proj, agent_id="stranger")
    assert {h["handoff_id"] for h in res2["handoffs"]} == {h_broadcast}


def test_list_available_pagination(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    created = []
    for _ in range(5):
        created.append(
            svc.handoff_create(
                project_root=proj,
                from_agent_id="c",
                target={"strategy": "broadcast"},
                visibility="public",
            )["handoff_id"]
        )

    page1 = svc.handoff_list_available(project_root=proj, agent_id="w", limit=2)
    assert len(page1["handoffs"]) == 2
    assert page1["has_more"] is True
    assert page1["next_cursor"] == "2"

    page2 = svc.handoff_list_available(
        project_root=proj, agent_id="w", limit=2, cursor=page1["next_cursor"]
    )
    assert len(page2["handoffs"]) == 2
    assert page2["has_more"] is True

    page3 = svc.handoff_list_available(
        project_root=proj, agent_id="w", limit=2, cursor=page2["next_cursor"]
    )
    assert len(page3["handoffs"]) == 1
    assert page3["has_more"] is False
    assert page3["next_cursor"] is None

    seen = [
        h["handoff_id"]
        for h in page1["handoffs"] + page2["handoffs"] + page3["handoffs"]
    ]
    assert set(seen) == set(created) and len(seen) == 5

    with pytest.raises(OktoNexusError) as ei:
        svc.handoff_list_available(project_root=proj, agent_id="w", cursor="abc")
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    with pytest.raises(OktoNexusError) as el:
        svc.handoff_list_available(project_root=proj, agent_id="w", limit=0)
    assert el.value.code == ErrorCode.VALIDATION_ERROR.value


def test_list_available_long_poll_timeout(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)

    # No eligible handoffs + a timeout -> blocks until deadline -> timed_out.
    started = time.monotonic()
    res = svc.handoff_list_available(project_root=proj, agent_id="w", timeout_seconds=1)
    elapsed = time.monotonic() - started
    assert res["handoffs"] == []
    assert res["timed_out"] is True
    assert 0.5 <= elapsed < 5.0

    # No timeout -> single shot, not flagged as timed out.
    res0 = svc.handoff_list_available(project_root=proj, agent_id="w")
    assert res0["timed_out"] is False


# --------------------------------------------------------------------------- #
# list_available long-poll via the Waiter port (M5: blocking out of the
# application layer; re-scan only on a store change or a time boundary)
# --------------------------------------------------------------------------- #
def test_list_available_waiter_timeout_skips_rescan_when_no_change(
    migrated_factory, tmp_config, tmp_path
):
    # An idle wait answers the timeout WITHOUT re-running the availability
    # scan: one entry scan + one boundary probe, then a single full-window
    # wait - never a scan per poll interval.
    clock = StubClock()
    repo = CountingHandoffRepo(SqliteHandoffRepo(clock))
    waiter = ManualWaiter()
    svc = make_service(
        migrated_factory, tmp_config, clock, waiter=waiter, handoffs=repo
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)

    res = svc.handoff_list_available(project_root=proj, agent_id="w", timeout_seconds=5)
    assert res["timed_out"] is True and res["handoffs"] == []
    assert waiter.calls == [pytest.approx(5.0)]  # ONE full-window wait
    # OPEN is listed by the availability scan and the boundary probe, once each.
    assert repo.list_statuses.count(STATUS_OPEN) == 2


def test_list_available_wakes_on_store_change(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    proj_box: dict = {}

    class TriggerWaiter(ManualWaiter):
        def wait_for_change(self, since, timeout_s: float) -> bool:
            self.calls.append(timeout_s)
            self.t += min(0.2, timeout_s)
            proj_box["svc"].handoff_create(
                project_root=proj_box["proj"],
                from_agent_id="c",
                target={"strategy": "broadcast"},
                visibility="public",
            )
            return True

    waiter = TriggerWaiter()
    svc = make_service(migrated_factory, tmp_config, clock, waiter=waiter)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    proj_box.update(svc=svc, proj=proj)

    res = svc.handoff_list_available(
        project_root=proj, agent_id="w", timeout_seconds=10
    )
    assert res["timed_out"] is False
    assert len(res["handoffs"]) == 1  # the concurrent create woke the wait
    assert len(waiter.calls) == 1


def test_list_available_wakes_at_lease_expiry_boundary(migrated_factory, tmp_path):
    # A lease expiring produces NO write until a scan reopens it, so a purely
    # write-gated wait would sleep through it. The wait must cap its window at
    # the lease boundary and re-scan there (strict-expiry edge at poll cadence).
    config = NexusConfig(
        home_dir=tmp_path / "okto_home",
        handoff_lease_ttl_seconds=10,
        max_wait_timeout_seconds=60,
    )
    clock = StubClock()
    waiter = ClockAdvancingWaiter(clock)
    svc = make_service(migrated_factory, config, clock, waiter=waiter)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)

    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="w")

    res = svc.handoff_list_available(
        project_root=proj, agent_id="v", timeout_seconds=60
    )
    assert res["timed_out"] is False
    assert [h["handoff_id"] for h in res["handoffs"]] == [hid]  # reopened
    assert row_of(migrated_factory, hid)["status"] == STATUS_OPEN
    # First wait was capped at the LEASE boundary (10s), not the 60s budget;
    # the strict edge (== lease instant does not expire) re-checks briefly.
    assert waiter.calls[0] == pytest.approx(10.0)
    assert sum(waiter.calls) < 15  # woke at the boundary, nowhere near 60


def test_list_available_wakes_at_fallback_open_boundary(
    migrated_factory, tmp_config, tmp_path
):
    # direct_with_fallback widens its eligible set at created_at +
    # fallback_after_seconds with NO write: the wait must wake exactly there.
    clock = StubClock()
    waiter = ClockAdvancingWaiter(clock)
    svc = make_service(migrated_factory, tmp_config, clock, waiter=waiter)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)

    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={
            "strategy": "direct_with_fallback",
            "agent_id": "other",
            "fallback_after_seconds": 15,
        },
        visibility="public",
    )["handoff_id"]

    res = svc.handoff_list_available(
        project_root=proj, agent_id="w", timeout_seconds=30
    )
    assert res["timed_out"] is False
    assert [h["handoff_id"] for h in res["handoffs"]] == [hid]
    assert waiter.calls == [pytest.approx(15.0)]  # woke EXACTLY at the opening


# --------------------------------------------------------------------------- #
# FR4 / FR5 / TS5 / TS6 - claim
# --------------------------------------------------------------------------- #
def test_claim_happy(migrated_factory, tmp_config, tmp_path):
    clock = StubClock("2026-06-07T00:00:00.000000Z")
    emitter = ThreadSafeEmitter()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=emitter)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]

    out = svc.handoff_claim(
        project_root=proj, handoff_id=hid, agent_id="w", session_id="s1"
    )
    assert out["status"] == STATUS_CLAIMED
    assert out["claimed_by"] == "w"
    expected_lease = iso_plus(
        "2026-06-07T00:00:00.000000Z", tmp_config.handoff_lease_ttl_seconds
    )
    assert out["lease_expires_at"] == expected_lease
    assert emitter.types() == ["handoff.created", "handoff.claimed"]
    assert emitter.events[-1]["payload"]["claimed_session_id"] == "s1"


def test_claim_not_found_and_workspace_mismatch(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock)
    proj_a = str(mkdir(tmp_path, "A"))
    proj_b = str(mkdir(tmp_path, "B"))
    seed_workspace(migrated_factory, proj_a, clock)
    seed_workspace(migrated_factory, proj_b, clock)
    hid = svc.handoff_create(
        project_root=proj_a,
        from_agent_id="c",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]

    with pytest.raises(OktoNexusError) as e_nf:
        svc.handoff_claim(project_root=proj_a, handoff_id="ghost", agent_id="w")
    assert e_nf.value.code == ErrorCode.NOT_FOUND.value

    with pytest.raises(OktoNexusError) as e_wm:
        svc.handoff_claim(project_root=proj_b, handoff_id=hid, agent_id="w")
    assert e_wm.value.code == ErrorCode.WORKSPACE_MISMATCH.value


def test_claim_eligibility_gate(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    emitter = ThreadSafeEmitter()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=emitter)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    # Public visibility (stranger can SEE) but direct target -> not eligible.
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "direct", "agent_id": "worker"},
        visibility="public",
    )["handoff_id"]
    created_events = len(emitter.events)

    with pytest.raises(OktoNexusError) as ei:
        svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="stranger")
    assert ei.value.code == ErrorCode.NOT_ELIGIBLE_TO_CLAIM.value
    # No mutation, no event.
    assert row_of(migrated_factory, hid)["status"] == STATUS_OPEN
    assert row_of(migrated_factory, hid)["claimed_by"] is None
    assert len(emitter.events) == created_events


def test_double_claim_single_winner(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    emitter = ThreadSafeEmitter()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=emitter)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]

    agents = [f"agent-{i}" for i in range(6)]
    barrier = threading.Barrier(len(agents))
    lock = threading.Lock()
    winners: list[dict] = []
    losers: list[str] = []

    def worker(agent):
        barrier.wait()
        try:
            # No retry wrapper: BEGIN IMMEDIATE serialises the writers, so a
            # loser must get the clean business error - never a DB_ERROR.
            out = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id=agent)
            with lock:
                winners.append(out)
        except OktoNexusError as exc:
            with lock:
                losers.append(exc.code)

    with ThreadPoolExecutor(max_workers=len(agents)) as ex:
        for f in [ex.submit(worker, a) for a in agents]:
            f.result()

    assert len(winners) == 1
    assert winners[0]["status"] == STATUS_CLAIMED
    assert len(losers) == len(agents) - 1
    assert set(losers) == {ErrorCode.HANDOFF_ALREADY_CLAIMED.value}
    # Exactly one claim event (plus the single create event).
    assert emitter.types().count("handoff.claimed") == 1
    assert row_of(migrated_factory, hid)["status"] == STATUS_CLAIMED


def test_two_thread_claim_race_loser_gets_business_error_not_db_error(
    migrated_factory, tmp_config, tmp_path
):
    # Core M1 contract: two writers disputing one claim, NO retry compensation.
    # One wins; the other receives the clean business error (and never an
    # opaque DB_ERROR from WAL snapshot/busy contention).
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]

    barrier = threading.Barrier(2)
    outcomes: dict[str, object] = {}
    lock = threading.Lock()

    def worker(agent):
        barrier.wait()
        try:
            out = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id=agent)
            with lock:
                outcomes[agent] = out
        except OktoNexusError as exc:
            with lock:
                outcomes[agent] = exc

    with ThreadPoolExecutor(max_workers=2) as ex:
        for f in [ex.submit(worker, a) for a in ("racer-1", "racer-2")]:
            f.result()

    wins = [v for v in outcomes.values() if isinstance(v, dict)]
    errors = [v for v in outcomes.values() if isinstance(v, OktoNexusError)]
    assert len(wins) == 1 and len(errors) == 1
    loser = errors[0]
    assert loser.code == ErrorCode.HANDOFF_ALREADY_CLAIMED.value
    assert loser.code != ErrorCode.DB_ERROR.value
    assert row_of(migrated_factory, hid)["claimed_by"] == wins[0]["claimed_by"]


def test_complete_by_non_claimant_names_the_claimant(
    migrated_factory, tmp_config, tmp_path
):
    # The precise NOT_OWNER error now reports WHO holds the claim, so an agent
    # knows the handoff is alive under another worker (not lost).
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="owner")

    with pytest.raises(OktoNexusError) as ei:
        svc.handoff_complete(project_root=proj, handoff_id=hid, agent_id="intruder")
    assert ei.value.code == ErrorCode.NOT_OWNER.value
    assert ei.value.details["claimed_by"] == "owner"
    assert ei.value.details["agent_id"] == "intruder"
    # The conditional UPDATE must not have clobbered the row.
    r = row_of(migrated_factory, hid)
    assert r["status"] == STATUS_CLAIMED and r["claimed_by"] == "owner"


def test_complete_after_lease_expiry_reopen_precise_error(
    migrated_factory, tmp_config, tmp_path
):
    # An owner whose lease expired (handoff reopened to OPEN) gets a precise,
    # prescriptive INVALID_TRANSITION pointing at handoff_claim - not NOT_FOUND,
    # not an accidental overwrite of the reopened row.
    clock = StubClock("2026-06-07T00:00:00.000000Z")
    svc = make_service(migrated_factory, tmp_config, clock)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    claim = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="a1")
    clock.set(iso_plus(claim["lease_expires_at"], 5))
    assert svc.expire_old_leases(project_root=proj)["expired"] == [hid]

    with pytest.raises(OktoNexusError) as ei:
        svc.handoff_complete(project_root=proj, handoff_id=hid, agent_id="a1")
    assert ei.value.code == ErrorCode.INVALID_TRANSITION.value
    assert ei.value.details["status"] == STATUS_OPEN
    assert "lease" in ei.value.message
    assert "handoff_claim" in ei.value.message
    # The reopened row stays OPEN and claimable.
    assert row_of(migrated_factory, hid)["status"] == STATUS_OPEN


def test_repo_transition_claimed_is_conditional_on_claimant(
    migrated_factory, tmp_config, tmp_path
):
    # Negative wiring: the repo-level terminal transition affects 0 rows when
    # the claimant does not match (the old unconditional UPDATE would have
    # completed the handoff on behalf of the wrong agent).
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock)
    repo = SqliteHandoffRepo(clock)
    proj = str(mkdir(tmp_path, "P"))
    ws = seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="owner")

    with migrated_factory.unit_of_work() as uow:
        denied = repo.transition_claimed(
            uow,
            workspace_id=ws,
            handoff_id=hid,
            claimed_by="not-the-owner",
            status=STATUS_COMPLETED,
        )
    assert denied is None
    r = row_of(migrated_factory, hid)
    assert r["status"] == STATUS_CLAIMED and r["claimed_by"] == "owner"

    with migrated_factory.unit_of_work() as uow:
        done = repo.transition_claimed(
            uow,
            workspace_id=ws,
            handoff_id=hid,
            claimed_by="owner",
            status=STATUS_COMPLETED,
        )
    assert done is not None and done.status == STATUS_COMPLETED
    assert row_of(migrated_factory, hid)["status"] == STATUS_COMPLETED


def test_repo_reject_open_is_conditional_on_open_status(
    migrated_factory, tmp_config, tmp_path
):
    # reject_open must affect 0 rows once the handoff is CLAIMED (a racing
    # direct-target reject cannot yank work from under the claimant).
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock)
    repo = SqliteHandoffRepo(clock)
    proj = str(mkdir(tmp_path, "P"))
    ws = seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "direct", "agent_id": "worker"},
        visibility="public",
    )["handoff_id"]
    svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="worker")

    with migrated_factory.unit_of_work() as uow:
        denied = repo.reject_open(uow, workspace_id=ws, handoff_id=hid)
    assert denied is None
    assert row_of(migrated_factory, hid)["status"] == STATUS_CLAIMED


# --------------------------------------------------------------------------- #
# FR7 / TS8 / TS9 - lease expiry boundary + re-claim
# --------------------------------------------------------------------------- #
def test_lease_expiry_strict_boundary_and_reclaim(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock("2026-06-07T00:00:00.000000Z")
    emitter = ThreadSafeEmitter()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=emitter)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    claim = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="a1")
    lease = claim["lease_expires_at"]

    # At lease_expires_at == now: NOT expired (strict threshold).
    clock.set(lease)
    res = svc.expire_old_leases(project_root=proj)
    assert res["expired"] == []
    assert row_of(migrated_factory, hid)["status"] == STATUS_CLAIMED

    # One second past the lease: expired -> reopened to OPEN, claim fields cleared.
    clock.set(iso_plus(lease, 1))
    res2 = svc.expire_old_leases(project_root=proj)
    assert res2["expired"] == [hid]
    r = row_of(migrated_factory, hid)
    assert r["status"] == STATUS_OPEN
    assert r["claimed_by"] is None
    assert r["lease_expires_at"] is None
    assert "handoff.expired" in emitter.types()

    # Re-claim by a new agent succeeds (OPEN -> CLAIMED) and emits handoff.claimed.
    reclaim = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="a2")
    assert reclaim["status"] == STATUS_CLAIMED
    assert reclaim["claimed_by"] == "a2"
    assert emitter.types().count("handoff.claimed") == 2


def test_list_available_expires_before_serving(migrated_factory, tmp_config, tmp_path):
    clock = StubClock("2026-06-07T00:00:00.000000Z")
    emitter = ThreadSafeEmitter()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=emitter)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    claim = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="a1")

    # Before expiry the handoff is CLAIMED -> not in the available list.
    assert (
        svc.handoff_list_available(project_root=proj, agent_id="a2")["handoffs"] == []
    )

    # After expiry, list_available runs expire first and surfaces the reopened OPEN handoff.
    clock.set(iso_plus(claim["lease_expires_at"], 5))
    res = svc.handoff_list_available(project_root=proj, agent_id="a2")
    assert {h["handoff_id"] for h in res["handoffs"]} == {hid}
    assert "handoff.expired" in emitter.types()


# --------------------------------------------------------------------------- #
# FR8 / FR9 / FR10 / TS10 / TS11 / TS12 - complete / reject / transitions
# --------------------------------------------------------------------------- #
def _open_and_claim(svc, migrated_factory, proj, clock, target=None, claimer="a1"):
    target = target or {"strategy": "broadcast"}
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target=target,
        visibility="public",
    )["handoff_id"]
    svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id=claimer)
    return hid


def test_complete_owner_nonowner_invalid(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    emitter = ThreadSafeEmitter()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=emitter)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)

    hid = _open_and_claim(svc, migrated_factory, proj, clock, claimer="owner")
    # non-owner -> NOT_OWNER
    with pytest.raises(OktoNexusError) as e_no:
        svc.handoff_complete(project_root=proj, handoff_id=hid, agent_id="intruder")
    assert e_no.value.code == ErrorCode.NOT_OWNER.value
    # owner completes -> COMPLETED + event
    out = svc.handoff_complete(project_root=proj, handoff_id=hid, agent_id="owner")
    assert out["status"] == STATUS_COMPLETED
    assert emitter.types()[-1] == "handoff.completed"
    # complete again on a terminal/non-CLAIMED state -> INVALID_TRANSITION
    with pytest.raises(OktoNexusError) as e_it:
        svc.handoff_complete(project_root=proj, handoff_id=hid, agent_id="owner")
    assert e_it.value.code == ErrorCode.INVALID_TRANSITION.value

    # complete on an OPEN (unclaimed) handoff -> INVALID_TRANSITION
    open_hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    with pytest.raises(OktoNexusError) as e_open:
        svc.handoff_complete(project_root=proj, handoff_id=open_hid, agent_id="anyone")
    assert e_open.value.code == ErrorCode.INVALID_TRANSITION.value


def test_reject_owner_and_direct_target(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    emitter = ThreadSafeEmitter()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=emitter)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)

    # owner rejects a CLAIMED handoff -> REJECTED
    hid = _open_and_claim(svc, migrated_factory, proj, clock, claimer="owner")
    out = svc.handoff_reject(
        project_root=proj, handoff_id=hid, agent_id="owner", reason="busy"
    )
    assert out["status"] == STATUS_REJECTED
    assert emitter.types()[-1] == "handoff.rejected"

    # direct target rejects an OPEN handoff before claim -> OPEN -> REJECTED
    direct_hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "direct", "agent_id": "worker"},
        visibility="eligible",
    )["handoff_id"]
    out2 = svc.handoff_reject(
        project_root=proj, handoff_id=direct_hid, agent_id="worker"
    )
    assert out2["status"] == STATUS_REJECTED

    # non-owner / non-direct rejecting an OPEN handoff -> NOT_OWNER
    open_hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "direct", "agent_id": "worker"},
        visibility="public",
    )["handoff_id"]
    with pytest.raises(OktoNexusError) as e_no:
        svc.handoff_reject(project_root=proj, handoff_id=open_hid, agent_id="stranger")
    assert e_no.value.code == ErrorCode.NOT_OWNER.value

    # rejecting a CLAIMED handoff by a non-owner -> NOT_OWNER
    claimed_hid = _open_and_claim(svc, migrated_factory, proj, clock, claimer="owner2")
    with pytest.raises(OktoNexusError) as e_no2:
        svc.handoff_reject(project_root=proj, handoff_id=claimed_hid, agent_id="other")
    assert e_no2.value.code == ErrorCode.NOT_OWNER.value


def test_reject_terminal_is_invalid_transition(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = _open_and_claim(svc, migrated_factory, proj, clock, claimer="owner")
    svc.handoff_complete(project_root=proj, handoff_id=hid, agent_id="owner")
    with pytest.raises(OktoNexusError) as ei:
        svc.handoff_reject(project_root=proj, handoff_id=hid, agent_id="owner")
    assert ei.value.code == ErrorCode.INVALID_TRANSITION.value


# --------------------------------------------------------------------------- #
# FR0 / TS1 - cross-workspace isolation
# --------------------------------------------------------------------------- #
def test_cross_workspace_isolation(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock)
    proj_a = str(mkdir(tmp_path, "A"))
    proj_b = str(mkdir(tmp_path, "B"))
    seed_workspace(migrated_factory, proj_a, clock)
    seed_workspace(migrated_factory, proj_b, clock)
    hid = svc.handoff_create(
        project_root=proj_a,
        from_agent_id="c",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]

    # The handoff never appears in another workspace's listing.
    assert (
        svc.handoff_list_available(project_root=proj_b, agent_id="w")["handoffs"] == []
    )
    # And cannot be completed/rejected from another workspace.
    with pytest.raises(OktoNexusError) as ei:
        svc.handoff_complete(project_root=proj_b, handoff_id=hid, agent_id="w")
    assert ei.value.code == ErrorCode.WORKSPACE_MISMATCH.value


# --------------------------------------------------------------------------- #
# D1b at handoff_create: direct -> unknown agent is a hard NOT_FOUND with full
# rollback; a pool target matching zero agents is success-with-warning
# --------------------------------------------------------------------------- #
def test_create_direct_unknown_agent_not_found_nothing_persists(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    emitter = ThreadSafeEmitter()
    svc = make_service(
        migrated_factory, tmp_config, clock, emitter=emitter, agents=FakeAgentRepo()
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)

    with pytest.raises(OktoNexusError) as ei:
        svc.handoff_create(
            project_root=proj,
            from_agent_id="c",
            target={"strategy": "direct", "agent_id": "ghost"},
            visibility="public",
        )
    assert ei.value.code == ErrorCode.NOT_FOUND.value
    # Prescriptive: points at agent_list / registration / the fallback escape.
    assert "agent_list" in ei.value.message
    assert "direct_with_fallback" in ei.value.message
    # Full rollback: no row, no event.
    assert count(migrated_factory, "handoffs") == 0
    assert emitter.events == []


def test_create_pool_zero_match_succeeds_with_warning(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        emitter=ThreadSafeEmitter(),
        agents=FakeAgentRepo(),  # nobody registered
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)

    out = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "capability", "capability": "ocr"},
        visibility="public",
    )
    assert out["status"] == STATUS_OPEN
    assert out["eligible_count"] == 0
    assert "warning" in out  # never a silent zero-match (S2)
    assert "handoff_cancel" in out["warning"]
    # The handoff persists: a later registrant may still claim it.
    assert row_of(migrated_factory, out["handoff_id"])["status"] == STATUS_OPEN


def test_create_direct_registered_agent_no_warning(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    agents = FakeAgentRepo()
    agents.add("worker")
    svc = make_service(migrated_factory, tmp_config, clock, agents=agents)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)

    out = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "direct", "agent_id": "worker"},
        visibility="public",
    )
    assert out["status"] == STATUS_OPEN
    assert "warning" not in out


def test_create_pool_with_match_reports_eligible_count(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    agents = FakeAgentRepo()
    agents.add("w1", capabilities={"ocr": True})
    agents.add("w2", capabilities={"ocr": True})
    agents.add("bystander")
    svc = make_service(migrated_factory, tmp_config, clock, agents=agents)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)

    out = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "capability", "capability": "ocr"},
        visibility="public",
    )
    assert out["eligible_count"] == 2
    assert "warning" not in out


def test_create_direct_with_fallback_unknown_agent_warns_not_errors(
    migrated_factory, tmp_config, tmp_path
):
    # direct_with_fallback is the sanctioned path for an agent that registers
    # LATER: an unknown agent_id is a zero-match warning, never NOT_FOUND.
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock, agents=FakeAgentRepo())
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)

    out = svc.handoff_create(
        project_root=proj,
        from_agent_id="c",
        target={
            "strategy": "direct_with_fallback",
            "agent_id": "late-joiner",
            "fallback_after_seconds": 30,
        },
        visibility="public",
    )
    assert out["status"] == STATUS_OPEN
    assert out["eligible_count"] == 0
    assert "warning" in out


# --------------------------------------------------------------------------- #
# handoff_cancel: creator-only, OPEN-only, terminal afterwards
# --------------------------------------------------------------------------- #
def test_cancel_by_creator_cancels_and_disappears(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    emitter = ThreadSafeEmitter()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=emitter)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="creator",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    assert (
        len(svc.handoff_list_available(project_root=proj, agent_id="w")["handoffs"])
        == 1
    )

    out = svc.handoff_cancel(
        project_root=proj, handoff_id=hid, agent_id="creator", reason="mistake"
    )
    assert out == {"handoff_id": hid, "status": STATUS_CANCELLED}
    assert row_of(migrated_factory, hid)["status"] == STATUS_CANCELLED
    assert emitter.types()[-1] == "handoff.cancelled"
    assert emitter.events[-1]["payload"]["reason"] == "mistake"
    # The cancelled handoff leaves the claimable pool.
    assert svc.handoff_list_available(project_root=proj, agent_id="w")["handoffs"] == []


def test_cancel_by_non_creator_is_not_owner(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="creator",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]

    with pytest.raises(OktoNexusError) as ei:
        svc.handoff_cancel(project_root=proj, handoff_id=hid, agent_id="intruder")
    assert ei.value.code == ErrorCode.NOT_OWNER.value
    assert ei.value.details["from_agent_id"] == "creator"
    assert row_of(migrated_factory, hid)["status"] == STATUS_OPEN  # untouched


def test_cancel_claimed_is_invalid_transition(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="creator",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="worker")

    with pytest.raises(OktoNexusError) as ei:
        svc.handoff_cancel(project_root=proj, handoff_id=hid, agent_id="creator")
    assert ei.value.code == ErrorCode.INVALID_TRANSITION.value
    # Prescriptive: a CLAIMED handoff is the claimant's to resolve.
    assert "handoff_complete" in ei.value.message
    assert "lease" in ei.value.message
    assert row_of(migrated_factory, hid)["status"] == STATUS_CLAIMED


def test_cancel_after_lease_expiry_succeeds(migrated_factory, tmp_config, tmp_path):
    # An expired claim lease reopens the handoff; the creator may then cancel.
    clock = StubClock("2026-06-07T00:00:00.000000Z")
    svc = make_service(migrated_factory, tmp_config, clock)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="creator",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    claim = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="worker")
    clock.set(iso_plus(claim["lease_expires_at"], 5))

    out = svc.handoff_cancel(project_root=proj, handoff_id=hid, agent_id="creator")
    assert out["status"] == STATUS_CANCELLED


def test_cancelled_is_terminal_for_reject_complete_claim_and_cancel(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="creator",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    svc.handoff_cancel(project_root=proj, handoff_id=hid, agent_id="creator")
    assert STATUS_CANCELLED in TERMINAL_STATUSES

    with pytest.raises(OktoNexusError) as e_rej:
        svc.handoff_reject(project_root=proj, handoff_id=hid, agent_id="creator")
    assert e_rej.value.code == ErrorCode.INVALID_TRANSITION.value

    with pytest.raises(OktoNexusError) as e_cmp:
        svc.handoff_complete(project_root=proj, handoff_id=hid, agent_id="creator")
    assert e_cmp.value.code == ErrorCode.INVALID_TRANSITION.value

    with pytest.raises(OktoNexusError) as e_clm:
        svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="w")
    assert e_clm.value.code == ErrorCode.HANDOFF_ALREADY_CLAIMED.value

    with pytest.raises(OktoNexusError) as e_cxl:
        svc.handoff_cancel(project_root=proj, handoff_id=hid, agent_id="creator")
    assert e_cxl.value.code == ErrorCode.INVALID_TRANSITION.value


# --------------------------------------------------------------------------- #
# TS13 - atomic events / monotonic event_id under concurrent writers
# --------------------------------------------------------------------------- #
def test_concurrent_creates_unique_monotonic_events(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    emitter = ThreadSafeEmitter()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=emitter)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    n = 12
    barrier = threading.Barrier(n)

    def worker():
        barrier.wait()
        # Direct call (no retry): concurrent writers serialise at BEGIN
        # IMMEDIATE instead of failing with BUSY_SNAPSHOT mid-transaction.
        svc.handoff_create(
            project_root=proj,
            from_agent_id="c",
            target={"strategy": "broadcast"},
            visibility="public",
        )

    with ThreadPoolExecutor(max_workers=n) as ex:
        for f in [ex.submit(worker) for _ in range(n)]:
            f.result()

    assert count(migrated_factory, "handoffs") == n  # zero lost writes
    ids = [e["event_id"] for e in emitter.events]
    assert len(ids) == n
    assert len(set(ids)) == n  # unique
    assert ids == sorted(ids)  # monotonic
    assert all(t == "handoff.created" for t in emitter.types())


# --------------------------------------------------------------------------- #
# MCP tool registration + canonical envelope (no exception escapes)
# --------------------------------------------------------------------------- #
def test_register_tools_and_envelope(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    deps = make_deps(migrated_factory, tmp_config, clock, emitter=ThreadSafeEmitter())
    server = FakeServer()
    register(server, deps)
    assert set(server.tools) == {
        "handoff_create",
        "handoff_list_available",
        "handoff_claim",
        "handoff_complete",
        "handoff_verify",
        "handoff_reject",
        "handoff_cancel",
        "handoff_get",
    }
    assert deps.repos.handoffs is not None
    assert deps.repos.messages is not None
    assert deps.repos.deliveries is not None

    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)

    created = server.tools["handoff_create"](
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "broadcast"},
        visibility="public",
        payload="please process batch 7",
    )
    assert created["ok"] is True
    hid = created["data"]["handoff_id"]

    listed = server.tools["handoff_list_available"](project_root=proj, agent_id="w")
    assert listed["ok"] is True
    assert {h["handoff_id"] for h in listed["data"]["handoffs"]} == {hid}
    assert "payload" not in listed["data"]["handoffs"][0]

    claimed = server.tools["handoff_claim"](
        project_root=proj, handoff_id=hid, agent_id="w"
    )
    assert claimed["ok"] is True and claimed["data"]["status"] == STATUS_CLAIMED
    assert claimed["data"]["payload"] == "please process batch 7"

    completed = server.tools["handoff_complete"](
        project_root=proj, handoff_id=hid, agent_id="w", result="done: 7/7"
    )
    assert completed["ok"] is True and completed["data"]["status"] == STATUS_COMPLETED

    # handoff_get reads the terminal outcome through the full MCP path.
    got = server.tools["handoff_get"](project_root=proj, handoff_id=hid, agent_id="c")
    assert got["ok"] is True
    assert got["data"]["status"] == STATUS_COMPLETED
    assert got["data"]["result"] == "done: 7/7"

    # handoff_cancel through the envelope (creator retracts a fresh handoff).
    fresh = server.tools["handoff_create"](
        project_root=proj,
        from_agent_id="c",
        target={"strategy": "broadcast"},
        visibility="public",
    )
    cancelled = server.tools["handoff_cancel"](
        project_root=proj, handoff_id=fresh["data"]["handoff_id"], agent_id="c"
    )
    assert cancelled["ok"] is True
    assert cancelled["data"]["status"] == STATUS_CANCELLED

    # Failures are surfaced as envelopes, never raised.
    missing_ws = server.tools["handoff_claim"](
        project_root="", handoff_id=hid, agent_id="w"
    )
    assert missing_ws["ok"] is False
    assert missing_ws["error"]["code"] == "WORKSPACE_REQUIRED"

    not_found = server.tools["handoff_claim"](
        project_root=proj, handoff_id="ghost", agent_id="w"
    )
    assert not_found["ok"] is False
    assert not_found["error"]["code"] == "NOT_FOUND"


def test_build_service_reuses_existing_repos(migrated_factory, tmp_config):
    clock = StubClock()
    deps = make_deps(migrated_factory, tmp_config, clock)
    existing = SqliteHandoffRepo(clock)
    deps.repos.handoffs = existing
    build_service(deps)
    assert deps.repos.handoffs is existing  # not overwritten
    assert deps.repos.agents is not None  # filled in
    assert deps.repos.messages is not None  # filled in (notification lane)
    assert deps.repos.deliveries is not None  # filled in (notification lane)


# --------------------------------------------------------------------------- #
# Handoff payload passthrough (migration 003) - returned to the claimant only
# --------------------------------------------------------------------------- #
def test_migration_003_adds_payload_column_idempotently(migrated_factory):
    # The payload column comes from migration 003, and re-applying is a no-op
    # (no 'duplicate column name', nothing newly applied).
    from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner

    conn = migrated_factory.get_connection()
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(handoffs)").fetchall()}
        migs = {
            r[0]
            for r in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
    finally:
        conn.close()
    assert "payload" in cols
    assert 3 in migs  # the column is attributable to migration 003
    assert MigrationRunner(migrated_factory).apply() == []  # idempotent re-run


def test_migrations_ship_inside_the_okto_nexus_package():
    # Migrations are package-data: the discovered dir must live UNDER the
    # okto_nexus package (so a non-editable wheel install finds them), not at the
    # repo root. Guards against moving migrations/ back outside the package.
    from pathlib import Path

    import okto_nexus
    from okto_nexus.adapters.outbound.sqlite.migrations import _default_migrations_dir

    mig = _default_migrations_dir()
    pkg = Path(okto_nexus.__file__).resolve().parent
    assert mig == pkg / "migrations"
    assert any(mig.glob("[0-9]*_*.sql"))


def test_handoff_claim_touches_claimer_last_seen(
    migrated_factory, tmp_config, tmp_path
):
    # Claiming a handoff stamps the claimer's last_seen_at (via the actor touch).
    clock = StubClock()
    agents = FakeAgentRepo()
    agents.add("worker")
    svc = make_service(
        migrated_factory, tmp_config, clock, emitter=ThreadSafeEmitter(), agents=agents
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="boss",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]

    assert agents.get(None, "worker").last_seen_at is None  # not acted yet
    svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="worker")
    assert agents.get(None, "worker").last_seen_at == clock.now_iso()


def test_handoff_create_touches_author_last_seen_real_repo(
    migrated_factory, tmp_config, tmp_path
):
    # The touch commits in the SAME SQLite transaction as the handoff mutation
    # (real SqliteAgentRepo over migrated_factory, not the in-memory fake).
    clock = StubClock()
    agents = SqliteAgentRepo(clock)
    svc = make_service(
        migrated_factory, tmp_config, clock, emitter=ThreadSafeEmitter(), agents=agents
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    with migrated_factory.unit_of_work() as uow:
        agents.upsert(uow, agent_id="boss")

    svc.handoff_create(
        project_root=proj,
        from_agent_id="boss",
        target={"strategy": "broadcast"},
        visibility="public",
    )
    with migrated_factory.unit_of_work() as uow:
        assert agents.get(uow, "boss").last_seen_at == clock.now_iso()


def test_payload_is_hidden_from_list_and_returned_by_claim(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    agents = FakeAgentRepo()
    agents.add("worker", capabilities={"ocr": True})
    svc = make_service(
        migrated_factory, tmp_config, clock, emitter=ThreadSafeEmitter(), agents=agents
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)

    body = '{"file":"scan.pdf","pages":12}'
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="boss",
        target={"strategy": "capability", "capability": "ocr"},
        visibility="eligible",
        payload=body,
    )["handoff_id"]

    listed = svc.handoff_list_available(project_root=proj, agent_id="worker")
    assert len(listed["handoffs"]) == 1
    assert "payload" not in listed["handoffs"][0]

    # The worker gets the payload only after winning the claim.
    claimed = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="worker")
    assert claimed["payload"] == body


def test_payload_none_stays_none(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        emitter=ThreadSafeEmitter(),
        agents=FakeAgentRepo(),
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="boss",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]

    listed = svc.handoff_list_available(project_root=proj, agent_id="w")
    assert "payload" not in listed["handoffs"][0]
    claimed = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="w")
    assert claimed["payload"] is None


def test_payload_object_is_serialized_to_json_text(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        emitter=ThreadSafeEmitter(),
        agents=FakeAgentRepo(),
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="boss",
        target={"strategy": "broadcast"},
        visibility="public",
        payload={"k": "v", "n": 3},
    )["handoff_id"]

    claimed = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="w")
    # Opaque on read-back: returned as the stored JSON TEXT, not re-parsed.
    assert isinstance(claimed["payload"], str)
    assert json.loads(claimed["payload"]) == {"k": "v", "n": 3}


def test_payload_consistent_between_event_and_claim(
    migrated_factory, tmp_config, tmp_path
):
    # A non-string payload is serialized for the claimant, while public events
    # remain metadata-only.
    clock = StubClock()
    emitter = ThreadSafeEmitter()
    svc = make_service(
        migrated_factory, tmp_config, clock, emitter=emitter, agents=FakeAgentRepo()
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="b",
        target={"strategy": "broadcast"},
        visibility="public",
        payload={"k": "v"},
    )["handoff_id"]
    claimed = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="w")
    created = [e for e in emitter.events if e["type"] == "handoff.created"]
    assert "payload" not in created[0]["payload"]
    assert claimed["payload"] == '{"k": "v"}'


def test_payload_large_round_trips_at_boundary(migrated_factory, tmp_config, tmp_path):
    # The feature is passthrough: a payload at the 64KB inclusive limit must come
    # back byte-for-byte through claim (not just pass the size gate).
    clock = StubClock()
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        emitter=ThreadSafeEmitter(),
        agents=FakeAgentRepo(),
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    big = "x" * tmp_config.max_inline_bytes
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="b",
        target={"strategy": "broadcast"},
        visibility="public",
        payload=big,
    )["handoff_id"]
    listed = svc.handoff_list_available(project_root=proj, agent_id="w")
    claimed = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="w")
    assert "payload" not in listed["handoffs"][0]
    assert claimed["payload"] == big
    assert len(claimed["payload"]) == tmp_config.max_inline_bytes


def test_payload_unicode_round_trips(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        emitter=ThreadSafeEmitter(),
        agents=FakeAgentRepo(),
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    text = "relatório café ☕ 文件"  # accents + emoji + CJK
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="b",
        target={"strategy": "broadcast"},
        visibility="public",
        payload=text,
    )["handoff_id"]
    assert (
        svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="w")["payload"]
        == text
    )  # same code points, no \\uXXXX escaping

    # An object with non-ASCII values is stored as UTF-8 JSON, not ASCII-escaped.
    hid2 = svc.handoff_create(
        project_root=proj,
        from_agent_id="b",
        target={"strategy": "broadcast"},
        visibility="public",
        payload={"nota": "café ☕"},
    )["handoff_id"]
    body2 = svc.handoff_claim(project_root=proj, handoff_id=hid2, agent_id="w")[
        "payload"
    ]
    assert json.loads(body2) == {"nota": "café ☕"}
    assert "\\u" not in body2  # ensure_ascii=False preserved the characters


def test_payload_empty_string_preserved_not_null(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        emitter=ThreadSafeEmitter(),
        agents=FakeAgentRepo(),
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="b",
        target={"strategy": "broadcast"},
        visibility="public",
        payload="",
    )["handoff_id"]
    claimed = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="w")
    assert claimed["payload"] == ""  # empty string preserved, distinct from None
    assert claimed["payload"] is not None


def test_legacy_row_backfills_to_null_payload(tmp_path):
    # A handoff row that existed BEFORE migration 003 (no payload column) reads
    # back with payload=None after the ALTER ADD COLUMN backfills NULL.
    import shutil

    from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
    from okto_nexus.adapters.outbound.sqlite.migrations import (
        MigrationRunner,
        _default_migrations_dir,
    )
    from okto_nexus.config import NexusConfig

    real_dir = _default_migrations_dir()
    partial = tmp_path / "migs_partial"
    partial.mkdir()
    for f in real_dir.glob("00[12]_*.sql"):
        shutil.copy(f, partial)

    config = NexusConfig(home_dir=tmp_path / "home")
    factory = ConnectionFactory(config)
    MigrationRunner(factory, migrations_dir=partial).apply()  # 001 + 002 only

    clock = StubClock()
    ws = seed_workspace(factory, str(mkdir(tmp_path, "P")), clock)
    conn = factory.get_connection()
    try:
        conn.execute("BEGIN")
        conn.execute(
            "INSERT INTO handoffs (handoff_id, workspace_id, status, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("hof_legacy", ws, STATUS_OPEN, "2026-06-07T00:00:00.000000Z"),
        )
        conn.execute("COMMIT")
    finally:
        conn.close()

    # Apply the full set: 003 adds the column and backfills the legacy row NULL.
    assert 3 in MigrationRunner(factory).apply()
    repo = SqliteHandoffRepo(clock)
    with factory.unit_of_work() as uow:
        row = repo.get(uow, workspace_id=ws, handoff_id="hof_legacy")
    assert row is not None and row.payload is None


# --------------------------------------------------------------------------- #
# Outcome persistence (migration 008) + handoff_get
# --------------------------------------------------------------------------- #
def make_real_world(migrated_factory, clock):
    """Real repos for the cross-slice tests: agents + messages + deliveries."""
    return (
        SqliteAgentRepo(clock),
        SqliteMessageRepo(clock),
        SqliteMessageDeliveryRepo(clock),
    )


def register_real_agent(factory, agents, agent_id, role=None, capabilities=None):
    with factory.unit_of_work() as uow:
        agents.upsert(uow, agent_id=agent_id, role=role, capabilities=capabilities)


def inbox_for(factory, clock):
    return InboxService(
        connection_factory=factory,
        deliveries=SqliteMessageDeliveryRepo(clock),
        messages=SqliteMessageRepo(clock),
        clock=clock,
    )


def test_migration_008_adds_outcome_columns(migrated_factory):
    from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner

    conn = migrated_factory.get_connection()
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(handoffs)").fetchall()}
        migs = {
            r[0]
            for r in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
    finally:
        conn.close()
    assert {"result", "rejected_reason"} <= cols
    assert 8 in migs
    assert MigrationRunner(migrated_factory).apply() == []  # idempotent re-run


def test_complete_persists_result_and_handoff_get_returns_it(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="creator",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="worker")
    result = '{"pages": 12, "ok": true}'
    svc.handoff_complete(
        project_root=proj, handoff_id=hid, agent_id="worker", result=result
    )

    got = svc.handoff_get(project_root=proj, handoff_id=hid, agent_id="creator")
    assert got["status"] == STATUS_COMPLETED
    assert got["result"] == result  # byte-for-byte (string stored verbatim)
    assert got["rejected_reason"] is None
    assert got["claimed_by"] == "worker"
    assert got["from_agent_id"] == "creator"


def test_complete_serializes_non_string_result_to_json_text(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="creator",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="worker")
    svc.handoff_complete(
        project_root=proj,
        handoff_id=hid,
        agent_id="worker",
        result={"nota": "café ☕"},
    )
    got = svc.handoff_get(project_root=proj, handoff_id=hid, agent_id="worker")
    assert isinstance(got["result"], str)  # opaque JSON TEXT, like payload
    assert json.loads(got["result"]) == {"nota": "café ☕"}
    assert "\\u" not in got["result"]  # ensure_ascii=False


def test_reject_persists_reason_and_handoff_get_returns_it(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="creator",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="worker")
    svc.handoff_reject(
        project_root=proj, handoff_id=hid, agent_id="worker", reason="out of scope"
    )
    got = svc.handoff_get(project_root=proj, handoff_id=hid, agent_id="creator")
    assert got["status"] == STATUS_REJECTED
    assert got["rejected_reason"] == "out of scope"
    assert got["result"] is None


def test_reject_open_by_direct_target_persists_reason(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    agents = FakeAgentRepo()
    agents.add("worker")
    svc = make_service(migrated_factory, tmp_config, clock, agents=agents)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="creator",
        target={"strategy": "direct", "agent_id": "worker"},
        visibility="public",
    )["handoff_id"]
    svc.handoff_reject(
        project_root=proj, handoff_id=hid, agent_id="worker", reason="busy"
    )
    got = svc.handoff_get(project_root=proj, handoff_id=hid, agent_id="creator")
    assert got["status"] == STATUS_REJECTED
    assert got["rejected_reason"] == "busy"


def test_handoff_get_access_creator_claimant_eligible_stranger(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    agents = FakeAgentRepo()
    agents.add("worker", capabilities={"ocr": True})
    agents.add("peer", capabilities={"ocr": True})
    agents.add("stranger")
    svc = make_service(migrated_factory, tmp_config, clock, agents=agents)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="creator",
        target={"strategy": "capability", "capability": "ocr"},
        visibility="eligible",
    )["handoff_id"]

    # Creator (not eligible itself) and an eligible peer can read it.
    assert (
        svc.handoff_get(project_root=proj, handoff_id=hid, agent_id="creator")["status"]
        == STATUS_OPEN
    )
    assert (
        svc.handoff_get(project_root=proj, handoff_id=hid, agent_id="peer")["status"]
        == STATUS_OPEN
    )
    # A non-eligible stranger is gated (same predicate as list_available).
    with pytest.raises(OktoNexusError) as ei:
        svc.handoff_get(project_root=proj, handoff_id=hid, agent_id="stranger")
    assert ei.value.code == ErrorCode.NOT_OWNER.value
    assert "handoff_get" in ei.value.message

    # The claimant always can, even after the handoff turns terminal.
    svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="worker")
    svc.handoff_complete(project_root=proj, handoff_id=hid, agent_id="worker")
    assert (
        svc.handoff_get(project_root=proj, handoff_id=hid, agent_id="worker")["status"]
        == STATUS_COMPLETED
    )


def test_handoff_get_not_found_and_workspace_mismatch(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock)
    proj_a = str(mkdir(tmp_path, "A"))
    proj_b = str(mkdir(tmp_path, "B"))
    seed_workspace(migrated_factory, proj_a, clock)
    seed_workspace(migrated_factory, proj_b, clock)
    hid = svc.handoff_create(
        project_root=proj_a,
        from_agent_id="c",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]

    with pytest.raises(OktoNexusError) as e_nf:
        svc.handoff_get(project_root=proj_a, handoff_id="ghost", agent_id="c")
    assert e_nf.value.code == ErrorCode.NOT_FOUND.value
    with pytest.raises(OktoNexusError) as e_wm:
        svc.handoff_get(project_root=proj_b, handoff_id=hid, agent_id="c")
    assert e_wm.value.code == ErrorCode.WORKSPACE_MISMATCH.value


def test_handoff_get_reflects_expired_lease_as_open(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock("2026-06-07T00:00:00.000000Z")
    svc = make_service(migrated_factory, tmp_config, clock)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="creator",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    claim = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="worker")
    clock.set(iso_plus(claim["lease_expires_at"], 5))

    got = svc.handoff_get(project_root=proj, handoff_id=hid, agent_id="creator")
    assert got["status"] == STATUS_OPEN  # the elapsed lease reads as reopened
    assert got["claimed_by"] is None


def test_creator_reads_outcome_invisible_on_the_event_stream(
    migrated_factory, tmp_config, tmp_path
):
    """The v2 scenario end-to-end: visibility=eligible + a capability target the
    creator does NOT possess. The creator never sees handoff.completed via
    event_get (events are observability, visibility-gated), yet handoff_get
    returns COMPLETED + the result byte-for-byte."""
    clock = StubClock()
    agents, messages, deliveries = make_real_world(migrated_factory, clock)
    register_real_agent(migrated_factory, agents, "creator")  # no ocr capability
    register_real_agent(migrated_factory, agents, "worker", capabilities={"ocr": True})
    events_repo = SqliteEventRepo(clock)
    emitter = SqliteEventEmitter(events_repo)
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        emitter=emitter,
        agents=agents,
        messages=messages,
        deliveries=deliveries,
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)

    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="creator",
        target={"strategy": "capability", "capability": "ocr"},
        visibility="eligible",
    )["handoff_id"]
    svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="worker")
    result = "scanned 12 pages"
    svc.handoff_complete(
        project_root=proj, handoff_id=hid, agent_id="worker", result=result
    )

    event_svc = EventService(
        connection_factory=migrated_factory,
        events=events_repo,
        clock=clock,
        config=tmp_config,
        agents=agents,
    )
    page = event_svc.event_get(project_root=proj, agent_id="creator", stream="handoff")
    assert "handoff.completed" not in [e["type"] for e in page["events"]]

    got = svc.handoff_get(project_root=proj, handoff_id=hid, agent_id="creator")
    assert got["status"] == STATUS_COMPLETED
    assert got["result"] == result


# --------------------------------------------------------------------------- #
# Directed-handoff + outcome inbox notifications (messages/deliveries reuse)
# --------------------------------------------------------------------------- #
def test_direct_handoff_lands_one_inbox_notification(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    agents, messages, deliveries = make_real_world(migrated_factory, clock)
    register_real_agent(migrated_factory, agents, "worker")
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        agents=agents,
        messages=messages,
        deliveries=deliveries,
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)

    out = svc.handoff_create(
        project_root=proj,
        from_agent_id="boss",
        target={"strategy": "direct", "agent_id": "worker"},
        visibility="eligible",
        payload="OCR scan.pdf",
    )
    assert out["notified"] == ["worker"]

    inbox = inbox_for(migrated_factory, clock)
    assert inbox.count(agent_id="worker")["unread"] == 1
    pulled = inbox.pull(agent_id="worker")
    assert pulled["count"] == 1
    msg = pulled["messages"][0]
    assert msg["subject"] == "handoff {} directed to you".format(out["handoff_id"])
    body = json.loads(msg["body"])
    assert body["kind"] == "handoff.directed"
    assert body["handoff_id"] == out["handoff_id"]
    assert "payload" not in body
    assert "handoff_claim" in body["next_step"]
    # The notification acks through the normal inbox lanes.
    assert inbox.ack(agent_id="worker", message_ids=[msg["message_id"]]) == {
        "acknowledged": 1,
        "read_message_ids": [msg["message_id"]],
    }
    assert inbox.count(agent_id="worker")["unread"] == 0


def test_pool_handoff_creates_zero_deliveries(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    agents, messages, deliveries = make_real_world(migrated_factory, clock)
    register_real_agent(migrated_factory, agents, "w1", capabilities={"ocr": True})
    register_real_agent(migrated_factory, agents, "w2", capabilities={"ocr": True})
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        agents=agents,
        messages=messages,
        deliveries=deliveries,
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)

    svc.handoff_create(
        project_root=proj,
        from_agent_id="boss",
        target={"strategy": "capability", "capability": "ocr"},
        visibility="public",
    )
    svc.handoff_create(
        project_root=proj,
        from_agent_id="boss",
        target={"strategy": "broadcast"},
        visibility="public",
    )
    # Pool targets keep poll semantics (handoff_list_available); no inbox noise.
    assert count(migrated_factory, "message_deliveries") == 0


def test_direct_with_fallback_notifies_registered_agent(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    agents, messages, deliveries = make_real_world(migrated_factory, clock)
    register_real_agent(migrated_factory, agents, "worker")
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        agents=agents,
        messages=messages,
        deliveries=deliveries,
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)

    out = svc.handoff_create(
        project_root=proj,
        from_agent_id="boss",
        target={
            "strategy": "direct_with_fallback",
            "agent_id": "worker",
            "fallback_after_seconds": 60,
        },
        visibility="public",
    )
    assert out["notified"] == ["worker"]
    assert out["eligible_count"] == 1

    # Unknown agent on the fallback path: no error, no delivery, explicit warning.
    out2 = svc.handoff_create(
        project_root=proj,
        from_agent_id="boss",
        target={
            "strategy": "direct_with_fallback",
            "agent_id": "late-joiner",
            "fallback_after_seconds": 60,
        },
        visibility="public",
    )
    assert "notified" not in out2
    assert out2["eligible_count"] == 0 and "warning" in out2
    assert count(migrated_factory, "message_deliveries") == 1  # only the first


def test_complete_delivers_result_to_creator_inbox(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    agents, messages, deliveries = make_real_world(migrated_factory, clock)
    register_real_agent(migrated_factory, agents, "creator")
    register_real_agent(migrated_factory, agents, "worker")
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        agents=agents,
        messages=messages,
        deliveries=deliveries,
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="creator",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="worker")
    out = svc.handoff_complete(
        project_root=proj, handoff_id=hid, agent_id="worker", result="all done"
    )
    assert out["notified"] == ["creator"]

    inbox = inbox_for(migrated_factory, clock)
    pulled = inbox.pull(agent_id="creator")
    assert pulled["count"] == 1
    msg = pulled["messages"][0]
    assert msg["subject"] == "handoff {} completed by worker".format(hid)
    body = json.loads(msg["body"])
    assert body["kind"] == "handoff.completed"
    assert body["result"] == "all done"
    assert "handoff_get" in body["next_step"]


def test_reject_delivers_reason_to_creator_inbox(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    agents, messages, deliveries = make_real_world(migrated_factory, clock)
    register_real_agent(migrated_factory, agents, "creator")
    register_real_agent(migrated_factory, agents, "worker")
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        agents=agents,
        messages=messages,
        deliveries=deliveries,
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="creator",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="worker")
    out = svc.handoff_reject(
        project_root=proj, handoff_id=hid, agent_id="worker", reason="not my area"
    )
    assert out["notified"] == ["creator"]

    inbox = inbox_for(migrated_factory, clock)
    msg = inbox.pull(agent_id="creator")["messages"][0]
    body = json.loads(msg["body"])
    assert body["kind"] == "handoff.rejected"
    assert body["reason"] == "not my area"


def test_no_self_notification_when_creator_completes_own_claim(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    agents, messages, deliveries = make_real_world(migrated_factory, clock)
    register_real_agent(migrated_factory, agents, "solo")
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        agents=agents,
        messages=messages,
        deliveries=deliveries,
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="solo",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="solo")
    out = svc.handoff_complete(project_root=proj, handoff_id=hid, agent_id="solo")
    assert "notified" not in out
    assert count(migrated_factory, "message_deliveries") == 0


def test_outcome_to_unregistered_creator_skips_delivery(
    migrated_factory, tmp_config, tmp_path
):
    # The creator never registered (no agents row to satisfy the delivery FK):
    # the notification is skipped (no crash) and the lifecycle still completes.
    clock = StubClock()
    agents, messages, deliveries = make_real_world(migrated_factory, clock)
    register_real_agent(migrated_factory, agents, "worker")
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        agents=agents,
        messages=messages,
        deliveries=deliveries,
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj,
        from_agent_id="phantom",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="worker")
    out = svc.handoff_complete(project_root=proj, handoff_id=hid, agent_id="worker")
    assert out["status"] == STATUS_COMPLETED
    assert "notified" not in out
    assert count(migrated_factory, "message_deliveries") == 0
