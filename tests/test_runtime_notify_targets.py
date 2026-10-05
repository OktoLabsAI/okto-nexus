"""Explicit result audience uses canonical routing and approved endpoint state."""
import json
import threading
import time

import pytest

from test_pr34_remediation import runtime as runtime_fixture, send_message, tool, wait_sent
from test_runtime_commands import codex_session
from test_runtime_result_publication import result

runtime = runtime_fixture


def setup_notify(runtime, target, *, relay=False):
    deps, client, root, _, operator, _ = runtime
    codex_session(runtime)
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id="observer", role="observer")
    for agent in ("caller", "observer"):
        response = client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator}, json={
            "endpoint_id": "notify-" + agent, "agent_id": agent, "adapter_id": "pi", "project_root": root,
            "profile_id": "profile-pi", "enabled": True, "response_policy": "conversation" if relay else "explicit"})
        assert response.status_code == 200, response.text
        response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
            "agent_id": agent, "kind": "pi", "endpoint_id": "notify-" + agent, "project_root": root})
        assert response.status_code == 200, response.text
    response = client.patch("/api/v1/harness/endpoints/endpoint-codex", headers={"x-api-key": operator}, json={
        "expected_revision": 1, "public_config": {"notify_target": target, "relay_results": relay}})
    assert response.status_code == 200, response.text


def recipients(deps, message_id):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return [r[0] for r in uow.connection.execute(
            "SELECT recipient_agent_id FROM message_deliveries WHERE message_id=? ORDER BY recipient_agent_id", (message_id,))]


def test_explicit_broadcast_delivers_only_to_present_audience_and_removal_restores_private_reply(runtime):
    setup_notify(runtime, {"strategy": "broadcast"})
    deps, client, _, peers, operator, _ = runtime
    source = send_message(runtime, body="explicit shared update")
    published = result(runtime, source["runtime_operations"][0], "PUBLISHED")
    assert recipients(deps, published["publication_message_id"]) == ["caller", "observer"]
    assert all(not peer.sent for peer in peers), "informational publication executed observers"
    response = client.patch("/api/v1/harness/endpoints/endpoint-codex", headers={"x-api-key": operator}, json={
        "expected_revision": 2, "public_config": {"notify_target": None}})
    assert response.status_code == 200, response.text
    private = send_message(runtime, body="private after configuration removal")
    published = result(runtime, private["runtime_operations"][0], "PUBLISHED")
    assert recipients(deps, published["publication_message_id"]) == ["caller"]


@pytest.mark.parametrize("target", [{"strategy": "direct", "agent_id": "observer"}, {"strategy": "role", "role": "observer"}])
def test_explicit_target_reuses_canonical_direct_and_role_routing(runtime, target):
    setup_notify(runtime, target)
    source = send_message(runtime)
    published = result(runtime, source["runtime_operations"][0], "PUBLISHED")
    assert recipients(runtime[0], published["publication_message_id"]) == ["observer"]


def test_broadcast_does_not_override_sender_permission(runtime):
    setup_notify(runtime, {"strategy": "broadcast"})
    deps, client, _, _, operator, _ = runtime
    response = client.patch("/api/v1/agents/worker", headers={"x-api-key": operator}, json={
        "permissions": {"messages": {"send_broadcast": False}}})
    assert response.status_code == 200, response.text
    source = send_message(runtime)
    blocked = result(runtime, source["runtime_operations"][0], "BLOCKED")
    assert not blocked["publication_message_id"] and blocked["output_text"]


def test_notification_configuration_and_open_override_require_authority(runtime):
    _, client, root, peers, operator, caller = runtime
    response = client.patch("/api/v1/harness/endpoints/endpoint-pi", headers={"x-api-key": caller}, json={
        "expected_revision": 1, "public_config": {"notify_target": {"strategy": "broadcast"}}})
    assert response.status_code == 403, response.text
    denied = tool(client, operator, "harness_open", {"agent_id": "worker", "kind": "pi", "project_root": root,
        "notify_target": {"strategy": "broadcast"}})
    assert not denied["ok"] and denied["error"]["code"] == "PERMISSION_DENIED", denied
    assert not peers


