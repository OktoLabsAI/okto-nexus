"""The graph node carries each agent's LAST ACTION — the real coordination
verb from the event log — so the dashboard's entity card can render "x <verb>"
with a relative-time reference instead of a bare presence dot.

Backend contract (spec 5e1fa07c, card C1):

* ``SqliteObservabilityQueries.last_actions_by_agent`` returns, per actor, the
  ``type`` + ``created_at`` of the agent's HIGHEST-``event_id`` event — one
  GROUP-BY for the whole graph (anti-N+1), scoped to the workspace when given.
* ``ObservabilityService.graph_snapshot`` folds that into ``node["last_action"]``
  as ``{"type", "at"}`` or ``None`` when the agent has no event in scope.

Exercised over the REAL SQLite adapters (``migrated_factory``), events emitted
through the real emitter so the vocabulary gate and AUTOINCREMENT ordering are
the ones production uses.
"""

from __future__ import annotations

from datetime import datetime, timezone

from okto_nexus.adapters.outbound.sqlite.events_repo import (
    SqliteEventEmitter,
    SqliteEventRepo,
)
from okto_nexus.adapters.outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteSessionRepo,
    SqliteWorkspaceRepo,
)
from okto_nexus.adapters.outbound.sqlite.observability_repo import (
    SqliteObservabilityQueries,
)
from okto_nexus.application.identity import IdentityService
from okto_nexus.application.observability import ObservabilityService
from okto_nexus.config import NexusConfig
from okto_nexus.domain.base import iso_to_epoch


# --------------------------------------------------------------------------- #
# Deterministic, advanceable clock (mirrors the presence tests)
# --------------------------------------------------------------------------- #
class StubClock:
    def __init__(self, iso: str = "2026-07-06T00:00:00.000000Z") -> None:
        self._iso = iso

    def now_iso(self) -> str:
        return self._iso

    def now_epoch(self) -> float:
        return iso_to_epoch(self._iso)

    def advance_seconds(self, seconds: float) -> None:
        dt = datetime.fromtimestamp(self.now_epoch() + seconds, tz=timezone.utc)
        self._iso = dt.isoformat(timespec="microseconds").replace("+00:00", "Z")


class FakeEmitter:
    """No-op emitter for IdentityService (its own events are irrelevant here)."""

    def emit(self, uow, **kwargs) -> int:
        return 0


def _config(tmp_path) -> NexusConfig:
    return NexusConfig(home_dir=tmp_path / "okto_home")


def _identity(factory, config, clock) -> IdentityService:
    return IdentityService(
        connection_factory=factory,
        workspaces=SqliteWorkspaceRepo(clock),
        agents=SqliteAgentRepo(clock),
        sessions=SqliteSessionRepo(clock),
        clock=clock,
        config=config,
        event_emitter=FakeEmitter(),
    )


def _mkproj(tmp_path, name):
    p = tmp_path / name
    p.mkdir()
    return str(p)


def _seed_ws(identity, project_root, *agents) -> str:
    ws = identity.workspace_resolve(project_root=project_root)["workspace_id"]
    for agent in agents:
        identity.agent_register(agent_id=agent)
    return ws


def _emit(factory, clock, *, workspace_id, type, actor):
    """Append one event through the real emitter (inside its own UoW)."""
    emitter = SqliteEventEmitter(SqliteEventRepo(clock))
    with factory.unit_of_work() as uow:
        emitter.emit(
            uow,
            workspace_id=workspace_id,
            stream="agent",
            type=type,
            actor_agent_id=actor,
        )


