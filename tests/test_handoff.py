"""Tests for the handoff lifecycle slice.

Hexagonal unit/integration tests: the application service runs over the REAL
SQLite adapters owned by this slice (``SqliteHandoffRepo`` / ``SqliteTaskRepo``
via ``migrated_factory``), while ports owned by OTHER slices are faked - the
Event Log ``EventEmitter`` and the identity ``AgentRepo`` (agent-profile port
for routing/eligibility). Covers the workspace guard, cross-workspace
isolation, create happy path + validation + 64KB boundary, list_available
visibility/eligibility filtering + opportunistic expiry + pagination/long-poll,
atomic double-claim concurrency, claim NOT_FOUND/WORKSPACE_MISMATCH, the
eligibility gate, strict lease-expiry boundary + re-claim, complete/reject
ownership and the explicit transition table, the MCP tool envelope, and
concurrent-writer event monotonicity.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.mcp.tools.handoff import build_service, register
from okto_nexus.adapters.outbound.sqlite.handoff_repo import (
    SqliteHandoffRepo,
    SqliteTaskRepo,
)
from okto_nexus.application.handoff import (
    HandoffService,
    _epoch_to_iso,
    _iso_to_epoch,
)
from okto_nexus.application.ports import Repos
from okto_nexus.domain.handoff import (
    STATUS_CLAIMED,
    STATUS_COMPLETED,
    STATUS_OPEN,
    STATUS_REJECTED,
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
    """Deterministic, mutable clock implementing the Clock port."""

    def __init__(self, iso: str = "2026-06-07T00:00:00Z") -> None:
        self._iso = iso

    def now_iso(self) -> str:
        return self._iso

    def now_epoch(self) -> float:
        return _iso_to_epoch(self._iso)

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
            created_at="2026-06-07T00:00:00Z",
            role=role,
            capabilities=capabilities or {},
            metadata={},
        )

    def get(self, uow, agent_id):
        return self._agents.get(agent_id)

    def upsert(self, uow, *, agent_id, role=None, capabilities=None, metadata=None):
        self.add(agent_id, role=role, capabilities=capabilities)
        return self._agents[agent_id]


class FakeServer:
    """Captures FastMCP-style ``@server.tool()`` registrations by name."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def iso_plus(iso: str, seconds: float) -> str:
    return _epoch_to_iso(_iso_to_epoch(iso) + seconds)


