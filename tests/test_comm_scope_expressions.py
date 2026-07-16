"""Rich selector expressions end-to-end (F3 / C2-C3).

F3 extends the selector GRAMMAR (domain) with Kubernetes-style match
expressions; every consumer inherits it through the same two predicates
(``selector_matches`` / ``reachable``) and the same catalog gate
(``ensure_registered``). This file proves the inheritance over the real
services + SQLite adapters (``bootstrap`` deps):

* write path (AC5): a ``tag`` target or ``comm_scope`` carrying expressions
  is existence-checked fail-closed against the central catalog - keys of
  EVERY operator, values of In/NotIn only (Exists/DoesNotExist carry none);
  nothing unregistered ever persists;
* TAG_IN_USE (AC5/TR5): deleting a key referenced by any expression (or a
  value referenced by In/NotIn) is refused; a value referenced by nothing
  but a presence check on its key still deletes;
* enforcement (AC6): rich ``comm_scope`` selectors bound direct sends,
  fan-outs, handoff claims, discovery and the event stream exactly like the
  flat form - including hierarchical segment matching and the NotIn/
  DoesNotExist absence semantics;
* default-allow regression (AC9): agents without any scope stay unrestricted.
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
from okto_nexus.application.tags import TagCatalogService
from okto_nexus.domain.base import new_id
from okto_nexus.domain.ids import resolve_realpath, resolve_workspace_id
from okto_nexus.errors import ErrorCode, OktoNexusError

#: Rich outbound scope: "I talk to anyone EXCEPT sector OPS" (NotIn also
#: admits untagged agents - the documented K8s absence semantics).
OUT_NOT_OPS = {"outbound": [{"key": "sector", "operator": "NotIn", "values": ["OPS"]}]}


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


def _set_tags(deps, agent_id: str, tags):
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.set_tags(uow, agent_id=agent_id, tags=tags)


def _catalog(deps, key: str, values=()):
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.tag_catalog.create_key(uow, key=key, description=None)
        for value in values:
            deps.repos.tag_catalog.create_value(
                uow, key=key, value=value, description=None
            )


def _tag_service(deps) -> TagCatalogService:
    return TagCatalogService(catalog=deps.repos.tag_catalog, agents=deps.repos.agents)


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


def _open_session(deps, agent_id: str, project_root: str) -> None:
    ws = _ensure_workspace(deps, project_root)
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.sessions.create(
            uow,
            session_id=new_id("ses"),
            agent_id=agent_id,
            workspace_id=ws,
            status="active",
        )


def _count(deps, table: str) -> int:
    conn = deps.connection_factory.get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# AC5 - write path: expressions are existence-checked fail-closed
# --------------------------------------------------------------------------- #
def test_tag_message_routes_by_rich_expression_truth_table(deps, tmp_path):
    service = build_message_service(deps)
    root = str(tmp_path)
    _catalog(deps, "sector", ["DEV", "OPS"])
    _register(deps, "sender")
    _register(deps, "dev", tags={"sector": ["DEV"]})
    _register(deps, "ops", tags={"sector": ["OPS"]})
    _register(deps, "untagged")
    for present in ("dev", "ops", "untagged"):
        _open_session(deps, present, root)

    out = service.create_message(
        project_root=root,
        from_agent_id="sender",
        subject="s",
        body="b",
        target={
            "strategy": "tag",
            "selector": [
                {"key": "sector", "operator": "Exists"},
                {"key": "sector", "operator": "NotIn", "values": ["OPS"]},
            ],
        },
    )
    # Exists blocks the untagged agent; NotIn blocks OPS; only dev matches.
    assert out["recipients"] == ["dev"]
    assert out["delivered_count"] == 1


def test_tag_message_with_unregistered_expression_key_fails_closed(deps, tmp_path):
    service = build_message_service(deps)
    _catalog(deps, "sector", ["DEV"])
    _register(deps, "sender")

    with pytest.raises(OktoNexusError) as ei:
        service.create_message(
            project_root=str(tmp_path),
            from_agent_id="sender",
            subject="s",
            body="b",
            target={
                "strategy": "tag",
                "selector": [{"key": "GHOST", "operator": "Exists"}],
            },
        )
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert ei.value.details["field"] == "target.selector"
    # Presence expressions carry no value: the key alone is reported.
    assert ei.value.details["unregistered"] == [
        {"key": "GHOST", "value": None, "missing": "key"}
    ]
    assert _count(deps, "messages") == 0
    assert _count(deps, "events") == 0


def test_tag_message_with_unregistered_notin_value_fails_closed(deps, tmp_path):
    service = build_message_service(deps)
    _catalog(deps, "sector", ["DEV"])
    _register(deps, "sender")

    with pytest.raises(OktoNexusError) as ei:
        service.create_message(
            project_root=str(tmp_path),
            from_agent_id="sender",
            subject="s",
            body="b",
            target={
                "strategy": "tag",
                "selector": [
                    {"key": "sector", "operator": "NotIn", "values": ["GHOST"]}
                ],
            },
        )
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert ei.value.details["unregistered"] == [
        {"key": "sector", "value": "GHOST", "missing": "value"}
    ]
    assert _count(deps, "messages") == 0


def test_exists_expression_validates_only_the_key(deps, tmp_path):
    # A key with NO registered values is still a legal Exists/DoesNotExist
    # subject (presence checks reference the key, never a value).
    handoffs = build_handoff_service(deps)
    root = str(tmp_path)
    _ensure_workspace(deps, root)
    _catalog(deps, "audited")  # key only - zero registered values
    _register(deps, "creator")

    out = handoffs.handoff_create(
        project_root=root,
        from_agent_id="creator",
        target={
            "strategy": "tag",
            "selector": [{"key": "audited", "operator": "Exists"}],
        },
        visibility="public",
    )
    assert out["handoff_id"]


# --------------------------------------------------------------------------- #
# AC5/TR5 - TAG_IN_USE recognises expression references
# --------------------------------------------------------------------------- #
def test_delete_key_referenced_by_exists_expression_is_tag_in_use(deps):
    _catalog(deps, "sector", ["DEV"])
    _register(
        deps,
        "sentinel",
        comm_scope={"outbound": [{"key": "sector", "operator": "Exists"}]},
    )
    service = _tag_service(deps)
    with deps.connection_factory.unit_of_work() as uow:
        with pytest.raises(OktoNexusError) as ei:
            service.delete_key(uow, key="sector")
    assert ei.value.code == ErrorCode.TAG_IN_USE.value
    assert ei.value.details["uses"] == [{"agent_id": "sentinel", "kind": "comm_scope"}]


def test_delete_value_referenced_by_notin_is_tag_in_use_presence_is_not(deps):
    _catalog(deps, "sector", ["DEV", "OPS"])
    _register(
        deps,
        "a",
        comm_scope={
            "inbound": [{"key": "sector", "operator": "NotIn", "values": ["OPS"]}]
        },
    )
    service = _tag_service(deps)
    # OPS is named by the NotIn values -> refused.
    with deps.connection_factory.unit_of_work() as uow:
        with pytest.raises(OktoNexusError) as ei:
            service.delete_value(uow, key="sector", value="OPS")
    assert ei.value.code == ErrorCode.TAG_IN_USE.value
    # DEV is referenced by nothing (NotIn names only OPS) -> deletable.
    with deps.connection_factory.unit_of_work() as uow:
        assert service.delete_value(uow, key="sector", value="DEV")["deleted"]
    # The KEY stays referenced by the expression -> still refused.
    with deps.connection_factory.unit_of_work() as uow:
        with pytest.raises(OktoNexusError) as ei:
            service.delete_key(uow, key="sector")
    assert ei.value.code == ErrorCode.TAG_IN_USE.value


# --------------------------------------------------------------------------- #
# AC6 - enforcement inherited by every surface (no consumer changed)
# --------------------------------------------------------------------------- #
def test_direct_blocked_by_rich_outbound_is_opaque_and_dynamic(deps, tmp_path):
    service = build_message_service(deps)
    _register(deps, "sender", comm_scope=OUT_NOT_OPS)
    _register(deps, "target", tags={"sector": ["OPS"]})

    with pytest.raises(OktoNexusError) as exc:
        service.create_message(
            project_root=str(tmp_path),
            from_agent_id="sender",
            subject="s",
            body="b",
            target={"strategy": "direct", "agent_id": "target"},
        )
    assert exc.value.code == ErrorCode.PERMISSION_DENIED
    # Same opaque denial as the flat form - no selector data leaks.
    assert exc.value.details == {"required_permission": "comm_scope.outbound"}
    assert _count(deps, "messages") == 0

    # Read at send time: re-tagging the recipient unblocks the next send.
    _set_tags(deps, "target", {"sector": ["DEV"]})
    out = service.create_message(
        project_root=str(tmp_path),
        from_agent_id="sender",
        subject="s",
        body="b",
        target={"strategy": "direct", "agent_id": "target"},
    )
    assert out["recipients"] == ["target"]


def test_fanout_narrowed_by_rich_inbound_silently(deps, tmp_path):
    service = build_message_service(deps)
    _register(deps, "sender")  # no team tag
    _register(deps, "bob", role="worker")
    _register(
        deps,
        "picky",
        role="worker",
        comm_scope={"inbound": [{"key": "team", "operator": "Exists"}]},
    )

    out = service.create_message(
        project_root=str(tmp_path),
        from_agent_id="sender",
        subject="s",
        body="b",
        target={"strategy": "role", "role": "worker"},
    )
    # picky requires senders to CARRY a team tag; the drop is silent.
    assert out["recipients"] == ["bob"]
    assert "filtered_by_audience" not in out
    assert "warning" not in out


def test_handoff_claim_bounded_by_rich_tag_target(deps, tmp_path):
    handoffs = build_handoff_service(deps)
    root = str(tmp_path)
    _ensure_workspace(deps, root)
    _catalog(deps, "sector", ["DEV", "OPS"])
    _register(deps, "creator")
    _register(deps, "dev", tags={"sector": ["DEV"]})
    _register(deps, "ops", tags={"sector": ["OPS"]})
    _register(deps, "untagged")

    hid = handoffs.handoff_create(
        project_root=root,
        from_agent_id="creator",
        target={
            "strategy": "tag",
            "selector": [{"key": "sector", "operator": "NotIn", "values": ["OPS"]}],
        },
        visibility="public",
    )["handoff_id"]

    # OPS fails the NotIn expression.
    with pytest.raises(OktoNexusError) as exc:
        handoffs.handoff_claim(project_root=root, handoff_id=hid, agent_id="ops")
    assert exc.value.code == ErrorCode.NOT_ELIGIBLE_TO_CLAIM

    # The K8s absence trap END TO END: NotIn admits the UNTAGGED agent too.
    listed = handoffs.handoff_list_available(project_root=root, agent_id="untagged")
    assert [h["handoff_id"] for h in listed["handoffs"]] == [hid]

    claimed = handoffs.handoff_claim(project_root=root, handoff_id=hid, agent_id="dev")
    assert claimed["claimed_by"] == "dev"


def test_hierarchical_flat_outbound_scopes_discovery_by_segment(deps):
    service = build_identity_service(deps)
    # Hierarchy applies to the FLAT form too (In sugar): ENG covers the
    # ENG/* subtree segment-wise, never a bare string prefix.
    _register(deps, "viewer", comm_scope={"outbound": {"area": ["ENG"]}})
    _register(deps, "backend", tags={"area": ["ENG/BACKEND"]})
    _register(deps, "engx", tags={"area": ["ENGX"]})
    _register(deps, "sales", tags={"area": ["SALES"]})

    scoped = {a["agent_id"] for a in service.agent_list(caller_agent_id="viewer")}
    assert scoped == {"viewer", "backend"}
    # Operator surface (no caller) stays unfiltered - and includes the
    # bootstrap-seeded "operator" identity (spec 2948b2a2 FR6).
    assert {a["agent_id"] for a in service.agent_list()} == {
        "viewer",
        "backend",
        "engx",
        "sales",
        "operator",
    }


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


def test_event_stream_filtered_by_rich_reachability(deps, tmp_path):
    service = build_event_service(deps)
    root = str(tmp_path)
    ws = _ensure_workspace(deps, root)
    # Viewer only reaches agents WITHOUT a sector tag (DoesNotExist).
    _register(
        deps,
        "viewer",
        comm_scope={"outbound": [{"key": "sector", "operator": "DoesNotExist"}]},
    )
    _register(deps, "plain")
    _register(deps, "ops", tags={"sector": ["OPS"]})

    id_plain = _emit(deps, ws, "plain")
    _emit(deps, ws, "ops")
    id_self = _emit(deps, ws, "viewer")
    id_system = _emit(deps, ws, None)

    out = service.event_get(project_root=root, agent_id="viewer", stream="workspace")
    assert [e["event_id"] for e in out["events"]] == [id_plain, id_self, id_system]
    assert out["next_cursor"] == id_system


# --------------------------------------------------------------------------- #
# AC8 - the MCP surface documents the grammar (revision 15 + the NotIn trap)
# --------------------------------------------------------------------------- #
def test_surface_revision_15_and_grammar_resource_documents_expressions():
    from okto_nexus.adapters.inbound.mcp import resources
    from okto_nexus.adapters.inbound.mcp.server import SURFACE_REVISION
    from okto_nexus.adapters.inbound.mcp.tools.handoff import _P_TARGET_HANDOFF
    from okto_nexus.adapters.inbound.mcp.tools.messages import _P_TARGET_MSG

    # The expression grammar shipped at revision 15; later features only
    # advance the counter (the changelog entry for 15 stays).
    assert SURFACE_REVISION >= 15

    grammar = resources._RESOURCES["okto-nexus://reference/target-grammar"]["body"]
    for operator in ("In", "NotIn", "Exists", "DoesNotExist"):
        assert operator in grammar
    # The absence trap and the segment hierarchy are documented ON the surface.
    assert "ABSENCE TRAP" in grammar
    assert "ENG/BACKEND" in grammar

    # Both inline cheat-sheets teach the rich form and warn about absence.
    for description in (_P_TARGET_MSG, _P_TARGET_HANDOFF):
        assert "In|NotIn|Exists|DoesNotExist" in description
        assert "MISSING the key" in description


# --------------------------------------------------------------------------- #
# AC9 - default-allow regression: unscoped agents stay unrestricted
# --------------------------------------------------------------------------- #
def test_unscoped_agents_behave_as_before_f3(deps, tmp_path):
    service = build_message_service(deps)
    _register(deps, "a")
    _register(deps, "b")

    out = service.create_message(
        project_root=str(tmp_path),
        from_agent_id="a",
        subject="s",
        body="b",
        target={"strategy": "direct", "agent_id": "b"},
    )
    assert out["recipients"] == ["b"]
    assert out["delivered_count"] == 1
