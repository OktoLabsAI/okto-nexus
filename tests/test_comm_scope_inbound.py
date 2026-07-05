"""Inbound communication-scope enforcement (F2 / C2-C5).

F2 makes reachability a DOUBLE intersection: a sender reaches a recipient
only when the sender's ``comm_scope.outbound`` admits the recipient's tags
AND the recipient's ``comm_scope.inbound`` admits the sender's tags (self is
always reachable). This file exercises the four enforcement surfaces over the
real services + SQLite adapters (``bootstrap`` deps):

* messages (AC3/AC4): a directed send blocked by the RECIPIENT's inbound is
  ``PERMISSION_DENIED`` byte-identical to the outbound denial (the blocking
  side never leaks); group fan-outs drop inbound-excluded recipients
  SILENTLY - no count, no warning (recipient policy, not sender concern);
* handoffs (AC5): claim/list are bounded by full reachability between
  creator and claimant, evaluated dynamically; outcome notifications honour
  the recipient's inbound silently;
* discovery (AC6): ``agent_list``/``capability_list`` show only reachable
  agents (plus self); an unreachable ``agent_get`` reads as ``NOT_FOUND``
  byte-identical to a non-existent id; anonymous/operator callers unfiltered;
* event stream (AC7): events whose actor is outside the viewer's reach are
  omitted (own and actor-less events always show); unscoped viewers see all.
"""

from __future__ import annotations

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.inbound.mcp.tools.events import (
    build_service as build_event_service,
)
from okto_nexus.adapters.inbound.mcp.tools.handoff import (
    build_service as build_handoff_service,
)
from okto_nexus.adapters.inbound.mcp.tools.identity import (
    build_service as build_identity_service,
)
from okto_nexus.adapters.inbound.mcp.tools.messages import (
    build_service as build_message_service,
)
from okto_nexus.domain.ids import resolve_realpath, resolve_workspace_id
from okto_nexus.errors import ErrorCode, OktoNexusError

#: The recipient-side gate: only senders tagged sector=OPS may get in.
INBOUND_OPS = {"inbound": {"sector": ["OPS"]}}
INBOUND_DEV = {"inbound": {"sector": ["DEV"]}}
TAGS_DEV = {"sector": ["DEV"]}


@pytest.fixture
def deps(tmp_path):
    return bootstrap({}, ["--home", str(tmp_path / "home")])


def _register(
    deps, agent_id: str, *, role=None, capabilities=None, tags=None, comm_scope=None
):
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(
            uow, agent_id=agent_id, role=role, capabilities=capabilities
        )
        if tags is not None:
            deps.repos.agents.set_tags(uow, agent_id=agent_id, tags=tags)
        if comm_scope is not None:
            deps.repos.agents.set_comm_scope(
                uow, agent_id=agent_id, comm_scope=comm_scope
            )


def _set_comm_scope(deps, agent_id: str, comm_scope):
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.set_comm_scope(uow, agent_id=agent_id, comm_scope=comm_scope)


def _ensure_workspace(deps, project_root: str) -> str:
    ws = resolve_workspace_id(project_root)
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(
            uow,
            workspace_id=ws,
            root_realpath=resolve_realpath(project_root),
            last_seen_at=deps.clock.now_iso(),
        )
    return ws


def _count(deps, table: str) -> int:
    conn = deps.connection_factory.get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# AC3 - directed sends blocked by the recipient's inbound
# --------------------------------------------------------------------------- #
def test_direct_blocked_by_recipient_inbound_is_opaque_permission_denied(
    deps, tmp_path
):
    service = build_message_service(deps)
    _register(deps, "dev", tags=TAGS_DEV)
    _register(deps, "guarded", comm_scope=INBOUND_OPS)

    with pytest.raises(OktoNexusError) as exc:
        service.create_message(
            project_root=str(tmp_path),
            from_agent_id="dev",
            subject="s",
            body="b",
            target={"strategy": "direct", "agent_id": "guarded"},
        )
    assert exc.value.code == ErrorCode.PERMISSION_DENIED
    # OPAQUE: the denial never says WHICH side blocked, nor any tag data.
    assert exc.value.details == {"required_permission": "comm_scope.outbound"}
    for secret in ("sector", "DEV", "OPS", "inbound"):
        assert secret not in exc.value.message
    # Fail-closed rollback: nothing persisted.
    assert _count(deps, "messages") == 0
    assert _count(deps, "message_deliveries") == 0
    assert _count(deps, "events") == 0