def make_service(factory, config, clock, emitter=None, agents=None):
    return HandoffService(
        connection_factory=factory,
        handoffs=SqliteHandoffRepo(clock),
        tasks=SqliteTaskRepo(clock),
        clock=clock,
        config=config,
        event_emitter=emitter,
        agents=agents,
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


def retry_db(fn, attempts: int = 50, delay: float = 0.02):
    """Retry on transient DB_ERROR (WAL snapshot/busy under contention)."""
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
# Pure domain unit tests
# --------------------------------------------------------------------------- #
def test_validate_target_and_visibility():
    assert validate_target({"strategy": "broadcast"})["strategy"] == "broadcast"
    assert validate_target({"strategy": "direct", "agent_id": "a"})["agent_id"] == "a"
    assert validate_target('{"strategy":"role","role":"builder"}')["role"] == "builder"
    assert normalize_visibility("Public") == "public"

    for bad in (None, "", {"strategy": "nope"}, {"agent_id": "a"}, {"strategy": "direct"}):
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
    assert can_transition(STATUS_CLAIMED, STATUS_OPEN) is True
    assert can_transition(STATUS_CLAIMED, STATUS_COMPLETED) is True
    assert can_transition(STATUS_COMPLETED, STATUS_OPEN) is False
    assert can_transition(STATUS_OPEN, STATUS_COMPLETED) is False


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
    clock = StubClock("2026-06-07T00:00:00Z")
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
    assert out["created_at"] == "2026-06-07T00:00:00Z"

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


def test_handoff_create_content_boundary_inclusive(migrated_factory, tmp_config, tmp_path):
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
def test_list_available_visibility_and_eligibility(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    agents = FakeAgentRepo()
    agents.add("worker", capabilities=["py"])
    svc = make_service(migrated_factory, tmp_config, clock, agents=agents)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)

    # direct->worker, eligible visibility: visible+eligible to worker only.
    h_direct = svc.handoff_create(
        project_root=proj, from_agent_id="c",
        target={"strategy": "direct", "agent_id": "worker"}, visibility="eligible",
    )["handoff_id"]
    # broadcast public: visible+eligible to everyone.
    h_broadcast = svc.handoff_create(
        project_root=proj, from_agent_id="c",
        target={"strategy": "broadcast"}, visibility="public",
    )["handoff_id"]
    # direct->other, public: worker can SEE it but is NOT eligible -> excluded.
    svc.handoff_create(
        project_root=proj, from_agent_id="c",
        target={"strategy": "direct", "agent_id": "other"}, visibility="public",
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
                project_root=proj, from_agent_id="c",
                target={"strategy": "broadcast"}, visibility="public",
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

    seen = [h["handoff_id"] for h in page1["handoffs"] + page2["handoffs"] + page3["handoffs"]]
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
    res = svc.handoff_list_available(
        project_root=proj, agent_id="w", timeout_seconds=1
    )
    elapsed = time.monotonic() - started
    assert res["handoffs"] == []
    assert res["timed_out"] is True
    assert 0.5 <= elapsed < 5.0

    # No timeout -> single shot, not flagged as timed out.
    res0 = svc.handoff_list_available(project_root=proj, agent_id="w")
    assert res0["timed_out"] is False


# --------------------------------------------------------------------------- #
# FR4 / FR5 / TS5 / TS6 - claim
# --------------------------------------------------------------------------- #
def test_claim_happy(migrated_factory, tmp_config, tmp_path):
    clock = StubClock("2026-06-07T00:00:00Z")
    emitter = ThreadSafeEmitter()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=emitter)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj, from_agent_id="c",
        target={"strategy": "broadcast"}, visibility="public",
    )["handoff_id"]

    out = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="w", session_id="s1")
    assert out["status"] == STATUS_CLAIMED
    assert out["claimed_by"] == "w"
    expected_lease = iso_plus("2026-06-07T00:00:00Z", tmp_config.handoff_lease_ttl_seconds)
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
        project_root=proj_a, from_agent_id="c",
        target={"strategy": "broadcast"}, visibility="public",
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
        project_root=proj, from_agent_id="c",
        target={"strategy": "direct", "agent_id": "worker"}, visibility="public",
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
        project_root=proj, from_agent_id="c",
        target={"strategy": "broadcast"}, visibility="public",
    )["handoff_id"]

    agents = [f"agent-{i}" for i in range(6)]
    barrier = threading.Barrier(len(agents))
    lock = threading.Lock()
    winners: list[dict] = []
    losers: list[str] = []

    def worker(agent):
        barrier.wait()
        try:
            out = retry_db(
                lambda: svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id=agent)
            )
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


# --------------------------------------------------------------------------- #
# FR7 / TS8 / TS9 - lease expiry boundary + re-claim
# --------------------------------------------------------------------------- #
def test_lease_expiry_strict_boundary_and_reclaim(migrated_factory, tmp_config, tmp_path):
    clock = StubClock("2026-06-07T00:00:00Z")
    emitter = ThreadSafeEmitter()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=emitter)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj, from_agent_id="c",
        target={"strategy": "broadcast"}, visibility="public",
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
    clock = StubClock("2026-06-07T00:00:00Z")
    emitter = ThreadSafeEmitter()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=emitter)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj, from_agent_id="c",
        target={"strategy": "broadcast"}, visibility="public",
    )["handoff_id"]
    claim = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="a1")

    # Before expiry the handoff is CLAIMED -> not in the available list.
    assert svc.handoff_list_available(project_root=proj, agent_id="a2")["handoffs"] == []

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
        project_root=proj, from_agent_id="c", target=target, visibility="public",
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
        project_root=proj, from_agent_id="c",
        target={"strategy": "broadcast"}, visibility="public",
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
    out = svc.handoff_reject(project_root=proj, handoff_id=hid, agent_id="owner", reason="busy")
    assert out["status"] == STATUS_REJECTED
    assert emitter.types()[-1] == "handoff.rejected"

    # direct target rejects an OPEN handoff before claim -> OPEN -> REJECTED
    direct_hid = svc.handoff_create(
        project_root=proj, from_agent_id="c",
        target={"strategy": "direct", "agent_id": "worker"}, visibility="eligible",
    )["handoff_id"]
    out2 = svc.handoff_reject(project_root=proj, handoff_id=direct_hid, agent_id="worker")
    assert out2["status"] == STATUS_REJECTED

    # non-owner / non-direct rejecting an OPEN handoff -> NOT_OWNER
    open_hid = svc.handoff_create(
        project_root=proj, from_agent_id="c",
        target={"strategy": "direct", "agent_id": "worker"}, visibility="public",
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
        project_root=proj_a, from_agent_id="c",
        target={"strategy": "broadcast"}, visibility="public",
    )["handoff_id"]

    # The handoff never appears in another workspace's listing.
    assert svc.handoff_list_available(project_root=proj_b, agent_id="w")["handoffs"] == []
    # And cannot be completed/rejected from another workspace.
    with pytest.raises(OktoNexusError) as ei:
        svc.handoff_complete(project_root=proj_b, handoff_id=hid, agent_id="w")
    assert ei.value.code == ErrorCode.WORKSPACE_MISMATCH.value


