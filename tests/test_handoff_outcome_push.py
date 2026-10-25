"""Handoff lifecycle notices reach a creator that runs in a runtime session."""
import json
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap, register_tools
from okto_nexus.adapters.inbound.mcp.tools.messages import build_service
from okto_nexus.adapters.outbound.sqlite.handoff_notifications import SqliteHandoffNotificationRepository
from okto_nexus.application.execution_release_notifications import notify_contained_claimant
from okto_nexus.application.runtime_handoff_notifications import queue_outcome, validate
from okto_nexus.errors import OktoNexusError
from test_handoff_dependencies import FakeServer, _ok


@pytest.fixture
def env(tmp_path):
    deps = bootstrap({"OKTO_NEXUS_HOME": str(tmp_path / "home")}, [])
    deps.config.feature_harness_integrations = True
    server = FakeServer()
    register_tools(server, deps)
    tools = server.tools
    project = tmp_path / "project"
    project.mkdir()
    root = str(project)
    workspace = _ok(tools["workspace_resolve"](project_root=root))["workspace_id"]
    for agent, role in (("alpha", "builder"), ("beta", "executor"), ("gamma", "executor"), ("operator", "operator")):
        with deps.connection_factory.unit_of_work(write=False) as uow:
            known = deps.repos.agents.get(uow, agent) is not None
        if not known:
            _ok(tools["agent_register"](agent_id=agent, role=role))
    return deps, tools, root, workspace


def runtime_for(deps, workspace, *agents):
    """Give each agent an approved conversation endpoint and turn the runtime on."""
    conn = deps.connection_factory.get_connection()
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("UPDATE runtime_policy_defaults SET runtime_enabled=1 WHERE singleton=1")
        for agent in agents:
            conn.execute("INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,adapter_id,protocol,created_at,updated_at,"
                "enabled,activation_state,consumption,response_policy) VALUES(?,?,?,'claude','stream','t','t',1,'approved','exclusive','conversation')",
                ("ep-" + agent, agent, workspace))
    finally:
        conn.close()


def claim(tools, root, claimant="beta", creator="alpha"):
    hid = _ok(tools["handoff_create"](project_root=root, from_agent_id=creator,
        target={"strategy": "direct", "agent_id": claimant}, visibility="public"))["handoff_id"]
    _ok(tools["handoff_claim"](project_root=root, handoff_id=hid, agent_id=claimant))
    return hid


def pushed(deps, handoff_id):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return [dict(r) for r in uow.connection.execute(
            "SELECT n.recipient_agent_id,n.event_type,n.runtime_route,p.status FROM runtime_handoff_notifications n "
            "JOIN message_deliveries d ON d.message_id=n.message_id AND d.recipient_agent_id=n.recipient_agent_id "
            "JOIN runtime_pending_deliveries p ON p.delivery_id=d.delivery_id WHERE n.handoff_id=? AND n.event_type LIKE '%:%' ORDER BY n.event_type",
            (handoff_id,))]


def test_complete_and_reject_push_one_notice_to_the_creator(env):
    deps, tools, root, workspace = env
    runtime_for(deps, workspace, "alpha")
    done, refused = claim(tools, root), claim(tools, root)
    _ok(tools["handoff_complete"](project_root=root, handoff_id=done, agent_id="beta", result="x" * 5000))
    _ok(tools["handoff_reject"](project_root=root, handoff_id=refused, agent_id="beta", reason="no"))
    for hid, event in ((done, "handoff.completed"), (refused, "handoff.rejected")):
        rows = pushed(deps, hid)
        assert [(r["recipient_agent_id"], r["runtime_route"], r["status"]) for r in rows] == [("alpha", "conversation", "waiting")]
        assert rows[0]["event_type"].startswith(event + ":")
    with deps.connection_factory.unit_of_work(write=False) as uow:
        body = json.loads(uow.connection.execute("SELECT m.body FROM runtime_handoff_notifications n JOIN messages m USING(message_id) "
            "WHERE n.handoff_id=?", (done,)).fetchone()[0])
    assert len(body["result"]) == 4000


def test_creator_without_a_runtime_gets_the_inbox_message_only(env):
    deps, tools, root, workspace = env
    hid = claim(tools, root)
    _ok(tools["handoff_complete"](project_root=root, handoff_id=hid, agent_id="beta", result="ok"))
    assert pushed(deps, hid) == []
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM message_deliveries d JOIN messages m USING(message_id) "
            "WHERE d.recipient_agent_id='alpha' AND m.body LIKE '%handoff.completed%'").fetchone()[0] == 1


def test_cancel_after_expiry_pushes_a_notice_to_the_previous_claimant(env):
    deps, tools, root, workspace = env
    runtime_for(deps, workspace, "beta")
    hid = claim(tools, root)
    conn = deps.connection_factory.get_connection()
    try:
        conn.execute("UPDATE handoffs SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE handoff_id=?", (hid,))
    finally:
        conn.close()
    _ok(tools["handoff_cancel"](project_root=root, handoff_id=hid, agent_id="alpha", reason="stale"))
    rows = pushed(deps, hid)
    # The cancel runs the expiry first, so beta also gets the lease notice (#92).
    assert [(r["recipient_agent_id"], r["event_type"].split(":")[0]) for r in rows] == [
        ("beta", "handoff.cancelled"), ("beta", "handoff.lease_expired")]