def test_inbound_and_outbound_denials_are_byte_identical(deps, tmp_path):
    service = build_message_service(deps)
    # Pair 1 - blocked by the SENDER's outbound (the F1 leg).
    _register(deps, "shy", comm_scope={"outbound": {"team": ["core"]}})
    _register(deps, "eve", tags={"team": ["research"]})
    # Pair 2 - blocked by the RECIPIENT's inbound (the F2 leg).
    _register(deps, "dev", tags=TAGS_DEV)
    _register(deps, "guarded", comm_scope=INBOUND_OPS)

    def denial(from_agent_id, to_agent_id):
        with pytest.raises(OktoNexusError) as exc:
            service.create_message(
                project_root=str(tmp_path),
                from_agent_id=from_agent_id,
                subject="s",
                body="b",
                target={"strategy": "direct", "agent_id": to_agent_id},
            )
        return exc.value

    outbound_err = denial("shy", "eve")
    inbound_err = denial("dev", "guarded")
    assert inbound_err.code == outbound_err.code
    assert inbound_err.message == outbound_err.message
    assert inbound_err.details == outbound_err.details


def test_direct_delivers_once_recipient_inbound_admits_sender(deps, tmp_path):
    service = build_message_service(deps)
    _register(deps, "dev", tags=TAGS_DEV)
    _register(deps, "guarded", comm_scope=INBOUND_OPS)

    with pytest.raises(OktoNexusError):
        service.create_message(
            project_root=str(tmp_path),
            from_agent_id="dev",
            subject="s",
            body="b",
            target={"strategy": "direct", "agent_id": "guarded"},
        )

    # The scope is read at SEND time: relaxing it unblocks the next send.
    _set_comm_scope(deps, "guarded", INBOUND_DEV)
    out = service.create_message(
        project_root=str(tmp_path),
        from_agent_id="dev",
        subject="s",
        body="b",
        target={"strategy": "direct", "agent_id": "guarded"},
    )
    assert out["recipients"] == ["guarded"]
    assert out["delivered_count"] == 1


def test_direct_self_send_ignores_own_inbound(deps, tmp_path):
    # Self is ALWAYS reachable: an agent whose inbound excludes its own tags
    # can still message itself (the reachable() carve-out).
    service = build_message_service(deps)
    _register(deps, "me", tags=TAGS_DEV, comm_scope=INBOUND_OPS)

    out = service.create_message(
        project_root=str(tmp_path),
        from_agent_id="me",
        subject="s",
        body="b",
        target={"strategy": "direct", "agent_id": "me"},
    )
    assert out["recipients"] == ["me"]


# --------------------------------------------------------------------------- #
# AC4 - group fan-outs drop inbound-excluded recipients SILENTLY
# --------------------------------------------------------------------------- #
def test_role_fanout_drops_inbound_excluded_recipients_silently(deps, tmp_path):
    service = build_message_service(deps)
    _register(deps, "dev", tags=TAGS_DEV)
    _register(deps, "bob", role="worker")
    _register(deps, "zed", role="worker", comm_scope=INBOUND_OPS)

    out = service.create_message(
        project_root=str(tmp_path),
        from_agent_id="dev",
        subject="s",
        body="b",
        target={"strategy": "role", "role": "worker"},
    )
    # zed vanished with NO trace: a recipient's inbound is its own policy,
    # never surfaced to the sender (unlike the sender's own outbound).
    assert out["recipients"] == ["bob"]
    assert out["delivered_count"] == 1
    assert "filtered_by_audience" not in out
    assert "warning" not in out
    assert _count(deps, "message_deliveries") == 1


def test_fanout_outbound_warns_while_inbound_stays_silent(deps, tmp_path):
    service = build_message_service(deps)
    _register(deps, "dev", tags=TAGS_DEV, comm_scope={"outbound": {"team": ["core"]}})
    _register(deps, "bob", role="worker", tags={"team": ["core"]})
    _register(deps, "eve", role="worker", tags={"team": ["research"]})
    _register(
        deps, "zed", role="worker", tags={"team": ["core"]}, comm_scope=INBOUND_OPS
    )

    out = service.create_message(
        project_root=str(tmp_path),
        from_agent_id="dev",
        subject="s",
        body="b",
        target={"strategy": "role", "role": "worker"},
    )
    # eve (outbound leg) is counted + warned; zed (inbound leg) is not.
    assert out["recipients"] == ["bob"]
    assert out["filtered_by_audience"] == 1
    assert "comm_scope.outbound" in out["warning"]
    assert _count(deps, "message_deliveries") == 1


