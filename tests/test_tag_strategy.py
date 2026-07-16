"""The 'tag' routing strategy + dynamic handoff claim audience (F1 / C5).

Three layers:

* grammar (``domain.targets``): ``tag`` requires a NON-EMPTY, well-formed
  ``selector``; ``iter_target_selectors`` walks nested rules so write paths
  can existence-check the whole tree;
* eligibility (``domain.routing``): a ``tag`` target matches agents whose
  tags satisfy the selector (AND across keys, OR within values; tagless
  agents never match);
* end to end over the real services (``bootstrap`` deps): a tag message
  fans out to the PRESENT agents matching the selector (never the whole
  registry), an unregistered selector fails closed at create, a zero-match
  tag send is an explicit NO_MATCHING_AGENTS error (never a silent nobody
  send, never a broadcast fallback), and handoff claims are bounded
  DYNAMICALLY by the creator's ``comm_scope.outbound`` (AC8/AC9).
"""

from __future__ import annotations

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.inbound.mcp.tools.handoff import (
    build_service as build_handoff_service,
)
from okto_nexus.adapters.inbound.mcp.tools.messages import (
    build_service as build_message_service,
)
from okto_nexus.domain.base import new_id
from okto_nexus.domain.ids import resolve_realpath, resolve_workspace_id
from okto_nexus.domain.routing import RoutingAgent, is_agent_eligible
from okto_nexus.domain.targets import iter_target_selectors, validate_target
from okto_nexus.errors import ErrorCode, OktoNexusError


@pytest.fixture
def deps(tmp_path):
    return bootstrap({}, ["--home", str(tmp_path / "home")])


def _register(deps, agent_id: str, *, role=None, tags=None, comm_scope=None):
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id=agent_id, role=role)
        if tags is not None:
            deps.repos.agents.set_tags(uow, agent_id=agent_id, tags=tags)
        if comm_scope is not None:
            deps.repos.agents.set_comm_scope(
                uow, agent_id=agent_id, comm_scope=comm_scope
            )


def _set_tags(deps, agent_id: str, tags):
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.set_tags(uow, agent_id=agent_id, tags=tags)


def _catalog(deps, key: str, values):
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.tag_catalog.create_key(uow, key=key, description=None)
        for value in values:
            deps.repos.tag_catalog.create_value(
                uow, key=key, value=value, description=None
            )


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
# Grammar (domain.targets)
# --------------------------------------------------------------------------- #
def test_tag_target_validates_and_normalises_selector():
    out = validate_target({"strategy": "tag", "selector": {"SECTOR": "DEV"}})
    assert out == {"strategy": "tag", "selector": {"SECTOR": ["DEV"]}}


@pytest.mark.parametrize(
    "target",
    [
        {"strategy": "tag"},  # selector missing
        {"strategy": "tag", "selector": None},
        {"strategy": "tag", "selector": {}},  # empty = covert broadcast
        {"strategy": "tag", "selector": {"SECTOR": []}},  # dead entry
        {"strategy": "tag", "selector": {"": ["DEV"]}},  # blank key
        {"strategy": "tag", "selector": "SECTOR=DEV"},  # not a mapping
    ],
)
def test_tag_target_rejects_missing_or_malformed_selector(target):
    with pytest.raises(OktoNexusError) as ei:
        validate_target(target)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


def test_tag_rule_nests_inside_mixed():
    out = validate_target(
        {
            "strategy": "mixed",
            "rules": [
                {"strategy": "role", "role": "worker"},
                {"strategy": "tag", "selector": {"SECTOR": ["DEV"]}},
            ],
        }
    )
    assert out["rules"][1] == {"strategy": "tag", "selector": {"SECTOR": ["DEV"]}}


def test_iter_target_selectors_walks_nested_rules():
    resolved = validate_target(
        {
            "strategy": "mixed",
            "rules": [
                {"strategy": "tag", "selector": {"A": ["1"]}},
                {"strategy": "role", "role": "x"},
                {
                    "strategy": "mixed",
                    "rules": [{"strategy": "tag", "selector": {"B": ["2"]}}],
                },
            ],
        }
    )
    assert list(iter_target_selectors(resolved)) == [{"A": ["1"]}, {"B": ["2"]}]
    fallback = validate_target(
        {
            "strategy": "direct_with_fallback",
            "agent_id": "a",
            "fallback_after_seconds": 0,
            "fallback": {"strategy": "tag", "selector": {"C": ["3"]}},
        }
    )
    assert list(iter_target_selectors(fallback)) == [{"C": ["3"]}]
    assert list(iter_target_selectors(None)) == []


