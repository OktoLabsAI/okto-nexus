"""Canonical result audiences preserve fanout authority and atomic budgets."""
import json
import time
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from nexus_connector_core import RuntimeEvent
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, connect_local, admit, wait_receipt
from test_canonical_delivery import connected_local
from test_agent_recovery_isolation import create_agent
from test_vertical_inventory import _Native
from test_canonical_grant_regressions import mcp_helpers


@pytest.fixture
def runtime(connected_local, monkeypatch):
    setup, first, _ = connected_local
    deps, app, client, headers, *_ = setup
    client.headers["host"] = "127.0.0.1:8000"
    setups, bindings = {"subject": setup}, {"subject": first}
    for agent in ("caller", "observer"):
        current = create_agent(setup, agent)
        current, binding, _ = connect_local(current, agent_id=agent)
        setups[agent], bindings[agent] = current, binding
    peers = {}
    class Factory:
        opens = 0
        async def open(self, prepared, session_id, context, *, stream_epoch):
            self.opens += 1
            peer = _Native()
            peers[session_id] = peer
            return peer
    factory = Factory()
    app.state.embedded_dispatch_owner.native_factory = factory
    sessions = {}
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET role='observer' WHERE agent_id='observer'")
        uow.connection.execute("UPDATE agent_endpoints SET consumption='exclusive',response_policy='explicit'")
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='conversation' WHERE endpoint_id=?", (first["endpoint_id"],))
    deps.runtime_dispatcher.recovery_seconds = .2
    deps.runtime_dispatcher.wake()
    value = SimpleNamespace(setup=setup, setups=setups, deps=deps, client=client, headers=headers,
        bindings=bindings, sessions=sessions, peers=peers, factory=factory)
    yield value
    assert 1 <= factory.opens <= 3


def configure(runtime, target, *, relay=False):
    config = dict(relay_results=relay)
    if target is not None:
        config["notify_target"] = target
    with runtime.deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET public_config=? WHERE endpoint_id=?",
            (json.dumps(config), runtime.bindings["subject"]["endpoint_id"]))
        if relay:
            uow.connection.execute("UPDATE agent_endpoints SET response_policy='conversation'")


def send(runtime, body="Fanout output"):
    from test_pr34_remediation import tool
    key = runtime.setups["caller"][3]["subject"]["Authorization"].removeprefix("Bearer ")
    reply = tool(runtime.client, key, "message_create", dict(project_root=str(runtime.setup[-1]),
        from_agent_id="caller", subject="Fanout source", body="Generate the requested output",
        target=dict(strategy="direct", agent_id="subject")))
    assert reply["ok"], reply
    operation = reply["data"]["runtime_operations"][0]
    with runtime.deps.connection_factory.unit_of_work(write=False) as uow:
        turn = dict(uow.connection.execute("SELECT p.* FROM execution_operations p JOIN execution_domain_deliveries m "
            "USING(server_id,executor_id,operation_id) WHERE m.domain_operation_id=? AND p.action='turn.submit'", (operation,)).fetchone())
    wait_receipt(runtime.setup, turn)
    with runtime.deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute("SELECT * FROM execution_local_streams WHERE session_id=?", (turn["session_id"],)).fetchone())
    peer = runtime.peers[turn["session_id"]]
    for offset in range(0, len(body), 30000):
        runtime.client.portal.call(peer.queue.put, RuntimeEvent(stream["server_id"], stream["executor_id"],
            stream["session_id"], stream["stream_epoch"], 0, "text_delta", "fixture.fanout-output",
            dict(output_text=body[offset:offset + 30000]), operation_id=turn["operation_id"]))
    runtime.client.portal.call(peer.queue.put, RuntimeEvent(stream["server_id"], stream["executor_id"],
        stream["session_id"], stream["stream_epoch"], 0, "turn_state", "fixture.fanout",
        dict(delivery_phase="terminal", delivery_outcome="success", output_text=""), operation_id=turn["operation_id"]))
    wait_receipt(runtime.setup, turn, stages=("SUCCEEDED",))
    return operation


def result(runtime, operation, state):
    until = time.monotonic() + 15
    while True:
        with runtime.deps.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT * FROM runtime_results WHERE operation_id=?", (operation,)).fetchone()
        if row and row["publication_state"] == state:
            return dict(row)
        assert time.monotonic() < until, dict(row) if row else None
        time.sleep(.02)