def test_role_fanout_all_inbound_excluded_delivers_to_nobody(deps, tmp_path):
    service = build_message_service(deps)
    _register(deps, "dev", tags=TAGS_DEV)
    _register(deps, "zed", role="worker", comm_scope=INBOUND_OPS)

    out = service.create_message(
        project_root=str(tmp_path),
        from_agent_id="dev",
        subject="s",
        body="b",
        target={"strategy": "role", "role": "worker"},
    )
    assert out["recipients"] == []
    assert out["delivered_count"] == 0
    assert "warning" not in out
    # The message row persists (a zero-recipient group send stays legal).
    assert _count(deps, "messages") == 1
    assert _count(deps, "message_deliveries") == 0


# --------------------------------------------------------------------------- #
# AC5 - handoffs: claim/list bounded by full reachability, dynamic
# --------------------------------------------------------------------------- #
def test_handoff_claim_blocked_when_creator_outside_claimant_inbound(deps, tmp_path):
    handoffs = build_handoff_service(deps)
    root = str(tmp_path)
    _ensure_workspace(deps, root)
    _register(deps, "boss", tags=TAGS_DEV)
    _register(deps, "picky", role="worker", comm_scope=INBOUND_OPS)

    hid = handoffs.handoff_create(
        project_root=root,
        from_agent_id="boss",
        target={"strategy": "role", "role": "worker"},
        visibility="public",
    )["handoff_id"]

    with pytest.raises(OktoNexusError) as exc:
        handoffs.handoff_claim(project_root=root, handoff_id=hid, agent_id="picky")
    assert exc.value.code == ErrorCode.NOT_ELIGIBLE_TO_CLAIM
    # Opaque: no tag data in the refusal.
    for secret in ("sector", "DEV", "OPS", "inbound"):
        assert secret not in exc.value.message

    # list_available mirrors the claim gate: the handoff is silently omitted.
    listed = handoffs.handoff_list_available(project_root=root, agent_id="picky")
    assert listed["handoffs"] == []

    # Dynamic: relaxing picky's inbound makes the SAME handoff claimable.
    _set_comm_scope(deps, "picky", INBOUND_DEV)
    listed = handoffs.handoff_list_available(project_root=root, agent_id="picky")
    assert [h["handoff_id"] for h in listed["handoffs"]] == [hid]
    claimed = handoffs.handoff_claim(
        project_root=root, handoff_id=hid, agent_id="picky"
    )
    assert claimed["claimed_by"] == "picky"


def test_handoff_outcome_notification_honours_creator_inbound_silently(deps, tmp_path):
    handoffs = build_handoff_service(deps)
    build_message_service(deps)  # wire the message repos the inbox lane reuses
    root = str(tmp_path)
    _ensure_workspace(deps, root)
    # The creator's inbound excludes the claimant -> the completion goes
    # through, but the creator's inbox notification is silently skipped.
    _register(deps, "quiet", comm_scope=INBOUND_OPS)
    _register(deps, "worker", role="worker", tags=TAGS_DEV)

    hid = handoffs.handoff_create(
        project_root=root,
        from_agent_id="quiet",
        target={"strategy": "role", "role": "worker"},
        visibility="public",
    )["handoff_id"]
    handoffs.handoff_claim(project_root=root, handoff_id=hid, agent_id="worker")
    out = handoffs.handoff_complete(
        project_root=root, handoff_id=hid, agent_id="worker", result="done"
    )
    assert out["status"] == "COMPLETED"
    assert not out.get("notified")
    assert _count(deps, "message_deliveries") == 0

    # Control: with the inbound admitting the claimant, the creator IS notified.
    _set_comm_scope(deps, "quiet", INBOUND_DEV)
    hid2 = handoffs.handoff_create(
        project_root=root,
        from_agent_id="quiet",
        target={"strategy": "role", "role": "worker"},
        visibility="public",
    )["handoff_id"]
    handoffs.handoff_claim(project_root=root, handoff_id=hid2, agent_id="worker")
    out = handoffs.handoff_complete(
        project_root=root, handoff_id=hid2, agent_id="worker", result="done"
    )
    assert out.get("notified") == ["quiet"]
    assert _count(deps, "message_deliveries") == 1


# --------------------------------------------------------------------------- #
# AC6 - discovery: visible = reachable (plus self); operator unfiltered
# --------------------------------------------------------------------------- #
def _seed_discovery_registry(deps):
    _register(
        deps,
        "a",
        capabilities=["plan"],
        tags=TAGS_DEV,
        comm_scope={"outbound": {"team": ["core"]}},
    )
    _register(deps, "b", capabilities=["ocr"], tags={"team": ["core"]})
    _register(
        deps,
        "c",
        capabilities=["scan"],
        tags={"team": ["core"]},
        comm_scope=INBOUND_OPS,
    )
    _register(deps, "d", capabilities=["ocr"], tags={"team": ["research"]})


