"""The graph node carries the ENRICHED card payload — the agent display color,
its tags, and two workspace-scoped counts (pending-inbox depth + open-handoff
involvement) — so the dashboard entity card can render a colored header, chips
and self-hiding badges.

Backend contract (spec 2d6920f4, cards C1/C2):

* ``SqliteAgentRepo.set_color`` persists a per-agent color and a ``None`` value
  resets it to auto-by-identity, leaving role/capabilities/metadata untouched
  (mirrors ``set_tags``).
* ``SqliteObservabilityQueries.inbox_depth_by_agent`` counts the PHYSICAL
  not-yet-read lanes (unread + delivered) per recipient, excludes read/parked,
  and is workspace-scoped (``None`` = all workspaces) — ONE GROUP-BY.
* ``SqliteObservabilityQueries.open_handoffs_by_agent`` counts NON-TERMINAL
  handoffs (OPEN/CLAIMED/VERIFYING) attributed to BOTH the origin
  (``from_agent_id``) and the holder (``claimed_by``) via a UNION ALL, excludes
  terminal, and is workspace-scoped.
* ``ObservabilityService.graph_snapshot`` folds ``color``/``tags``/
  ``pending_inbox``/``open_handoffs`` into EVERY node.

Exercised over the REAL migrated SQLite adapters (``migrated_factory``); the
message/delivery/handoff rows are seeded directly so the aggregation SQL — the
contract under test — runs against the production schema with precise lane and
status control.
"""

from __future__ import annotations

from datetime import datetime, timezone

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
# Harness (mirrors tests/test_graph_last_action.py)
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


def _insert_message(factory, *, message_id, workspace_id, from_agent, created_at):
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "INSERT INTO messages "
            "(message_id, workspace_id, from_agent_id, created_at) "
            "VALUES (?, ?, ?, ?)",
            (message_id, workspace_id, from_agent, created_at),
        )


def _insert_delivery(
    factory, *, delivery_id, message_id, recipient, status, created_at
):
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "INSERT INTO message_deliveries "
            "(delivery_id, message_id, recipient_agent_id, status, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (delivery_id, message_id, recipient, status, created_at),
        )


def _insert_handoff(
    factory, *, handoff_id, workspace_id, from_agent, claimed_by, status, created_at
):
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "INSERT INTO handoffs "
            "(handoff_id, workspace_id, from_agent_id, claimed_by, status, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (handoff_id, workspace_id, from_agent, claimed_by, status, created_at),
        )


# --------------------------------------------------------------------------- #
# T1a / ts_040234ea: set_color persists; null resets; siblings untouched
# --------------------------------------------------------------------------- #
def test_set_color_persists_and_null_resets(migrated_factory):
    clock = StubClock()
    repo = SqliteAgentRepo(clock)
    with migrated_factory.unit_of_work() as uow:
        repo.upsert(
            uow,
            agent_id="alice",
            role="dev",
            capabilities={"lang": ["py"]},
            metadata={"team": "core"},
        )
        assert repo.set_color(uow, agent_id="alice", color="#22c55e") is True
        a = repo.get(uow, "alice")
        assert a.color == "#22c55e"
        # Sibling fields are untouched by a color write.
        assert a.role == "dev"
        assert a.capabilities == {"lang": ["py"]}
        assert a.metadata == {"team": "core"}

        # Explicit None clears back to auto-by-identity, siblings still intact.
        assert repo.set_color(uow, agent_id="alice", color=None) is True
        a2 = repo.get(uow, "alice")
        assert a2.color is None
        assert a2.role == "dev"
        assert a2.capabilities == {"lang": ["py"]}
        assert a2.metadata == {"team": "core"}

        # Unknown agent -> no row updated.
        assert repo.set_color(uow, agent_id="ghost", color="#000000") is False