def recipients(runtime, row):
    with runtime.deps.connection_factory.unit_of_work(write=False) as uow:
        return [r[0] for r in uow.connection.execute("SELECT recipient_agent_id FROM message_deliveries WHERE message_id=? ORDER BY recipient_agent_id", (row["publication_message_id"],))]


def observer_sends(runtime, count):
    until = time.monotonic() + 10
    while True:
        with runtime.deps.connection_factory.unit_of_work(write=False) as uow:
            observer_sessions = [r[0] for r in uow.connection.execute("SELECT DISTINCT session_id FROM execution_operations WHERE subject_agent_id IN ('caller','observer')")]
        actual = sum(len(runtime.peers[sid].sent) for sid in observer_sessions if sid in runtime.peers)
        if actual == count:
            return
        assert time.monotonic() < until, actual
        time.sleep(.02)


@pytest.mark.parametrize("strategy", ["direct", "role", "broadcast"])
def test_result_audience_uses_canonical_routing_without_executing_observers(runtime, strategy):
    target = dict(strategy=strategy)
    target.update(dict(agent_id="observer") if strategy == "direct" else dict(role="observer") if strategy == "role" else {})
    configure(runtime, target)
    row = result(runtime, send(runtime), "PUBLISHED")
    assert recipients(runtime, row) == (["caller", "observer"] if strategy == "broadcast" else ["observer"])
    observer_sends(runtime, 0)
    with runtime.deps.connection_factory.unit_of_work(write=False) as uow:
        sid = uow.connection.execute("SELECT session_id FROM execution_operations WHERE operation_id=?",
            (row["canonical_operation_id"],)).fetchone()[0]
    # A new configuration cannot reuse a session prepared with the old one.
    wait_receipt(runtime.setup, admit(runtime.setup, runtime.bindings["subject"], "notify-reconfigure-close",
        "runtime.close", session_id=sid), stages=("SUCCEEDED",))
    configure(runtime, None)
    private = result(runtime, send(runtime, "Private after removal"), "PUBLISHED")
    assert recipients(runtime, private) == ["caller"]
    observer_sends(runtime, 0)


@pytest.mark.parametrize("actor", ["subject", "caller"])
def test_broadcast_cannot_borrow_sender_or_origin_permissions(runtime, actor):
    configure(runtime, dict(strategy="broadcast"))
    with runtime.deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET permissions=? WHERE agent_id=?",
            (json.dumps(dict(messages=dict(send_broadcast=False))), actor))
    row = result(runtime, send(runtime), "BLOCKED")
    assert row["output_text"] and not row["publication_message_id"]
    observer_sends(runtime, 0)


@pytest.mark.parametrize("budget,state,sends", [(3, "ENQUEUED", 2), (2, "PARTIAL", 1), (1, "BLOCKED", 0)])
def test_broadcast_charges_one_message_and_bounds_each_child(runtime, budget, state, sends):
    runtime.deps.config.max_executions_per_root = budget
    configure(runtime, dict(strategy="broadcast"), relay=True)
    row = result(runtime, send(runtime), "PUBLISHED")
    assert row["relay_state"] == state
    observer_sends(runtime, sends)
    with runtime.deps.connection_factory.unit_of_work() as uow:
        # An informational result with no executable child does not consume
        # the generated-execution-message budget.
        assert uow.connection.execute("SELECT generated_messages,admitted_executions FROM runtime_causal_roots").fetchone()[:] == (int(sends > 0), budget)
        decisions = uow.connection.execute("SELECT state FROM runtime_relay_decisions WHERE result_id=?", (row["result_id"],)).fetchall()
        assert len(decisions) == 2 and sum(r[0] == "ENQUEUED" for r in decisions) == sends
        assert uow.connection.execute("SELECT COUNT(*) FROM messages WHERE subject='Runtime result'").fetchone()[0] == 1
        assert uow.connection.execute("SELECT COUNT(*) FROM events WHERE type='runtime.relay_blocked'").fetchone()[0] == 2 - sends
        uow.connection.execute("UPDATE message_deliveries SET status='read',read_at='2000-01-01T00:00:00.000Z'")
        runtime.deps.repos.deliveries.prune_read_before(uow, cutoff="2099-01-01T00:00:00.000Z", limit=100)
        assert uow.connection.execute("SELECT COUNT(*) FROM runtime_relay_decisions").fetchone()[0] == 2
        assert not uow.connection.execute("PRAGMA foreign_key_check").fetchall()