def test_result_artifact_readers_match_explicit_audience(runtime):
    setup_notify(runtime, {"strategy": "role", "role": "observer"})
    deps = runtime[0]
    source = send_message(runtime, body="x" * 62000)
    published = result(runtime, source["runtime_operations"][0], "PUBLISHED")
    assert published["output_artifact_id"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        artifact = deps.repos.artifacts.get(uow, workspace_id=uow.connection.execute(
            "SELECT workspace_id FROM delivery_outbox WHERE operation_id=?", (source["runtime_operations"][0],)).fetchone()[0],
            artifact_id=published["output_artifact_id"])
        assert artifact.reader_agent_ids == ["observer", "worker"]
        message = uow.connection.execute("SELECT target FROM messages WHERE message_id=?", (published["publication_message_id"],)).fetchone()
        assert json.loads(message[0]) == {"strategy": "role", "role": "observer"}


@pytest.mark.parametrize("budget,state,sends", [(3, "ENQUEUED", 2), (2, "PARTIAL", 1)])
def test_explicit_broadcast_relay_charges_one_message_and_bounded_executions(runtime, budget, state, sends):
    deps = runtime[0]
    deps.config.max_executions_per_root = budget
    setup_notify(runtime, {"strategy": "broadcast"}, relay=True)
    source = send_message(runtime)
    published = result(runtime, source["runtime_operations"][0], "PUBLISHED")
    assert published["relay_state"] == state
    wait_sent(runtime[3], count=sends)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        root = uow.connection.execute("SELECT * FROM runtime_causal_roots").fetchone()
        assert root["generated_messages"] == 1
        assert root["admitted_executions"] == budget
        decisions = uow.connection.execute("SELECT state FROM runtime_relay_decisions WHERE result_id=?",
            (published["result_id"],)).fetchall()
        assert len(decisions) == 2 and sum(r[0] == "ENQUEUED" for r in decisions) == sends
        assert uow.connection.execute("SELECT count(*) FROM events WHERE type='runtime.relay_blocked'").fetchone()[0] == 2 - sends
        assert uow.connection.execute("SELECT count(*) FROM messages WHERE subject='Runtime result'").fetchone()[0] == 1


def test_relay_decision_retention_does_not_delete_fences_or_fail(runtime):
    deps = runtime[0]
    deps.config.max_executions_per_root = 1
    setup_notify(runtime, {"strategy": "broadcast"}, relay=True)
    source = send_message(runtime)
    published = result(runtime, source["runtime_operations"][0], "PUBLISHED")
    assert published["relay_state"] == "BLOCKED"
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE message_deliveries SET status='read',read_at='2000-01-01T00:00:00.000Z'")
        assert deps.repos.deliveries.prune_read_before(uow, cutoff="2099-01-01T00:00:00.000Z", limit=100) >= 0
        assert uow.connection.execute("SELECT count(*) FROM runtime_relay_decisions").fetchone()[0] == 2
        assert uow.connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_fanout_publication_commit_cut_rolls_back_all_children_and_budgets(runtime, monkeypatch):
    from okto_nexus.application.runtime_results import RuntimeResultService
    deps = runtime[0]
    setup_notify(runtime, {"strategy": "broadcast"}, relay=True)
    original, failed = RuntimeResultService.finish, threading.Event()

    def cut(uow, **kwargs):
        original(uow, **kwargs)
        failed.set()
        raise OSError("fixture publication commit cut")

    with monkeypatch.context() as patch:
        patch.setattr(RuntimeResultService, "finish", staticmethod(cut))
        source = send_message(runtime)
        assert failed.wait(5)
        result(runtime, source["runtime_operations"][0], "PENDING_AUTHORIZATION")
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
            assert uow.connection.execute("SELECT count(*) FROM runtime_relay_decisions").fetchone()[0] == 0
            root = uow.connection.execute("SELECT generated_messages,admitted_executions FROM runtime_causal_roots").fetchone()
            assert tuple(root) == (0, 1)
        assert all(not peer.sent for peer in runtime[3])
    deps.runtime_dispatcher.wake()
    result(runtime, source["runtime_operations"][0], "PUBLISHED")
    wait_sent(runtime[3], count=2)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_relay_decisions").fetchone()[0] == 2


def test_stale_configuration_cannot_overwrite_new_notification_audience(runtime):
    _, client, _, _, operator, _ = runtime
    path = "/api/v1/harness/endpoints/endpoint-codex"
    response = client.patch(path, headers={"x-api-key": operator}, json={"expected_revision": 1,
        "public_config": {"notify_target": {"strategy": "direct", "agent_id": "caller"}}})
    assert response.status_code == 200, response.text
    stale = client.patch(path, headers={"x-api-key": operator}, json={"expected_revision": 1,
        "public_config": {"notify_target": {"strategy": "broadcast"}}})
    assert stale.status_code == 409, stale.text


def test_broadcast_cannot_borrow_represented_agent_privileges(runtime):
    setup_notify(runtime, {"strategy": "broadcast"})
    _, client, _, _, operator, _ = runtime
    response = client.patch("/api/v1/agents/caller", headers={"x-api-key": operator}, json={
        "permissions": {"messages": {"send_broadcast": False}}})
    assert response.status_code == 200, response.text
    source = send_message(runtime)
    blocked = result(runtime, source["runtime_operations"][0], "BLOCKED")
    assert not blocked["publication_message_id"]


@pytest.mark.parametrize("strategy", ["broadcast", "BROADCAST"])
def test_originating_actor_governance_applies_to_broader_notifications(runtime, strategy):
    from test_governance import _attach, _rule
    setup_notify(runtime, {"strategy": strategy})
    deps = runtime[0]
    _attach(deps, "caller", governance=[_rule("broadcast", "deny")])
    source = send_message(runtime)
    blocked = result(runtime, source["runtime_operations"][0], "BLOCKED")
    assert not blocked["publication_message_id"]


def test_originating_actor_broadcast_approval_is_not_bypassed(runtime, monkeypatch):
    from test_governance import _attach, _rule
    from okto_nexus.application.runtime_results import RuntimeResultService
    setup_notify(runtime, {"strategy": "broadcast"})
    deps, client, _, _, operator, _ = runtime
    deps.config.feature_hitl = True
    prepare, attached = RuntimeResultService.prepare, False

    def before_publication(self, *args, **kwargs):
        nonlocal attached
        # Install a new actor policy after the initiating turn was admitted,
        # before result publication starts its transaction.
        if not attached:
            _attach(deps, "caller", governance=[_rule("message_create", "require_approval")])
            attached = True
        return prepare(self, *args, **kwargs)

    monkeypatch.setattr(RuntimeResultService, "prepare", before_publication)
    source = send_message(runtime)
    pending = result(runtime, source["runtime_operations"][0], "PENDING_APPROVAL")
    assert not pending["publication_message_id"]
    response = client.post(f'/api/v1/approvals/{pending["publication_approval_id"]}/decision',
        headers={"x-api-key": operator}, json={"decision": "approve"})
    assert response.status_code == 200, response.text
    published = result(runtime, source["runtime_operations"][0], "PUBLISHED")
    assert recipients(deps, published["publication_message_id"]) == ["caller", "observer"]


def test_private_reply_does_not_require_initiator_to_send_to_itself(runtime):
    from test_runtime_relay import configure, wait_blocked
    configure(runtime, depth=1)
    _, client, _, _, operator, _ = runtime
    headers = {"x-api-key": operator}
    assert client.post("/api/v1/tags", headers=headers, json={"key": "team"}).status_code == 200
    assert client.post("/api/v1/tags/team/values", headers=headers, json={"value": "worker"}).status_code == 200
    assert client.patch("/api/v1/agents/worker", headers=headers, json={"tags": {"team": ["worker"]}}).status_code == 200
    assert client.patch("/api/v1/agents/caller", headers=headers, json={
        "comm_scope": {"outbound": {"team": ["worker"]}}}).status_code == 200
    send_message(runtime)
    rows = wait_blocked(runtime)
    assert len(rows) == 2


def test_origin_permission_revocation_after_publication_blocks_native_fanout(runtime, monkeypatch):
    from okto_nexus.application.runtime_results import RuntimeResultService
    setup_notify(runtime, {"strategy": "broadcast"}, relay=True)
    deps = runtime[0]
    finish = RuntimeResultService.finish

    def revoke(uow, **kwargs):
        finish(uow, **kwargs)
        uow.connection.execute("UPDATE agents SET permissions=? WHERE agent_id='caller'",
            (json.dumps({"messages": {"send_broadcast": False}}),))

    monkeypatch.setattr(RuntimeResultService, "finish", staticmethod(revoke))
    source = send_message(runtime)
    result(runtime, source["runtime_operations"][0], "PUBLISHED")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            states = [r[0] for r in uow.connection.execute("SELECT status FROM delivery_outbox WHERE source_result_id IS NOT NULL")]
        if states == ["REJECTED", "REJECTED"]:
            assert all(not peer.sent for peer in runtime[3])
            return
        time.sleep(.01)
    raise AssertionError(states)