# --------------------------------------------------------------------------- #
# Eligibility (domain.routing)
# --------------------------------------------------------------------------- #
def test_tag_eligibility_matches_agent_tags():
    target = {"strategy": "tag", "selector": {"SECTOR": ["DEV"]}}
    dev = RoutingAgent(agent_id="a", workspace_id="w", tags={"SECTOR": ["DEV", "QA"]})
    ops = RoutingAgent(agent_id="b", workspace_id="w", tags={"SECTOR": ["OPS"]})
    tagless = RoutingAgent(agent_id="c", workspace_id="w")
    assert is_agent_eligible(dev, target) is True
    assert is_agent_eligible(ops, target) is False
    assert is_agent_eligible(tagless, target) is False


# --------------------------------------------------------------------------- #
# message_create with strategy 'tag' (ts_b032a489)
# --------------------------------------------------------------------------- #
def test_tag_message_reaches_only_present_matching_agents(deps, tmp_path):
    service = build_message_service(deps)
    root = str(tmp_path)
    _catalog(deps, "SECTOR", ["DEV", "OPS"])
    _register(deps, "sender")
    _register(deps, "b", tags={"SECTOR": ["DEV"]})
    _register(deps, "c", tags={"SECTOR": ["OPS"]})
    _register(deps, "d", tags={"SECTOR": ["DEV"]})
    _open_session(deps, "b", root)
    _open_session(deps, "c", root)
    # d matches the selector but holds NO session: tag targets the LIVE audience.

    out = service.create_message(
        project_root=root,
        from_agent_id="sender",
        subject="s",
        body="b",
        target={"strategy": "tag", "selector": {"SECTOR": ["DEV"]}},
    )
    assert out["recipients"] == ["b"]
    assert out["delivered_count"] == 1


def test_tag_message_with_unregistered_selector_fails_closed(deps, tmp_path):
    service = build_message_service(deps)
    _catalog(deps, "SECTOR", ["DEV"])
    _register(deps, "sender")

    with pytest.raises(OktoNexusError) as ei:
        service.create_message(
            project_root=str(tmp_path),
            from_agent_id="sender",
            subject="s",
            body="b",
            target={"strategy": "tag", "selector": {"SECTOR": ["GHOST"]}},
        )
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert ei.value.details["unregistered"] == [
        {"key": "SECTOR", "value": "GHOST", "missing": "value"}
    ]
    # Fail-closed: nothing routed, nothing persisted.
    assert _count(deps, "messages") == 0
    assert _count(deps, "events") == 0


def test_tag_message_matching_no_live_agent_is_explicit_error(deps, tmp_path):
    service = build_message_service(deps)
    root = str(tmp_path)
    _catalog(deps, "SECTOR", ["DEV"])
    _register(deps, "sender")
    _register(deps, "d", tags={"SECTOR": ["DEV"]})  # matches, but not present

    with pytest.raises(OktoNexusError) as ei:
        service.create_message(
            project_root=root,
            from_agent_id="sender",
            subject="s",
            body="b",
            target={"strategy": "tag", "selector": {"SECTOR": ["DEV"]}},
        )
    assert ei.value.code == ErrorCode.NOT_FOUND.value
    assert ei.value.details["reason"] == "NO_MATCHING_AGENTS"
    # Never a silent nobody-send: the message did not persist.
    assert _count(deps, "messages") == 0


# --------------------------------------------------------------------------- #
# handoff: dynamic claim audience (ts_594778ca) + tag targets (AC9)
# --------------------------------------------------------------------------- #
def test_handoff_claim_bounded_by_creator_outbound_scope(deps, tmp_path):
    handoffs = build_handoff_service(deps)
    root = str(tmp_path)
    _ensure_workspace(deps, root)
    _catalog(deps, "SECTOR", ["DEV", "OPS"])
    _register(deps, "creator", comm_scope={"outbound": {"SECTOR": ["DEV"]}})
    _register(deps, "b", tags={"SECTOR": ["OPS"]})
    _register(deps, "c", tags={"SECTOR": ["DEV"]})

    created = handoffs.handoff_create(
        project_root=root,
        from_agent_id="creator",
        target={"strategy": "broadcast"},
        visibility="public",
    )
    hid = created["handoff_id"]

    # b is outside the creator's outbound audience -> opaque refusal.
    with pytest.raises(OktoNexusError) as ei:
        handoffs.handoff_claim(project_root=root, handoff_id=hid, agent_id="b")
    assert ei.value.code == ErrorCode.NOT_ELIGIBLE_TO_CLAIM.value
    # The refusal never leaks the policy (no selector, no tags).
    for secret in ("SECTOR", "DEV", "OPS", "comm_scope"):
        assert secret not in ei.value.message

    # The handoff stayed OPEN: c (inside the audience) claims it.
    claimed = handoffs.handoff_claim(project_root=root, handoff_id=hid, agent_id="c")
    assert claimed["claimed_by"] == "c"