# --------------------------------------------------------------------------- #
# T1a / ts_79365959: graph_snapshot folds the 4 enrichment keys into every node
# --------------------------------------------------------------------------- #
def test_graph_snapshot_folds_enrichment_into_every_node(migrated_factory, tmp_path):
    clock = StubClock()
    config = _config(tmp_path)
    identity = _identity(migrated_factory, config, clock)
    proj = _mkproj(tmp_path, "P")
    ws = _seed_ws(identity, proj, "alice", "bob", "idle")

    repo = SqliteAgentRepo(clock)
    with migrated_factory.unit_of_work() as uow:
        repo.set_color(uow, agent_id="alice", color="#8b5cf6")
        repo.set_tags(uow, agent_id="alice", tags={"team": ["core"]})

    # alice: one unread delivery + originates h1 (OPEN) and h2 (CLAIMED by bob).
    _insert_message(
        migrated_factory,
        message_id="m1",
        workspace_id=ws,
        from_agent="bob",
        created_at=clock.now_iso(),
    )
    _insert_delivery(
        migrated_factory,
        delivery_id="d1",
        message_id="m1",
        recipient="alice",
        status="unread",
        created_at=clock.now_iso(),
    )
    _insert_handoff(
        migrated_factory,
        handoff_id="h1",
        workspace_id=ws,
        from_agent="alice",
        claimed_by=None,
        status="OPEN",
        created_at=clock.now_iso(),
    )
    _insert_handoff(
        migrated_factory,
        handoff_id="h2",
        workspace_id=ws,
        from_agent="alice",
        claimed_by="bob",
        status="CLAIMED",
        created_at=clock.now_iso(),
    )

    queries = SqliteObservabilityQueries()
    obs = ObservabilityService(queries, clock, config)
    with migrated_factory.unit_of_work() as uow:
        snapshot = obs.graph_snapshot(uow, workspace_id=ws)
    nodes = {n["agent_id"]: n for n in snapshot["nodes"]}

    # EVERY node carries the four enrichment keys (present, defaulted).
    for node in nodes.values():
        assert "color" in node
        assert "tags" in node
        assert "pending_inbox" in node
        assert "open_handoffs" in node

    assert nodes["alice"]["color"] == "#8b5cf6"
    assert nodes["alice"]["tags"] == {"team": ["core"]}
    assert nodes["alice"]["pending_inbox"] == 1
    # alice originates h1 + h2 -> 2 open-handoff involvements (origin arm).
    assert nodes["alice"]["open_handoffs"] == 2
    # bob holds h2 -> 1; no deliveries queued for bob.
    assert nodes["bob"]["open_handoffs"] == 1
    assert nodes["bob"]["pending_inbox"] == 0
    # idle: unset color, no tags, zero counts.
    assert nodes["idle"]["color"] is None
    assert nodes["idle"]["tags"] == {}
    assert nodes["idle"]["pending_inbox"] == 0
    assert nodes["idle"]["open_handoffs"] == 0


# --------------------------------------------------------------------------- #
# T1b / ts_0768c4ea: inbox_depth counts unread+delivered, excludes read/parked,
# workspace-scoped with a None=all-workspaces mode
# --------------------------------------------------------------------------- #
def test_inbox_depth_counts_physical_lane_scoped(migrated_factory, tmp_path):
    clock = StubClock()
    config = _config(tmp_path)
    identity = _identity(migrated_factory, config, clock)
    ws_a = _seed_ws(identity, _mkproj(tmp_path, "A"), "alice", "bob")
    ws_b = _seed_ws(identity, _mkproj(tmp_path, "B"), "alice")

    # ws_a: alice unread + delivered (both count) + read (excluded); bob parked
    # (excluded). Distinct messages per (message, recipient) UNIQUE constraint.
    for mid in ("m1", "m2", "m3", "m4"):
        _insert_message(
            migrated_factory,
            message_id=mid,
            workspace_id=ws_a,
            from_agent="bob",
            created_at=clock.now_iso(),
        )
    _insert_delivery(
        migrated_factory,
        delivery_id="d1",
        message_id="m1",
        recipient="alice",
        status="unread",
        created_at=clock.now_iso(),
    )
    _insert_delivery(
        migrated_factory,
        delivery_id="d2",
        message_id="m2",
        recipient="alice",
        status="delivered",
        created_at=clock.now_iso(),
    )
    _insert_delivery(
        migrated_factory,
        delivery_id="d3",
        message_id="m3",
        recipient="alice",
        status="read",
        created_at=clock.now_iso(),
    )
    _insert_delivery(
        migrated_factory,
        delivery_id="d4",
        message_id="m4",
        recipient="bob",
        status="parked",
        created_at=clock.now_iso(),
    )
    # ws_b: alice has a single unread delivery in a DIFFERENT workspace.
    _insert_message(
        migrated_factory,
        message_id="m5",
        workspace_id=ws_b,
        from_agent="bob",
        created_at=clock.now_iso(),
    )
    _insert_delivery(
        migrated_factory,
        delivery_id="d5",
        message_id="m5",
        recipient="alice",
        status="unread",
        created_at=clock.now_iso(),
    )

    queries = SqliteObservabilityQueries()
    with migrated_factory.unit_of_work() as uow:
        depth_a = queries.inbox_depth_by_agent(uow, workspace_id=ws_a)
        depth_b = queries.inbox_depth_by_agent(uow, workspace_id=ws_b)
        depth_all = queries.inbox_depth_by_agent(uow, workspace_id=None)

    # ws_a: alice counts unread+delivered only (read excluded) = 2; bob's only
    # delivery is 'parked' -> excluded -> absent from the map.
    assert depth_a.get("alice") == 2
    assert "bob" not in depth_a
    # ws_b: alice has exactly the one unread there.
    assert depth_b.get("alice") == 1
    # All-workspaces: alice = 2 (ws_a) + 1 (ws_b) = 3; bob still 0.
    assert depth_all.get("alice") == 3
    assert "bob" not in depth_all