# --------------------------------------------------------------------------- #
# Task repo (owned by this slice) + handoff<->task linkage
# --------------------------------------------------------------------------- #
def test_task_repo_crud_and_linkage(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock)
    proj = str(mkdir(tmp_path, "P"))
    ws = seed_workspace(migrated_factory, proj, clock)
    tasks = SqliteTaskRepo(clock)

    with migrated_factory.unit_of_work() as uow:
        t = tasks.create(
            uow, task_id="task-1", workspace_id=ws, title="Build", status="open"
        )
        assert t.title == "Build"
        assert tasks.get(uow, workspace_id=ws, task_id="task-1").status == "open"
        updated = tasks.update_status(
            uow, workspace_id=ws, task_id="task-1", status="done"
        )
        assert updated.status == "done"
        assert [x.task_id for x in tasks.list(uow, workspace_id=ws)] == ["task-1"]
        with pytest.raises(OktoNexusError) as ei:
            tasks.update_status(uow, workspace_id=ws, task_id="ghost", status="x")
        assert ei.value.code == ErrorCode.NOT_FOUND.value

    # handoff_create with a valid task_id links; an unknown task_id -> NOT_FOUND.
    linked = svc.handoff_create(
        project_root=proj, from_agent_id="c",
        target={"strategy": "broadcast"}, visibility="public", task_id="task-1",
    )
    assert linked["status"] == STATUS_OPEN
    with pytest.raises(OktoNexusError) as enf:
        svc.handoff_create(
            project_root=proj, from_agent_id="c",
            target={"strategy": "broadcast"}, visibility="public", task_id="missing",
        )
    assert enf.value.code == ErrorCode.NOT_FOUND.value


# --------------------------------------------------------------------------- #
# TS13 - atomic events / monotonic event_id under concurrent writers
# --------------------------------------------------------------------------- #
def test_concurrent_creates_unique_monotonic_events(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    emitter = ThreadSafeEmitter()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=emitter)
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    n = 12
    barrier = threading.Barrier(n)

    def worker():
        barrier.wait()
        retry_db(
            lambda: svc.handoff_create(
                project_root=proj, from_agent_id="c",
                target={"strategy": "broadcast"}, visibility="public",
            )
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
        "handoff_reject",
    }
    assert deps.repos.handoffs is not None
    assert deps.repos.tasks is not None

    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)

    created = server.tools["handoff_create"](
        project_root=proj, from_agent_id="c",
        target={"strategy": "broadcast"}, visibility="public",
        payload="please process batch 7",
    )
    assert created["ok"] is True
    hid = created["data"]["handoff_id"]

    listed = server.tools["handoff_list_available"](project_root=proj, agent_id="w")
    assert listed["ok"] is True
    assert {h["handoff_id"] for h in listed["data"]["handoffs"]} == {hid}
    # Payload travels with the row through the full MCP path (no event correlation).
    assert listed["data"]["handoffs"][0]["payload"] == "please process batch 7"

    claimed = server.tools["handoff_claim"](project_root=proj, handoff_id=hid, agent_id="w")
    assert claimed["ok"] is True and claimed["data"]["status"] == STATUS_CLAIMED
    assert claimed["data"]["payload"] == "please process batch 7"

    completed = server.tools["handoff_complete"](
        project_root=proj, handoff_id=hid, agent_id="w"
    )
    assert completed["ok"] is True and completed["data"]["status"] == STATUS_COMPLETED

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
    assert deps.repos.tasks is not None  # filled in
    assert deps.repos.agents is not None  # filled in


