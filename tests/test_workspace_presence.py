"""Workspace overview presence is per DISTINCT AGENT, not per session.

A workspace accumulates many (mostly closed) session rows over time, so counting
sessions made "Agents in workspace" explode (e.g. 0/0/83 for 3 agents). The
presence rollup must reduce sessions to the best state per agent; stale_sessions
(a health signal) stays session-based.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteSessionRepo
from okto_nexus.adapters.outbound.sqlite.observability_repo import (
    SqliteObservabilityQueries,
)
from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.application.observability import ObservabilityService
from okto_nexus.application.workspace_overview import WorkspaceListService


@pytest.fixture
def svc_and_deps(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    if getattr(deps.repos, "sessions", None) is None:
        deps.repos.sessions = SqliteSessionRepo(deps.clock)
    queries = SqliteObservabilityQueries()
    obs = ObservabilityService(queries, deps.clock, deps.config)
    svc = WorkspaceListService(
        connection_factory=deps.connection_factory,
        queries=queries,
        workspaces=deps.repos.workspaces,
        observability=obs,
        clock=deps.clock,
        config=deps.config,
    )
    return svc, deps


def _item(svc, wid):
    return next(w for w in svc.list_workspaces() if w["workspace_id"] == wid)


def test_presence_counts_distinct_agents_not_sessions(svc_and_deps):
    svc, deps = svc_and_deps
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id="ws-a")
        deps.repos.agents.upsert(uow, agent_id="ag1")
        # 5 closed sessions for the SAME agent (the bug: this used to read 5).
        for i in range(5):
            deps.repos.sessions.create(
                uow,
                session_id=f"s{i}",
                agent_id="ag1",
                workspace_id="ws-a",
                status="closed",
            )
    presence = _item(svc, "ws-a")["presence"]
    assert presence == {"present": 0, "stale": 0, "offline": 1}  # 1 agent, offline


def test_presence_present_when_any_session_active(svc_and_deps):
    svc, deps = svc_and_deps
    now = deps.clock.now_iso()
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id="ws-b")
        deps.repos.agents.upsert(uow, agent_id="ag1")
        deps.repos.agents.upsert(uow, agent_id="ag2")
        # ag1: one closed + one active+fresh-heartbeat -> best state is present.
        deps.repos.sessions.create(
            uow, session_id="c1", agent_id="ag1", workspace_id="ws-b", status="closed"
        )
        deps.repos.sessions.create(
            uow, session_id="a1", agent_id="ag1", workspace_id="ws-b", status="active"
        )
        deps.repos.sessions.heartbeat(uow, session_id="a1", at=now)
        # ag2: only a closed session -> offline.
        deps.repos.sessions.create(
            uow, session_id="c2", agent_id="ag2", workspace_id="ws-b", status="closed"
        )
    presence = _item(svc, "ws-b")["presence"]
    # 2 distinct agents: ag1 present (has an active fresh session), ag2 offline.
    assert presence == {"present": 1, "stale": 0, "offline": 1}


def test_recent_activity_reads_present_without_a_live_session(svc_and_deps):
    """The claude-validator case: an agent that pulls its durable inbox WITHOUT
    an open session (all sessions closed/reaped) but whose last_seen_at was just
    bumped by the action reads PRESENT - activity drives presence, not only the
    session heartbeat."""
    svc, deps = svc_and_deps
    now = deps.clock.now_iso()
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id="ws-c")
        deps.repos.agents.upsert(uow, agent_id="validator")
        # Only a CLOSED session remains (the live one was reaped)...
        deps.repos.sessions.create(
            uow,
            session_id="c1",
            agent_id="validator",
            workspace_id="ws-c",
            status="closed",
        )
        # ...but the agent just acted (inbox_pull bumps last_seen_at).
        deps.repos.agents.touch(uow, agent_id="validator", at=now)
    presence = _item(svc, "ws-c")["presence"]
    assert presence == {"present": 1, "stale": 0, "offline": 0}


def test_presence_buckets_by_activity_age(svc_and_deps):
    """With no live session, the agent's last_seen_at age alone buckets it:
    fresh -> present, within presence_ttl -> stale, beyond it -> offline."""
    svc, deps = svc_and_deps
    now_e = deps.clock.now_epoch()

    def iso(delta: float) -> str:
        dt = datetime.fromtimestamp(now_e + delta, tz=timezone.utc)
        return dt.isoformat(timespec="microseconds").replace("+00:00", "Z")

    stale_ttl = deps.config.session_stale_ttl_seconds
    presence_ttl = deps.config.presence_ttl_seconds
    ages = {
        "fresh": -5,
        "recent": -(stale_ttl + 30),
        "old": -(presence_ttl + 30),
    }
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id="ws-d")
        for aid, age in ages.items():
            deps.repos.agents.upsert(uow, agent_id=aid)
            deps.repos.sessions.create(
                uow,
                session_id=f"s-{aid}",
                agent_id=aid,
                workspace_id="ws-d",
                status="closed",
            )
            deps.repos.agents.touch(uow, agent_id=aid, at=iso(age))
    presence = _item(svc, "ws-d")["presence"]
    assert presence == {"present": 1, "stale": 1, "offline": 1}
