"""Tests for the identity slice (workspace / agent / session).

Hexagonal unit/integration tests: the application service is exercised over the
real SQLite adapters (via ``migrated_factory``), while ports owned by OTHER
slices (the Event Log ``EventEmitter``) are faked. Covers the happy paths, the
canonical error catalogue, the 64KB inline boundary, path/workspace resolution,
cross-workspace isolation + mismatch, stale-TTL derivation, the MCP tool
envelope, and concurrency (parallel session_open with unique ids, concurrent
writers across workspaces with no leakage, all committed under busy_timeout).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.mcp.tools.identity import (
    DEFAULT_SESSION_STALE_TTL_SECONDS,
    STALE_TTL_ENV,
    _resolve_stale_ttl,
    build_service,
    register,
)
from okto_nexus.adapters.outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteSessionRepo,
    SqliteWorkspaceRepo,
)
from okto_nexus.application.identity import IdentityService, _iso_to_epoch
from okto_nexus.application.ports import Repos
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
        dt = datetime.fromtimestamp(self.now_epoch() + seconds, tz=timezone.utc)
        self._iso = dt.isoformat().replace("+00:00", "Z")


class FakeEmitter:
    """Fake EventEmitter (Event Log slice port) recording emitted events."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self._next = 0

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
        self._next += 1
        self.events.append(
            {
                "event_id": self._next,
                "workspace_id": workspace_id,
                "stream": stream,
                "type": type,
                "payload": payload,
                "actor_agent_id": actor_agent_id,
                "visibility": visibility,
                "target": target,
            }
        )
        return self._next