def test_agent_list_scoped_by_reachability_plus_self(deps):
    service = build_identity_service(deps)
    _seed_discovery_registry(deps)

    # a's outbound admits b and c, but c's inbound rejects a; d is outside
    # a's outbound. Self is always visible.
    scoped = {a["agent_id"] for a in service.agent_list(caller_agent_id="a")}
    assert scoped == {"a", "b"}
    # Anonymous / operator surface stays unfiltered - and includes the
    # bootstrap-seeded "operator" identity (spec 2948b2a2 FR6).
    assert {a["agent_id"] for a in service.agent_list()} == {
        "a",
        "b",
        "c",
        "d",
        "operator",
    }


def test_agent_get_unreachable_reads_as_not_found_byte_identical(deps):
    service = build_identity_service(deps)
    _seed_discovery_registry(deps)

    def not_found(agent_id):
        with pytest.raises(OktoNexusError) as exc:
            service.agent_get(agent_id=agent_id, caller_agent_id="a")
        return exc.value

    unreachable = not_found("c")
    unknown = not_found("ghost")
    assert unreachable.code == unknown.code == ErrorCode.NOT_FOUND
    # Byte-identical (modulo the echoed id): unreachable and non-existent
    # are indistinguishable, so the policy never leaks.
    assert unreachable.message == unknown.message
    assert unreachable.details == {"agent_id": "c"}
    assert unknown.details == {"agent_id": "ghost"}

    # The operator surface (no caller) still reads the agent fine.
    assert service.agent_get(agent_id="c")["agent_id"] == "c"


def test_capability_list_scoped_by_reachability(deps):
    service = build_identity_service(deps)
    _seed_discovery_registry(deps)

    scoped = {
        c["capability"]: c["agents"]
        for c in service.capability_list(caller_agent_id="a")
    }
    # c's "scan" and d's share of "ocr" are invisible to a.
    assert scoped == {"plan": ["a"], "ocr": ["b"]}
    unfiltered = {c["capability"]: c["agents"] for c in service.capability_list()}
    assert unfiltered == {"plan": ["a"], "ocr": ["b", "d"], "scan": ["c"]}


# --------------------------------------------------------------------------- #
# AC7 - event stream: actors outside the viewer's reach are omitted
# --------------------------------------------------------------------------- #
def _emit(deps, ws: str, actor_agent_id) -> int:
    with deps.connection_factory.unit_of_work() as uow:
        return deps.repos.events.append(
            uow,
            workspace_id=ws,
            stream="workspace",
            type="message.created",
            payload={},
            actor_agent_id=actor_agent_id,
            visibility="public",
        )


def test_event_stream_hides_actors_outside_viewer_reach(deps, tmp_path):
    service = build_event_service(deps)
    root = str(tmp_path)
    ws = _ensure_workspace(deps, root)
    _register(deps, "v", tags=TAGS_DEV, comm_scope={"outbound": {"team": ["core"]}})
    _register(deps, "bob", tags={"team": ["core"]})
    _register(deps, "w", tags={"team": ["research"]})
    # guard's inbound rejects v (the SECOND leg of the double intersection).
    _register(
        deps,
        "guard",
        tags={"team": ["core"]},
        comm_scope={"inbound": {"team": ["core"]}},
    )

    id_bob = _emit(deps, ws, "bob")
    _emit(deps, ws, "w")
    _emit(deps, ws, "guard")
    id_self = _emit(deps, ws, "v")
    id_system = _emit(deps, ws, None)

    out = service.event_get(project_root=root, agent_id="v", stream="workspace")
    seen = [e["event_id"] for e in out["events"]]
    # bob is fully reachable; w fails v's outbound; guard's inbound fails v;
    # own events and actor-less (system) events ALWAYS show.
    assert seen == [id_bob, id_self, id_system]
    # The cursor still advances OVER the hidden rows (no poison pagination).
    assert out["next_cursor"] == id_system


def test_event_stream_unscoped_viewer_sees_everything(deps, tmp_path):
    service = build_event_service(deps)
    root = str(tmp_path)
    ws = _ensure_workspace(deps, root)
    _register(deps, "open")
    _register(deps, "w", tags={"team": ["research"]})

    id_w = _emit(deps, ws, "w")
    id_none = _emit(deps, ws, None)

    out = service.event_get(project_root=root, agent_id="open", stream="workspace")
    assert [e["event_id"] for e in out["events"]] == [id_w, id_none]