# --------------------------------------------------------------------------- #
# Handoff payload passthrough (migration 003) - returned by list/claim
# --------------------------------------------------------------------------- #
def test_migration_003_adds_payload_column_idempotently(migrated_factory):
    # The payload column comes from migration 003, and re-applying is a no-op
    # (no 'duplicate column name', nothing newly applied).
    from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner

    conn = migrated_factory.get_connection()
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(handoffs)").fetchall()}
        migs = {r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
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


def test_payload_round_trips_through_list_and_claim(
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

    # The worker sees the payload BEFORE claiming (no event correlation needed).
    listed = svc.handoff_list_available(project_root=proj, agent_id="worker")
    assert len(listed["handoffs"]) == 1
    assert listed["handoffs"][0]["payload"] == body

    # And gets it back on the claim response too.
    claimed = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="worker")
    assert claimed["payload"] == body


def test_payload_none_stays_none(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    svc = make_service(
        migrated_factory, tmp_config, clock,
        emitter=ThreadSafeEmitter(), agents=FakeAgentRepo(),
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj, from_agent_id="boss",
        target={"strategy": "broadcast"}, visibility="public",
    )["handoff_id"]

    listed = svc.handoff_list_available(project_root=proj, agent_id="w")
    assert listed["handoffs"][0]["payload"] is None
    claimed = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="w")
    assert claimed["payload"] is None


def test_payload_object_is_serialized_to_json_text(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_service(
        migrated_factory, tmp_config, clock,
        emitter=ThreadSafeEmitter(), agents=FakeAgentRepo(),
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj, from_agent_id="boss",
        target={"strategy": "broadcast"}, visibility="public",
        payload={"k": "v", "n": 3},
    )["handoff_id"]

    claimed = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="w")
    # Opaque on read-back: returned as the stored JSON TEXT, not re-parsed.
    assert isinstance(claimed["payload"], str)
    assert json.loads(claimed["payload"]) == {"k": "v", "n": 3}


def test_payload_consistent_between_event_and_claim(
    migrated_factory, tmp_config, tmp_path
):
    # A non-string payload exposes ONE representation across surfaces: the
    # handoff.created event and the claim echo must agree (both the JSON TEXT).
    clock = StubClock()
    emitter = ThreadSafeEmitter()
    svc = make_service(
        migrated_factory, tmp_config, clock, emitter=emitter, agents=FakeAgentRepo()
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj, from_agent_id="b",
        target={"strategy": "broadcast"}, visibility="public", payload={"k": "v"},
    )["handoff_id"]
    claimed = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="w")
    created = [e for e in emitter.events if e["type"] == "handoff.created"]
    # The emitter records the full event_payload dict; its "payload" key holds
    # the serialised work content - it must equal the claim echo.
    assert created[0]["payload"]["payload"] == claimed["payload"] == '{"k": "v"}'


def test_payload_large_round_trips_at_boundary(migrated_factory, tmp_config, tmp_path):
    # The feature is passthrough: a payload at the 64KB inclusive limit must come
    # back byte-for-byte through both list_available and claim (not just pass the
    # size gate).
    clock = StubClock()
    svc = make_service(
        migrated_factory, tmp_config, clock,
        emitter=ThreadSafeEmitter(), agents=FakeAgentRepo(),
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    big = "x" * tmp_config.max_inline_bytes
    hid = svc.handoff_create(
        project_root=proj, from_agent_id="b",
        target={"strategy": "broadcast"}, visibility="public", payload=big,
    )["handoff_id"]
    listed = svc.handoff_list_available(project_root=proj, agent_id="w")
    claimed = svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="w")
    assert listed["handoffs"][0]["payload"] == big
    assert claimed["payload"] == big
    assert len(claimed["payload"]) == tmp_config.max_inline_bytes


def test_payload_unicode_round_trips(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    svc = make_service(
        migrated_factory, tmp_config, clock,
        emitter=ThreadSafeEmitter(), agents=FakeAgentRepo(),
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    text = "relatório café ☕ 文件"  # accents + emoji + CJK
    hid = svc.handoff_create(
        project_root=proj, from_agent_id="b",
        target={"strategy": "broadcast"}, visibility="public", payload=text,
    )["handoff_id"]
    assert svc.handoff_claim(project_root=proj, handoff_id=hid, agent_id="w")[
        "payload"
    ] == text  # same code points, no \\uXXXX escaping

    # An object with non-ASCII values is stored as UTF-8 JSON, not ASCII-escaped.
    hid2 = svc.handoff_create(
        project_root=proj, from_agent_id="b",
        target={"strategy": "broadcast"}, visibility="public",
        payload={"nota": "café ☕"},
    )["handoff_id"]
    body2 = svc.handoff_claim(project_root=proj, handoff_id=hid2, agent_id="w")["payload"]
    assert json.loads(body2) == {"nota": "café ☕"}
    assert "\\u" not in body2  # ensure_ascii=False preserved the characters


def test_payload_empty_string_preserved_not_null(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_service(
        migrated_factory, tmp_config, clock,
        emitter=ThreadSafeEmitter(), agents=FakeAgentRepo(),
    )
    proj = str(mkdir(tmp_path, "P"))
    seed_workspace(migrated_factory, proj, clock)
    hid = svc.handoff_create(
        project_root=proj, from_agent_id="b",
        target={"strategy": "broadcast"}, visibility="public", payload="",
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
            ("hof_legacy", ws, STATUS_OPEN, "2026-06-07T00:00:00Z"),
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