# --------------------------------------------------------------------------- #
# T2 / ts_3dc48024: open_handoffs by owner (claimed_by) AND awaiter
# (from_agent_id), excludes terminal, workspace-scoped with None=all
# --------------------------------------------------------------------------- #
def test_open_handoffs_by_owner_and_awaiter_scoped(migrated_factory, tmp_path):
    clock = StubClock()
    config = _config(tmp_path)
    identity = _identity(migrated_factory, config, clock)
    ws_a = _seed_ws(identity, _mkproj(tmp_path, "A"), "alice", "bob", "carol")
    ws_b = _seed_ws(identity, _mkproj(tmp_path, "B"), "alice")

    # ws_a non-terminal:
    #   h1 OPEN      from alice, unclaimed        -> alice(origin)
    #   h2 CLAIMED   from alice, held by bob      -> alice(origin) + bob(holder)
    #   h3 VERIFYING from bob,   held by carol    -> bob(origin) + carol(holder)
    # ws_a terminal (must NOT count):
    #   h4 COMPLETED from alice, held by bob
    #   h5 REJECTED  from alice, held by carol
    # ws_b non-terminal:
    #   h6 OPEN      from alice, unclaimed        -> alice(origin), ws_b only
    seed = [
        ("h1", ws_a, "alice", None, "OPEN"),
        ("h2", ws_a, "alice", "bob", "CLAIMED"),
        ("h3", ws_a, "bob", "carol", "VERIFYING"),
        ("h4", ws_a, "alice", "bob", "COMPLETED"),
        ("h5", ws_a, "alice", "carol", "REJECTED"),
        ("h6", ws_b, "alice", None, "OPEN"),
    ]
    for hid, ws, frm, held, status in seed:
        _insert_handoff(
            migrated_factory,
            handoff_id=hid,
            workspace_id=ws,
            from_agent=frm,
            claimed_by=held,
            status=status,
            created_at=clock.now_iso(),
        )

    queries = SqliteObservabilityQueries()
    with migrated_factory.unit_of_work() as uow:
        oh_a = queries.open_handoffs_by_agent(uow, workspace_id=ws_a)
        oh_b = queries.open_handoffs_by_agent(uow, workspace_id=ws_b)
        oh_all = queries.open_handoffs_by_agent(uow, workspace_id=None)

    # ws_a: alice = h1 + h2 (origin) = 2; bob = h2 (holder) + h3 (origin) = 2;
    # carol = h3 (holder) = 1. Terminal h4/h5 contribute nothing.
    assert oh_a.get("alice") == 2
    assert oh_a.get("bob") == 2
    assert oh_a.get("carol") == 1
    # ws_b: only h6 -> alice = 1; nobody else present.
    assert oh_b.get("alice") == 1
    assert "bob" not in oh_b
    assert "carol" not in oh_b
    # All-workspaces: alice = h1,h2 (ws_a) + h6 (ws_b) = 3; bob = 2; carol = 1.
    assert oh_all.get("alice") == 3
    assert oh_all.get("bob") == 2
    assert oh_all.get("carol") == 1