class FakeServer:
    """Captures FastMCP-style ``@server.tool()`` registrations by name."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def make_service(factory, config, clock, emitter=None, stale_ttl=60):
    return IdentityService(
        connection_factory=factory,
        workspaces=SqliteWorkspaceRepo(clock),
        agents=SqliteAgentRepo(clock),
        sessions=SqliteSessionRepo(clock),
        clock=clock,
        config=config,
        event_emitter=emitter,
        stale_ttl_seconds=stale_ttl,
    )


def make_deps(factory, config, clock, emitter=None):
    return SimpleNamespace(
        config=config,
        connection_factory=factory,
        clock=clock,
        repos=Repos(),
        event_emitter=emitter,
    )


def count(factory, table: str) -> int:
    conn = factory.get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def retry_db(fn, attempts: int = 30, delay: float = 0.02):
    """Retry on transient DB_ERROR (WAL busy/snapshot under contention)."""
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


def mkdir(tmp_path, name):
    p = tmp_path / name
    p.mkdir()
    return p


# --------------------------------------------------------------------------- #
# workspace_resolve
# --------------------------------------------------------------------------- #
def test_workspace_resolve_determinism(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    proj = mkdir(tmp_path, "proj")
    mkdir(proj, "sub")

    r1 = svc.workspace_resolve(project_root=str(proj))
    r2 = svc.workspace_resolve(
        project_root=os.path.join(str(proj), "sub", "..")
    )

    expected = hashlib.sha256(
        os.path.realpath(str(proj)).encode("utf-8")
    ).hexdigest().lower()
    assert r1["workspace_id"] == expected
    assert r2["workspace_id"] == expected
    assert r1["workspace_id"] == r2["workspace_id"]
    assert r1["root_realpath"] == os.path.realpath(str(proj))


def test_workspace_resolve_upsert_and_display_name_metadata(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock("2026-06-07T00:00:00Z")
    svc = make_service(migrated_factory, tmp_config, clock)
    a = mkdir(tmp_path, "A")
    b = mkdir(tmp_path, "B")

    r1 = svc.workspace_resolve(project_root=str(a), display_name="Projeto Alpha")
    assert r1["display_name"] == "Projeto Alpha"
    assert r1["created_at"] == "2026-06-07T00:00:00Z"
    assert r1["last_seen_at"] == "2026-06-07T00:00:00Z"

    clock.set("2026-06-07T01:00:00Z")
    r2 = svc.workspace_resolve(project_root=str(a), display_name="Projeto Beta")
    assert r2["workspace_id"] == r1["workspace_id"]
    assert r2["created_at"] == r1["created_at"]  # immutable on re-resolution
    assert r2["last_seen_at"] == "2026-06-07T01:00:00Z"  # advanced
    assert r2["display_name"] == "Projeto Beta"

    # Same display_name but a distinct root_realpath coexists as its own row.
    r3 = svc.workspace_resolve(project_root=str(b), display_name="Projeto Alpha")
    assert r3["workspace_id"] != r1["workspace_id"]
    assert count(migrated_factory, "workspaces") == 2


def test_workspace_resolve_unresolved_no_fallback(
    migrated_factory, tmp_config, tmp_path
):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    missing = tmp_path / "does_not_exist" / "child"  # absolute, nonexistent

    with pytest.raises(OktoNexusError) as ei:
        svc.workspace_resolve(project_root=str(missing))
    assert ei.value.code == ErrorCode.WORKSPACE_UNRESOLVED.value
    assert count(migrated_factory, "workspaces") == 0


@pytest.mark.parametrize("bad", [None, "", "   ", os.path.join("relative", "path")])
def test_workspace_resolve_validation_error(migrated_factory, tmp_config, bad):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    with pytest.raises(OktoNexusError) as ei:
        svc.workspace_resolve(project_root=bad)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert count(migrated_factory, "workspaces") == 0


# --------------------------------------------------------------------------- #
# agent_register
# --------------------------------------------------------------------------- #
def test_agent_register_idempotent_no_workspace(migrated_factory, tmp_config):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    svc.agent_register(
        agent_id="agent-1", role="planner", capabilities=["plan"], metadata={"k": 1}
    )
    out = svc.agent_register(
        agent_id="agent-1", role="builder", capabilities=["plan", "code"]
    )
    assert out["agent_id"] == "agent-1"
    assert out["role"] == "builder"
    assert out["capabilities"] == ["plan", "code"]
    # metadata not re-supplied -> preserved (mutable-field update semantics)
    assert out["metadata"] == {"k": 1}
    assert count(migrated_factory, "agents") == 1


@pytest.mark.parametrize("bad", [None, "", "   "])
def test_agent_register_validation_error(migrated_factory, tmp_config, bad):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    with pytest.raises(OktoNexusError) as ei:
        svc.agent_register(agent_id=bad)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert count(migrated_factory, "agents") == 0


def test_agent_register_inline_size_boundary_inclusive(migrated_factory, tmp_config):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    limit = tmp_config.max_inline_bytes  # 65536, inclusive
    overhead = len(json.dumps({"v": ""}, ensure_ascii=False).encode("utf-8"))
    value_at_limit = {"v": "x" * (limit - overhead)}
    assert len(json.dumps(value_at_limit, ensure_ascii=False).encode("utf-8")) == limit

    # Exactly 65536 bytes is allowed (boundary is inclusive).
    ok = svc.agent_register(agent_id="agent-ok", metadata=value_at_limit)
    assert ok["agent_id"] == "agent-ok"

    # One byte over -> CONTENT_TOO_LARGE, nothing persisted for that agent.
    too_big = {"v": "x" * (limit - overhead + 1)}
    with pytest.raises(OktoNexusError) as ei:
        svc.agent_register(agent_id="agent-big", metadata=too_big)
    assert ei.value.code == ErrorCode.CONTENT_TOO_LARGE.value
    assert svc._agents is not None  # service intact
    assert count(migrated_factory, "agents") == 1


# --------------------------------------------------------------------------- #
# session_open
# --------------------------------------------------------------------------- #
def _seed_ws_agent(svc, tmp_path, name="P", agent="agent-1"):
    proj = mkdir(tmp_path, name)
    ws = svc.workspace_resolve(project_root=str(proj))["workspace_id"]
    svc.agent_register(agent_id=agent)
    return ws


def test_session_open_happy_path(migrated_factory, tmp_config, tmp_path):
    clock = StubClock("2026-06-07T00:00:00Z")
    svc = make_service(migrated_factory, tmp_config, clock)
    ws = _seed_ws_agent(svc, tmp_path)

    out = svc.session_open(agent_id="agent-1", workspace_id=ws)
    assert out["session_id"]  # server-assigned, non-empty
    assert out["status"] == "active"
    assert out["agent_id"] == "agent-1"
    assert out["workspace_id"] == ws
    assert out["started_at"] == "2026-06-07T00:00:00Z"
    assert out["last_heartbeat_at"] == "2026-06-07T00:00:00Z"

    stored = svc.get_session(session_id=out["session_id"])
    assert stored["agent_id"] == "agent-1"
    assert stored["workspace_id"] == ws


def test_session_open_workspace_required_and_not_found(
    migrated_factory, tmp_config, tmp_path
):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    ws = _seed_ws_agent(svc, tmp_path)

    with pytest.raises(OktoNexusError) as ei_req:
        svc.session_open(agent_id="agent-1", workspace_id=None)
    assert ei_req.value.code == ErrorCode.WORKSPACE_REQUIRED.value

    with pytest.raises(OktoNexusError) as ei_ws:
        svc.session_open(agent_id="agent-1", workspace_id="deadbeef" * 8)
    assert ei_ws.value.code == ErrorCode.NOT_FOUND.value

    with pytest.raises(OktoNexusError) as ei_ag:
        svc.session_open(agent_id="ghost", workspace_id=ws)
    assert ei_ag.value.code == ErrorCode.NOT_FOUND.value

    assert count(migrated_factory, "sessions") == 0


def test_session_open_missing_agent_is_validation_error(
    migrated_factory, tmp_config, tmp_path
):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    ws = _seed_ws_agent(svc, tmp_path)
    with pytest.raises(OktoNexusError) as ei:
        svc.session_open(agent_id="", workspace_id=ws)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert count(migrated_factory, "sessions") == 0


# --------------------------------------------------------------------------- #
# session_heartbeat & stale derivation
# --------------------------------------------------------------------------- #
def test_session_heartbeat_updates_and_not_found(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock("2026-06-07T00:00:00Z")
    svc = make_service(migrated_factory, tmp_config, clock)
    ws = _seed_ws_agent(svc, tmp_path)
    opened = svc.session_open(agent_id="agent-1", workspace_id=ws)
    sid = opened["session_id"]

    clock.advance_seconds(30)
    hb = svc.session_heartbeat(session_id=sid)
    assert hb["session_id"] == sid
    assert hb["status"] == "active"
    assert _iso_to_epoch(hb["last_heartbeat_at"]) > _iso_to_epoch(
        opened["last_heartbeat_at"]
    )

    with pytest.raises(OktoNexusError) as ei:
        svc.session_heartbeat(session_id="unknown-session")
    assert ei.value.code == ErrorCode.NOT_FOUND.value


def test_session_stale_by_ttl_and_recovery(migrated_factory, tmp_config, tmp_path):
    clock = StubClock("2026-06-07T00:00:00Z")
    svc = make_service(migrated_factory, tmp_config, clock, stale_ttl=60)
    ws = _seed_ws_agent(svc, tmp_path)
    sid = svc.session_open(agent_id="agent-1", workspace_id=ws)["session_id"]

    # Advance well beyond the TTL: a read reports 'stale', row still present.
    clock.set("2026-06-07T00:05:00Z")  # +300s > 60s
    read = svc.get_session(session_id=sid)
    assert read["status"] == "stale"
    assert count(migrated_factory, "sessions") == 1

    # A heartbeat restores 'active'.
    hb = svc.session_heartbeat(session_id=sid)
    assert hb["status"] == "active"
    assert svc.get_session(session_id=sid)["status"] == "active"


def test_session_heartbeat_workspace_mismatch_no_mutation(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock("2026-06-07T00:00:00Z")
    svc = make_service(migrated_factory, tmp_config, clock)
    ws_a = _seed_ws_agent(svc, tmp_path, name="A")
    ws_b = svc.workspace_resolve(project_root=str(mkdir(tmp_path, "B")))["workspace_id"]
    sid = svc.session_open(agent_id="agent-1", workspace_id=ws_a)["session_id"]

    before = svc.get_session(session_id=sid)["last_heartbeat_at"]
    clock.advance_seconds(30)
    with pytest.raises(OktoNexusError) as ei:
        svc.session_heartbeat(session_id=sid, workspace_id=ws_b)
    assert ei.value.code == ErrorCode.WORKSPACE_MISMATCH.value
    after = svc.get_session(session_id=sid)["last_heartbeat_at"]
    assert before == after  # no cross-workspace mutation


# --------------------------------------------------------------------------- #
# Cross-workspace isolation
# --------------------------------------------------------------------------- #
def test_cross_workspace_isolation_in_standard_read(
    migrated_factory, tmp_config, tmp_path
):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    ws_a = _seed_ws_agent(svc, tmp_path, name="A")
    ws_b = svc.workspace_resolve(project_root=str(mkdir(tmp_path, "B")))["workspace_id"]
    s_a = svc.session_open(agent_id="agent-1", workspace_id=ws_a)["session_id"]
    s_b = svc.session_open(agent_id="agent-1", workspace_id=ws_b)["session_id"]

    list_a = svc.list_sessions(workspace_id=ws_a)
    assert {r["session_id"] for r in list_a} == {s_a}
    assert all(r["workspace_id"] == ws_a for r in list_a)

    list_b = svc.list_sessions(workspace_id=ws_b)
    assert {r["session_id"] for r in list_b} == {s_b}


def test_list_sessions_requires_workspace(migrated_factory, tmp_config):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    with pytest.raises(OktoNexusError) as ei:
        svc.list_sessions(workspace_id=None)
    assert ei.value.code == ErrorCode.WORKSPACE_REQUIRED.value


def test_get_session_workspace_mismatch(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    ws_a = _seed_ws_agent(svc, tmp_path, name="A")
    ws_b = svc.workspace_resolve(project_root=str(mkdir(tmp_path, "B")))["workspace_id"]
    sid = svc.session_open(agent_id="agent-1", workspace_id=ws_a)["session_id"]
    with pytest.raises(OktoNexusError) as ei:
        svc.get_session(session_id=sid, workspace_id=ws_b)
    assert ei.value.code == ErrorCode.WORKSPACE_MISMATCH.value


# --------------------------------------------------------------------------- #
# Audit event emission (INV11) using a faked Event Log port
# --------------------------------------------------------------------------- #
def test_audit_event_preserves_actor_and_session(
    migrated_factory, tmp_config, tmp_path
):
    emitter = FakeEmitter()
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=emitter)
    ws = _seed_ws_agent(svc, tmp_path)

    opened = svc.session_open(agent_id="agent-1", workspace_id=ws)
    assert emitter.events, "session_open should emit an audit event"
    ev = emitter.events[-1]
    assert ev["type"] == "session.opened"
    assert ev["workspace_id"] == ws
    assert ev["actor_agent_id"] == "agent-1"
    assert ev["target"] == opened["session_id"]
    assert ev["payload"]["session_id"] == opened["session_id"]
    assert ev["payload"]["agent_id"] == "agent-1"

    svc.session_heartbeat(session_id=opened["session_id"])
    ev2 = emitter.events[-1]
    assert ev2["type"] == "session.heartbeat"
    assert ev2["actor_agent_id"] == "agent-1"
    assert ev2["payload"]["session_id"] == opened["session_id"]


def test_no_emitter_is_safe(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock(), emitter=None)
    ws = _seed_ws_agent(svc, tmp_path)
    out = svc.session_open(agent_id="agent-1", workspace_id=ws)
    assert svc.session_heartbeat(session_id=out["session_id"])["status"] == "active"


# --------------------------------------------------------------------------- #
# MCP tool registration + canonical envelope (no exception escapes)
# --------------------------------------------------------------------------- #
def test_register_tools_and_envelope(migrated_factory, tmp_config, tmp_path):
    deps = make_deps(migrated_factory, tmp_config, StubClock())
    server = FakeServer()
    register(server, deps)
    assert set(server.tools) == {
        "workspace_resolve",
        "workspace_list",
        "agent_register",
        "session_open",
        "session_heartbeat",
        "session_close",
    }
    # register() must wire the concrete repos into deps.repos.
    assert deps.repos.workspaces is not None
    assert deps.repos.agents is not None
    assert deps.repos.sessions is not None

    proj = mkdir(tmp_path, "P")
    res = server.tools["workspace_resolve"](project_root=str(proj))
    assert res["ok"] is True
    ws = res["data"]["workspace_id"]

    ar = server.tools["agent_register"](
        agent_id="agent-1", role="builder", capabilities=["x"]
    )
    assert ar["ok"] is True and ar["data"]["agent_id"] == "agent-1"

    # Failures are surfaced as envelopes, never raised.
    missing_ws = server.tools["session_open"](agent_id="agent-1")
    assert missing_ws["ok"] is False
    assert missing_ws["error"]["code"] == "WORKSPACE_REQUIRED"

    so = server.tools["session_open"](agent_id="agent-1", workspace_id=ws)
    assert so["ok"] is True
    sid = so["data"]["session_id"]

    hb = server.tools["session_heartbeat"](session_id=sid)
    assert hb["ok"] is True and hb["data"]["status"] == "active"

    hb_missing = server.tools["session_heartbeat"](session_id="ghost")
    assert hb_missing["ok"] is False
    assert hb_missing["error"]["code"] == "NOT_FOUND"


def test_unresolved_workspace_via_tool_envelope(
    migrated_factory, tmp_config, tmp_path
):
    deps = make_deps(migrated_factory, tmp_config, StubClock())
    server = FakeServer()
    register(server, deps)
    res = server.tools["workspace_resolve"](
        project_root=str(tmp_path / "nope" / "child")
    )
    assert res["ok"] is False
    assert res["error"]["code"] == "WORKSPACE_UNRESOLVED"


def test_resolve_stale_ttl_env():
    assert _resolve_stale_ttl({}) == DEFAULT_SESSION_STALE_TTL_SECONDS
    assert _resolve_stale_ttl({STALE_TTL_ENV: "15"}) == 15
    assert _resolve_stale_ttl({STALE_TTL_ENV: "  "}) == DEFAULT_SESSION_STALE_TTL_SECONDS
    assert _resolve_stale_ttl({STALE_TTL_ENV: "bad"}) == DEFAULT_SESSION_STALE_TTL_SECONDS
    assert _resolve_stale_ttl({STALE_TTL_ENV: "0"}) == DEFAULT_SESSION_STALE_TTL_SECONDS
    assert _resolve_stale_ttl({STALE_TTL_ENV: "-5"}) == DEFAULT_SESSION_STALE_TTL_SECONDS


def test_build_service_reuses_existing_repos(migrated_factory, tmp_config):
    clock = StubClock()
    deps = make_deps(migrated_factory, tmp_config, clock)
    existing = SqliteWorkspaceRepo(clock)
    deps.repos.workspaces = existing
    build_service(deps, env={STALE_TTL_ENV: "42"})
    assert deps.repos.workspaces is existing  # not overwritten
    assert deps.repos.agents is not None  # filled in


# --------------------------------------------------------------------------- #
# Concurrency
# --------------------------------------------------------------------------- #
def test_concurrent_session_open_unique_ids(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    ws = _seed_ws_agent(svc, tmp_path)
    n = 12
    results: list[str] = []
    lock = threading.Lock()
    barrier = threading.Barrier(n)

    def worker():
        barrier.wait()
        out = retry_db(
            lambda: svc.session_open(agent_id="agent-1", workspace_id=ws)
        )
        with lock:
            results.append(out["session_id"])

    with ThreadPoolExecutor(max_workers=n) as ex:
        futures = [ex.submit(worker) for _ in range(n)]
        for f in futures:
            f.result()

    assert len(results) == n
    assert len(set(results)) == n  # no PK collision
    assert count(migrated_factory, "sessions") == n  # no lost writes


def test_concurrent_writers_distinct_workspaces_no_leak(
    migrated_factory, tmp_config, tmp_path
):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    ws_a = _seed_ws_agent(svc, tmp_path, name="A")
    ws_b = svc.workspace_resolve(project_root=str(mkdir(tmp_path, "B")))["workspace_id"]
    per = 8
    targets = [ws_a] * per + [ws_b] * per
    barrier = threading.Barrier(len(targets))

    def worker(ws):
        barrier.wait()
        retry_db(lambda: svc.session_open(agent_id="agent-1", workspace_id=ws))

    with ThreadPoolExecutor(max_workers=len(targets)) as ex:
        futures = [ex.submit(worker, ws) for ws in targets]
        for f in futures:
            f.result()

    list_a = svc.list_sessions(workspace_id=ws_a)
    list_b = svc.list_sessions(workspace_id=ws_b)
    assert len(list_a) == per
    assert len(list_b) == per
    assert all(r["workspace_id"] == ws_a for r in list_a)  # zero leakage A
    assert all(r["workspace_id"] == ws_b for r in list_b)  # zero leakage B
    assert count(migrated_factory, "sessions") == 2 * per  # zero lost writes


# --------------------------------------------------------------------------- #
# session_close (idempotent)  -- spec ts_bfc06da4 / ac_ff46c0da
# --------------------------------------------------------------------------- #
def test_session_close_idempotent(migrated_factory, tmp_config, tmp_path):
    """First close stamps closed/closed_at; a second close is a no-op {ok:true}."""
    clock = StubClock("2026-06-07T00:00:00Z")
    emitter = FakeEmitter()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=emitter)
    ws = _seed_ws_agent(svc, tmp_path)
    sid = svc.session_open(agent_id="agent-1", workspace_id=ws)["session_id"]

    # First call: marks status='closed' and stamps closed_at.
    clock.set("2026-06-07T00:00:05Z")
    first = svc.session_close(session_id=sid)
    assert first["status"] == "closed"
    assert first["closed_at"] == "2026-06-07T00:00:05Z"
    assert count(migrated_factory, "sessions") == 1
    # Closed status is derived (and persisted) on read.
    assert svc.get_session(session_id=sid)["status"] == "closed"
    closed_emits = [e for e in emitter.events if e["type"] == "session.closed"]
    assert len(closed_emits) == 1  # only the transition emits

    # Second call: idempotent -> succeeds, no error, row stays closed.
    clock.set("2026-06-07T00:10:00Z")  # a much later clock must NOT move closed_at
    second = svc.session_close(session_id=sid)
    assert second["status"] == "closed"
    assert second["closed_at"] == first["closed_at"]  # preserved, not re-stamped
    assert count(migrated_factory, "sessions") == 1  # still exactly one row
    assert svc.get_session(session_id=sid)["status"] == "closed"
    # A repeat close does not emit a second lifecycle event.
    assert len([e for e in emitter.events if e["type"] == "session.closed"]) == 1


def test_session_close_via_tool_envelope_idempotent(
    migrated_factory, tmp_config, tmp_path
):
    """Both close calls return {ok:true} envelopes; unknown id -> NOT_FOUND."""
    deps = make_deps(migrated_factory, tmp_config, StubClock())
    server = FakeServer()
    register(server, deps)

    proj = mkdir(tmp_path, "P")
    ws = server.tools["workspace_resolve"](project_root=str(proj))["data"][
        "workspace_id"
    ]
    server.tools["agent_register"](agent_id="agent-1")
    sid = server.tools["session_open"](agent_id="agent-1", workspace_id=ws)["data"][
        "session_id"
    ]

    c1 = server.tools["session_close"](session_id=sid)
    assert c1["ok"] is True and c1["data"]["status"] == "closed"
    c2 = server.tools["session_close"](session_id=sid)
    assert c2["ok"] is True and c2["data"]["status"] == "closed"
    assert c2["data"]["closed_at"] == c1["data"]["closed_at"]

    missing = server.tools["session_close"](session_id="ghost")
    assert missing["ok"] is False and missing["error"]["code"] == "NOT_FOUND"


def test_session_close_validation_and_not_found(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    with pytest.raises(OktoNexusError) as ei_val:
        svc.session_close(session_id="")
    assert ei_val.value.code == ErrorCode.VALIDATION_ERROR.value
    with pytest.raises(OktoNexusError) as ei_nf:
        svc.session_close(session_id="no-such-session")
    assert ei_nf.value.code == ErrorCode.NOT_FOUND.value


# --------------------------------------------------------------------------- #
# workspace_list global-admin surface  -- spec ts_995c27c5 / ac_083f4f4c
# --------------------------------------------------------------------------- #
def test_workspace_list_global_admin_crosses_workspaces(
    migrated_factory, tmp_config, tmp_path
):
    """workspace_list returns A+B; a workspace-scoped read returns only A."""
    svc = make_service(migrated_factory, tmp_config, StubClock())
    ws_a = _seed_ws_agent(svc, tmp_path, name="A")
    ws_b = svc.workspace_resolve(project_root=str(mkdir(tmp_path, "B")))["workspace_id"]
    s_a = svc.session_open(agent_id="agent-1", workspace_id=ws_a)["session_id"]
    s_b = svc.session_open(agent_id="agent-1", workspace_id=ws_b)["session_id"]

    # GLOBAL-ADMIN surface: sees BOTH workspaces.
    all_ws = svc.workspace_list()
    seen = {w["workspace_id"] for w in all_ws}
    assert {ws_a, ws_b} <= seen

    # Standard workspace-scoped read: only A, never B.
    scoped_a = svc.list_sessions(workspace_id=ws_a)
    assert {r["session_id"] for r in scoped_a} == {s_a}
    assert all(r["workspace_id"] == ws_a for r in scoped_a)
    assert s_b not in {r["session_id"] for r in scoped_a}


def test_workspace_list_tool_global_admin(migrated_factory, tmp_config, tmp_path):
    """Via the MCP tool: workspace_list spans workspaces; list stays scoped."""
    deps = make_deps(migrated_factory, tmp_config, StubClock())
    server = FakeServer()
    register(server, deps)

    ws_a = server.tools["workspace_resolve"](
        project_root=str(mkdir(tmp_path, "A"))
    )["data"]["workspace_id"]
    ws_b = server.tools["workspace_resolve"](
        project_root=str(mkdir(tmp_path, "B"))
    )["data"]["workspace_id"]

    res = server.tools["workspace_list"]()
    assert res["ok"] is True
    ids = {w["workspace_id"] for w in res["data"]["workspaces"]}
    assert {ws_a, ws_b} <= ids  # global-admin crosses workspaces


# --------------------------------------------------------------------------- #
# Concurrency: heartbeat vs stale read  -- spec ts_b87fdebd / ac_12db4f07
# --------------------------------------------------------------------------- #
def test_concurrent_heartbeat_vs_stale_read(migrated_factory, tmp_config, tmp_path):
    """Heartbeat writers and status readers near the TTL never tear or DB_ERROR.

    A session is opened at T0 and the clock is advanced past the stale TTL so a
    bare read derives 'stale' while a fresh heartbeat (writing the current
    clock) derives 'active'. Concurrently firing both must ALWAYS yield a whole,
    valid status ('active' or 'stale', never partial) with no escaping DB_ERROR
    under WAL + busy_timeout=5000.
    """
    ttl = 60
    clock = StubClock("2026-06-07T00:00:00Z")
    svc = make_service(migrated_factory, tmp_config, clock, stale_ttl=ttl)
    ws = _seed_ws_agent(svc, tmp_path)
    sid = svc.session_open(agent_id="agent-1", workspace_id=ws)["session_id"]

    # Position the clock past the TTL: a read with no fresh heartbeat is 'stale'.
    clock.set("2026-06-07T00:01:30Z")  # +90s > ttl=60

    readers = 8
    writers = 8
    rounds = 6
    statuses: list[str] = []
    errors: list[Exception] = []
    lock = threading.Lock()
    barrier = threading.Barrier(readers + writers)

    def reader():
        barrier.wait()
        for _ in range(rounds):
            try:
                out = retry_db(lambda: svc.get_session(session_id=sid))
            except Exception as exc:  # noqa: BLE001 - capture for assertion
                with lock:
                    errors.append(exc)
                return
            with lock:
                statuses.append(out["status"])

    def writer():
        barrier.wait()
        for _ in range(rounds):
            try:
                retry_db(lambda: svc.session_heartbeat(session_id=sid))
            except Exception as exc:  # noqa: BLE001 - capture for assertion
                with lock:
                    errors.append(exc)
                return

    with ThreadPoolExecutor(max_workers=readers + writers) as ex:
        futures = [ex.submit(reader) for _ in range(readers)]
        futures += [ex.submit(writer) for _ in range(writers)]
        for f in futures:
            f.result()

    # No exception (no unrecovered DB_ERROR) escaped under busy_timeout.
    assert not errors, f"concurrent ops raised: {errors}"
    # Every read returned a whole, valid status - never a partial/torn state.
    assert statuses, "expected reader observations"
    assert set(statuses) <= {"active", "stale"}
    # The row is intact and still readable after the storm.
    final = svc.get_session(session_id=sid)
    assert final["status"] in {"active", "stale"}
    assert count(migrated_factory, "sessions") == 1