# --------------------------------------------------------------------------- #
# TS-1: the aggregate returns the MAX(event_id) row's type + at, per actor
# --------------------------------------------------------------------------- #
def test_last_action_is_the_most_recent_event_per_actor(migrated_factory, tmp_path):
    clock = StubClock()
    config = _config(tmp_path)
    identity = _identity(migrated_factory, config, clock)
    proj = _mkproj(tmp_path, "P")
    ws = _seed_ws(identity, proj, "alice", "bob")

    # alice acts twice; the SECOND (later, higher event_id) must win.
    _emit(
        migrated_factory, clock, workspace_id=ws, type="message.created", actor="alice"
    )
    clock.advance_seconds(90)
    _emit(
        migrated_factory, clock, workspace_id=ws, type="handoff.claimed", actor="alice"
    )
    winning_at = clock.now_iso()
    # bob acts once.
    clock.advance_seconds(30)
    _emit(migrated_factory, clock, workspace_id=ws, type="message.created", actor="bob")
    bob_at = clock.now_iso()

    queries = SqliteObservabilityQueries()
    with migrated_factory.unit_of_work() as uow:
        actions = queries.last_actions_by_agent(uow, workspace_id=ws)

    assert actions["alice"] == {"type": "handoff.claimed", "at": winning_at}
    assert actions["bob"] == {"type": "message.created", "at": bob_at}


# --------------------------------------------------------------------------- #
# TS-2: an agent with no events has NO last_action (absent -> node None)
# --------------------------------------------------------------------------- #
def test_agent_without_events_has_no_last_action(migrated_factory, tmp_path):
    clock = StubClock()
    config = _config(tmp_path)
    identity = _identity(migrated_factory, config, clock)
    proj = _mkproj(tmp_path, "P")
    ws = _seed_ws(identity, proj, "alice", "idle")

    _emit(
        migrated_factory, clock, workspace_id=ws, type="message.created", actor="alice"
    )

    queries = SqliteObservabilityQueries()
    with migrated_factory.unit_of_work() as uow:
        actions = queries.last_actions_by_agent(uow, workspace_id=ws)
    # 'idle' never acted -> absent from the map.
    assert "idle" not in actions
    assert "alice" in actions

    # And the graph node reflects that as an explicit None (card body: "no
    # recent activity"), while the acting agent carries the folded action.
    obs = ObservabilityService(queries, clock, config)
    with migrated_factory.unit_of_work() as uow:
        snapshot = obs.graph_snapshot(uow, workspace_id=ws)
    nodes = {n["agent_id"]: n for n in snapshot["nodes"]}
    assert nodes["idle"]["last_action"] is None
    assert nodes["alice"]["last_action"] == {
        "type": "message.created",
        "at": clock.now_iso(),
    }


# --------------------------------------------------------------------------- #
# TS-3: last_action is workspace-scoped; None (All) spans every workspace
# --------------------------------------------------------------------------- #
def test_last_action_is_workspace_scoped(migrated_factory, tmp_path):
    clock = StubClock()
    config = _config(tmp_path)
    identity = _identity(migrated_factory, config, clock)
    proj_a = _mkproj(tmp_path, "A")
    proj_b = _mkproj(tmp_path, "B")
    ws_a = _seed_ws(identity, proj_a, "alice")
    ws_b = _seed_ws(identity, proj_b, "alice")  # same global agent, two workspaces

    _emit(
        migrated_factory,
        clock,
        workspace_id=ws_a,
        type="message.created",
        actor="alice",
    )
    at_a = clock.now_iso()
    clock.advance_seconds(120)
    _emit(
        migrated_factory,
        clock,
        workspace_id=ws_b,
        type="handoff.completed",
        actor="alice",
    )
    at_b = clock.now_iso()

    queries = SqliteObservabilityQueries()
    with migrated_factory.unit_of_work() as uow:
        only_a = queries.last_actions_by_agent(uow, workspace_id=ws_a)
        only_b = queries.last_actions_by_agent(uow, workspace_id=ws_b)
        across = queries.last_actions_by_agent(uow, workspace_id=None)

    # Scoped views see only their own workspace's event.
    assert only_a["alice"] == {"type": "message.created", "at": at_a}
    assert only_b["alice"] == {"type": "handoff.completed", "at": at_b}
    # The "All workspaces" view (None) collapses to the globally-latest event.
    assert across["alice"] == {"type": "handoff.completed", "at": at_b}
