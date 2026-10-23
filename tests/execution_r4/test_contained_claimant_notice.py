"""A contained session tells the creators of its claimed handoffs and the operator."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from nexus_connector_core import CoreError
from okto_nexus.adapters.inbound.mcp.server import bootstrap, register_tools
from okto_nexus.adapters.inbound.mcp.tools.messages import build_service
from okto_nexus.application.execution_release_notifications import notify_contained_claimant
from okto_nexus.bootstrap import embedded_agent_recovery
from okto_nexus.bootstrap.embedded_agent_recovery import EmbeddedAgentRecovery, _containment_reason
from test_handoff_dependencies import FakeServer, _ok


@pytest.fixture
def env(tmp_path):
    deps = bootstrap({"OKTO_NEXUS_HOME": str(tmp_path / "home")}, [])
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


def claimed(tools, root, claimant, creator="alpha"):
    created = _ok(tools["handoff_create"](project_root=root, from_agent_id=creator,
        target={"strategy": "direct", "agent_id": claimant}, visibility="public"))
    handoff_id = created["handoff_id"]
    _ok(tools["handoff_claim"](project_root=root, handoff_id=handoff_id, agent_id=claimant))
    return handoff_id


def notices(deps, recipient):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return [dict(row) for row in uow.connection.execute(
            "SELECT m.subject,m.body,m.from_agent_id FROM message_deliveries d JOIN messages m USING(message_id) "
            "WHERE d.recipient_agent_id=? AND m.message_id LIKE 'msg_claimant_contained_%' ORDER BY m.message_id",
            (recipient,))]


def contain(deps, **options):
    values = dict(server_id="server", executor_id="executor", session_id="session-1",
                  agent_id="beta", reason="EVENT_OPERATION_MISMATCH")
    values.update(options)
    return notify_contained_claimant(deps, build_service(deps), **values)


def test_each_creator_gets_one_notice_per_claimed_handoff_and_the_operator_one(env):
    deps, tools, root, _ = env
    first, second = claimed(tools, root, "beta"), claimed(tools, root, "beta")
    other = claimed(tools, root, "gamma")
    assert contain(deps) == 3
    creator = notices(deps, "alpha")
    assert len(creator) == 2
    assert {first, second} == {next(h for h in (first, second) if h in item["subject"]) for item in creator}
    for item in creator:
        assert item["from_agent_id"] == "beta"
        assert "Claimant session contained (reason: EVENT_OPERATION_MISMATCH)" in item["body"]
        assert "may be lost" in item["body"] and "runs to" in item["body"]
    operator = notices(deps, "operator")
    assert len(operator) == 1
    assert "EVENT_OPERATION_MISMATCH" in operator[0]["body"]
    assert first in operator[0]["body"] and second in operator[0]["body"] and other not in operator[0]["body"]
    assert notices(deps, "gamma") == [] and notices(deps, "beta") == []


def test_no_notice_without_a_claimed_handoff(env):
    deps, tools, root, _ = env
    claimed(tools, root, "gamma")
    assert contain(deps) == 0
    assert notices(deps, "alpha") == [] and notices(deps, "operator") == []


def test_creator_who_is_the_operator_gets_the_operator_notice_only_once(env):
    deps, tools, root, _ = env
    claimed(tools, root, "beta", creator="operator")
    assert contain(deps) == 1
    assert len(notices(deps, "operator")) == 1


def test_reason_is_recorded_once_and_a_repeat_sends_nothing(env):
    deps, tools, root, _ = env
    claimed(tools, root, "beta")
    # Only the identity columns matter here. A separate connection skips the
    # foreign keys of the full session graph.
    conn = deps.connection_factory.get_connection()
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("INSERT INTO execution_sessions(server_id,executor_id,session_id,binding_id,workspace_id,"
            "workspace_binding_id,open_operation_id,owner_generation,lifecycle_state,lease_state) "
            "VALUES('server','executor','session-1','binding','workspace','wb','op',1,'FAILED','CLOSED')")
    finally:
        conn.close()
    assert contain(deps) == 2
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stored = uow.connection.execute("SELECT containment_reason,contained_at FROM execution_sessions "
            "WHERE session_id='session-1'").fetchone()
    assert stored[0] == "EVENT_OPERATION_MISMATCH" and stored[1]
    assert contain(deps, reason="OTHER_REASON") == 0
    assert len(notices(deps, "alpha")) == 1 and len(notices(deps, "operator")) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT containment_reason FROM execution_sessions "
            "WHERE session_id='session-1'").fetchone()[0] == "EVENT_OPERATION_MISMATCH"


@pytest.mark.parametrize(("session", "reason"), [
    ({"recovery_error": CoreError("EVENT_OPERATION_MISMATCH", "stage")}, "EVENT_OPERATION_MISMATCH"),
    ({"recovery_error": RuntimeError("secret text")}, "RuntimeError"),
    ({"recovery_reason": "LEASE_EXPIRED", "recovery_error": RuntimeError("x")}, "LEASE_EXPIRED"),
    ({"recovery_reason": "has spaces and secret"}, "SESSION_CONTAINED"),
    ({}, "SESSION_CONTAINED"),
])
def test_reason_is_a_technical_identifier(session, reason):
    assert _containment_reason(session) == reason


def test_released_session_notifies_before_it_leaves_the_owner(monkeypatch):
    order = []

    async def nothing(*args, **kwargs):
        return None

    class Reconciliation:
        def __init__(self, owner):
            pass

        async def release_stopped_session(self, session_id):
            order.append("release")

    monkeypatch.setattr(embedded_agent_recovery, "EmbeddedReconciliation", Reconciliation)
    report = SimpleNamespace(session_outcomes={})
    runtime = SimpleNamespace(shutdown=lambda policy: nothing_report(report),
                              shutdown_resources=lambda: {})

    async def nothing_report(value):
        return value

    session = {"scope": {"agent_id": "beta"}, "executor": SimpleNamespace(_runtime=lambda: nothing_report(runtime)),
               "recovery_error": CoreError("EVENT_OPERATION_MISMATCH", "stage")}
    owner = SimpleNamespace(
        verify=lambda: None, sessions={"session-1": session}, worker_sessions={},
        channel=SimpleNamespace(executor_id="executor"),
        host=SimpleNamespace(close_native_actions=lambda **kwargs: nothing_report(True)),
        _recover_publications=nothing, events=SimpleNamespace(recover=nothing),
        tools=SimpleNamespace(release_session=nothing))
    owner._recovery_event = lambda code, *args, **kwargs: order.append(
        (code, "session-1" in owner.sessions))
    owner._notify_contained_claimant = lambda *args: order.append(("notify", args, "session-1" in owner.sessions))
    recovery = EmbeddedAgentRecovery(owner)
    # Blocked sessions publish their cause first. Mark it as recorded.
    session["recovery_error_recorded"] = True
    asyncio.run(recovery._recover_session("session-1", session))
    assert order == [
        "release",
        ("notify", ("session-1", "beta", "EVENT_OPERATION_MISMATCH"), True),
        ("RECOVERY_SESSION_RELEASED", False),
    ]


def test_stream_fault_names_its_reason():
    async def scenario():
        async def publications(**kwargs):
            return False

        async def recover(**kwargs):
            return False

        owner = SimpleNamespace(workers=set(), sessions={"s": {}}, _activity=asyncio.Event(),
            active_operations=set(), _recover_publications=publications, events=SimpleNamespace(recover=recover))
        agents = EmbeddedAgentRecovery(owner)
        agents._check_stream_health = lambda agent_id, active: ["s"]
        agents.recover_session = lambda session_id: None
        await agents._publish("a")
        assert _containment_reason(owner.sessions["s"]) == "EVENT_STREAM_UNAVAILABLE"

    asyncio.run(scenario())