def test_handoff_claim_audience_is_evaluated_at_claim_time(deps, tmp_path):
    handoffs = build_handoff_service(deps)
    root = str(tmp_path)
    _ensure_workspace(deps, root)
    _catalog(deps, "SECTOR", ["DEV"])
    _register(deps, "creator", comm_scope={"outbound": {"SECTOR": ["DEV"]}})
    _register(deps, "c", tags={"SECTOR": ["DEV"]})

    hid = handoffs.handoff_create(
        project_root=root,
        from_agent_id="creator",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]

    # c loses the tag BETWEEN create and claim: what counts is the state at
    # claim time (dynamic), so the claim is refused.
    _set_tags(deps, "c", None)
    with pytest.raises(OktoNexusError) as ei:
        handoffs.handoff_claim(project_root=root, handoff_id=hid, agent_id="c")
    assert ei.value.code == ErrorCode.NOT_ELIGIBLE_TO_CLAIM.value


def test_handoff_tag_target_gates_claim_by_selector(deps, tmp_path):
    handoffs = build_handoff_service(deps)
    root = str(tmp_path)
    _ensure_workspace(deps, root)
    _catalog(deps, "SECTOR", ["DEV", "OPS"])
    _register(deps, "creator")
    _register(deps, "b", tags={"SECTOR": ["DEV"]})
    _register(deps, "c", tags={"SECTOR": ["OPS"]})

    created = handoffs.handoff_create(
        project_root=root,
        from_agent_id="creator",
        target={"strategy": "tag", "selector": {"SECTOR": ["DEV"]}},
        visibility="public",
    )
    assert created["eligible_count"] == 1
    hid = created["handoff_id"]

    with pytest.raises(OktoNexusError) as ei:
        handoffs.handoff_claim(project_root=root, handoff_id=hid, agent_id="c")
    assert ei.value.code == ErrorCode.NOT_ELIGIBLE_TO_CLAIM.value
    claimed = handoffs.handoff_claim(project_root=root, handoff_id=hid, agent_id="b")
    assert claimed["claimed_by"] == "b"


def test_handoff_tag_target_with_unregistered_selector_fails_closed(deps, tmp_path):
    handoffs = build_handoff_service(deps)
    _ensure_workspace(deps, str(tmp_path))
    _catalog(deps, "SECTOR", ["DEV"])
    _register(deps, "creator")

    with pytest.raises(OktoNexusError) as ei:
        handoffs.handoff_create(
            project_root=str(tmp_path),
            from_agent_id="creator",
            target={"strategy": "tag", "selector": {"TEAM": ["BE"]}},
            visibility="public",
        )
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert ei.value.details["unregistered"] == [
        {"key": "TEAM", "value": "BE", "missing": "key"}
    ]
    assert _count(deps, "handoffs") == 0
    assert _count(deps, "events") == 0


def test_fallback_claim_is_still_bounded_by_creator_audience(deps, tmp_path):
    # direct_with_fallback with delay 0: the broadcast fallback is live
    # immediately, but it never widens past the creator's outbound scope.
    handoffs = build_handoff_service(deps)
    root = str(tmp_path)
    _ensure_workspace(deps, root)
    _catalog(deps, "SECTOR", ["DEV", "OPS"])
    _register(deps, "creator", comm_scope={"outbound": {"SECTOR": ["DEV"]}})
    _register(deps, "named", tags={"SECTOR": ["DEV"]})
    _register(deps, "b", tags={"SECTOR": ["OPS"]})
    _register(deps, "c", tags={"SECTOR": ["DEV"]})

    hid = handoffs.handoff_create(
        project_root=root,
        from_agent_id="creator",
        target={
            "strategy": "direct_with_fallback",
            "agent_id": "named",
            "fallback_after_seconds": 0,
        },
        visibility="public",
    )["handoff_id"]

    # b is fallback-eligible (broadcast) but outside the creator's audience.
    with pytest.raises(OktoNexusError) as ei:
        handoffs.handoff_claim(project_root=root, handoff_id=hid, agent_id="b")
    assert ei.value.code == ErrorCode.NOT_ELIGIBLE_TO_CLAIM.value
    # c is fallback-eligible AND inside the audience.
    claimed = handoffs.handoff_claim(project_root=root, handoff_id=hid, agent_id="c")
    assert claimed["claimed_by"] == "c"


def test_handoff_claim_unrestricted_creator_unchanged(deps, tmp_path):
    handoffs = build_handoff_service(deps)
    root = str(tmp_path)
    _ensure_workspace(deps, root)
    _register(deps, "creator")
    _register(deps, "worker")

    hid = handoffs.handoff_create(
        project_root=root,
        from_agent_id="creator",
        target={"strategy": "broadcast"},
        visibility="public",
    )["handoff_id"]
    claimed = handoffs.handoff_claim(
        project_root=root, handoff_id=hid, agent_id="worker"
    )
    assert claimed["claimed_by"] == "worker"