def test_fanout_publication_failure_rolls_back_children_and_recovers_automatically(runtime, monkeypatch):
    from okto_nexus.application.runtime_results import RuntimeResultService
    configure(runtime, dict(strategy="broadcast"), relay=True)
    original, failed = RuntimeResultService.finish, threading.Event()
    def cut(uow, **kwargs):
        original(uow, **kwargs)
        failed.set()
        raise OSError("Publication transaction cut")
    with monkeypatch.context() as patch:
        patch.setattr(RuntimeResultService, "finish", staticmethod(cut))
        operation = send(runtime)
        assert failed.wait(5)
        result(runtime, operation, "PENDING_AUTHORIZATION")
        with runtime.deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT COUNT(*) FROM delivery_outbox").fetchone()[0] == 1
            assert uow.connection.execute("SELECT COUNT(*) FROM runtime_relay_decisions").fetchone()[0] == 0
            assert uow.connection.execute("SELECT generated_messages,admitted_executions FROM runtime_causal_roots").fetchone()[:] == (0, 1)
        observer_sends(runtime, 0)
    result(runtime, operation, "PUBLISHED")
    observer_sends(runtime, 2)
    with runtime.deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM runtime_relay_decisions").fetchone()[0] == 2


def test_origin_permission_revocation_after_publication_blocks_all_native_children(runtime, monkeypatch):
    from okto_nexus.application.runtime_results import RuntimeResultService
    configure(runtime, dict(strategy="broadcast"), relay=True)
    original = RuntimeResultService.finish
    def revoke(uow, **kwargs):
        original(uow, **kwargs)
        uow.connection.execute("UPDATE agents SET permissions=? WHERE agent_id='caller'", ('{"messages":{"send_broadcast":false}}',))
    monkeypatch.setattr(RuntimeResultService, "finish", staticmethod(revoke))
    result(runtime, send(runtime), "PUBLISHED")
    until = time.monotonic() + 15
    while True:
        with runtime.deps.connection_factory.unit_of_work(write=False) as uow:
            states = [r[0] for r in uow.connection.execute("SELECT status FROM delivery_outbox WHERE source_result_id IS NOT NULL")]
        if states == ["REJECTED", "REJECTED"]:
            break
        assert time.monotonic() < until, states
        time.sleep(.02)
    observer_sends(runtime, 0)


def test_large_result_artifact_readers_match_explicit_audience(runtime):
    configure(runtime, dict(strategy="role", role="observer"))
    row = result(runtime, send(runtime, "x" * 90000), "PUBLISHED")
    assert row["output_artifact_id"]
    with runtime.deps.connection_factory.unit_of_work(write=False) as uow:
        artifact = runtime.deps.repos.artifacts.get(uow,
            workspace_id=runtime.bindings["subject"]["workspace_id"], artifact_id=row["output_artifact_id"])
        assert artifact.reader_agent_ids == ["observer", "subject"]
        message = uow.connection.execute("SELECT target FROM messages WHERE message_id=?", (row["publication_message_id"],)).fetchone()
        assert json.loads(message[0]) == dict(strategy="role", role="observer")


@pytest.mark.parametrize("strategy", ["broadcast", "BROADCAST"])
def test_origin_governance_applies_to_broader_result_audience(runtime, strategy):
    from test_governance import _attach, _rule
    configure(runtime, dict(strategy=strategy))
    _attach(runtime.deps, "caller", governance=[_rule("broadcast", "deny")])
    row = result(runtime, send(runtime), "BLOCKED")
    assert not row["publication_message_id"] and row["output_text"]
    observer_sends(runtime, 0)


def test_origin_broadcast_approval_is_not_bypassed(runtime, monkeypatch):
    from test_governance import _attach, _rule
    from okto_nexus.application.runtime_results import RuntimeResultService
    configure(runtime, dict(strategy="broadcast"))
    runtime.deps.config.feature_hitl = True
    prepare, attached = RuntimeResultService.prepare, False
    def before_publication(self, *args, **kwargs):
        nonlocal attached
        if not attached:
            _attach(runtime.deps, "caller", governance=[_rule("message_create", "require_approval")])
            attached = True
        return prepare(self, *args, **kwargs)
    monkeypatch.setattr(RuntimeResultService, "prepare", before_publication)
    operation = send(runtime)
    row = result(runtime, operation, "PENDING_APPROVAL")
    assert not row["publication_message_id"]
    response = runtime.client.post(f"/api/v1/approvals/{row['publication_approval_id']}/decision",
        headers=runtime.headers["operator"], json=dict(decision="approve"))
    assert response.status_code == 200, response.text
    assert recipients(runtime, result(runtime, operation, "PUBLISHED")) == ["caller", "observer"]
    observer_sends(runtime, 0)