def make_notice(deps, uow, workspace, hid, kind, sender, recipient, body=None, tag="1"):
    service = build_service(deps)
    now = deps.clock.now_iso()
    body = json.dumps(dict(kind=kind, handoff_id=hid, **(body or {})))
    mid = f"msg_t_{kind}_{tag}"
    message = service._messages.create(uow, message_id=mid, workspace_id=workspace, from_agent_id=sender, channel_id=None,
        from_session_id=None, target=json.dumps(dict(strategy="direct", agent_id=recipient)), subject="s", body=body,
        artifacts=[], parent_message_id=None, trace_id=None, created_at=now)
    delivery = service._deliveries.create(uow, delivery_id="del_" + mid, message_id=mid, recipient_agent_id=recipient,
        status="unread", created_at=now)
    return message, delivery


def call_queue(deps, uow, message, delivery, hid, kind):
    return queue_outcome(uow, message=message, delivery=delivery, handoff_id=hid, kind=kind, agents=deps.repos.agents,
        handoffs=deps.repos.handoffs, now=deps.clock.now_iso(), notifications=SqliteHandoffNotificationRepository())


def test_two_epochs_do_not_clash_and_one_epoch_queues_once(env):
    deps, tools, root, workspace = env
    runtime_for(deps, workspace, "alpha", "beta")
    hid = claim(tools, root)
    kind = "handoff.lease_expired"
    with deps.connection_factory.unit_of_work() as uow:
        m1, d1 = make_notice(deps, uow, workspace, hid, kind, "beta", "alpha", tag="1")
        assert call_queue(deps, uow, m1, d1, hid, kind) is True
        m2, d2 = make_notice(deps, uow, workspace, hid, kind, "beta", "alpha", tag="2")
        assert call_queue(deps, uow, m2, d2, hid, kind) is False  # same epoch: inbox only
        uow.connection.execute("UPDATE handoffs SET claim_epoch=claim_epoch+1 WHERE handoff_id=?", (hid,))
        m3, d3 = make_notice(deps, uow, workspace, hid, kind, "beta", "alpha", tag="3")
        assert call_queue(deps, uow, m3, d3, hid, kind) is True
    assert sorted(r["event_type"] for r in pushed(deps, hid)) == [kind + ":1", kind + ":2"]


def test_validate_accepts_creator_and_previous_claimant_and_refuses_a_third_agent(env):
    deps, tools, root, workspace = env
    runtime_for(deps, workspace, "alpha", "beta", "gamma")
    hid = claim(tools, root)
    _ok(tools["handoff_complete"](project_root=root, handoff_id=hid, agent_id="beta", result="ok"))
    kind = "handoff.lease_expired"
    with deps.connection_factory.unit_of_work() as uow:
        creator = make_notice(deps, uow, workspace, hid, kind, "beta", "alpha", tag="c")
        assert call_queue(deps, uow, *creator, hid, kind)
        prev = make_notice(deps, uow, workspace, hid, kind, "alpha", "beta", {"previous_claimed_by": "beta"}, tag="p")
        assert call_queue(deps, uow, *prev, hid, kind)
        third = make_notice(deps, uow, workspace, hid, kind, "alpha", "gamma", tag="g")
        assert call_queue(deps, uow, *third, hid, kind) is False
        now = deps.clock.now_iso()
        validate(uow, message=creator[0], recipient_id="alpha", agents=deps.repos.agents, now=now)
        validate(uow, message=prev[0], recipient_id="beta", agents=deps.repos.agents, now=now)
        # A forged row for a third agent fails validation.
        uow.connection.execute("INSERT INTO runtime_handoff_notifications(message_id,handoff_id,recipient_agent_id,event_type,actor_guard) "
            "VALUES(?,?,?,?,?)", (third[0].message_id, hid, "gamma", kind + ":9", "g"))
        with pytest.raises(OktoNexusError):
            validate(uow, message=third[0], recipient_id="gamma", agents=deps.repos.agents, now=now)


def test_containment_pushes_creator_notices_and_keeps_the_operator_notice_inbox_only(env):
    deps, tools, root, workspace = env
    runtime_for(deps, workspace, "alpha")
    hid = claim(tools, root)
    assert notify_contained_claimant(deps, build_service(deps), server_id="server", executor_id="executor",
        session_id="session-1", agent_id="beta", reason="EVENT_OPERATION_MISMATCH") == 2
    rows = pushed(deps, hid)
    assert [(r["recipient_agent_id"], r["event_type"].split(":")[0]) for r in rows] == [("alpha", "handoff.claimant_contained")]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_pending_deliveries").fetchone()[0] == 1
