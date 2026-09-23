"""Explicit relay admission through real HTTP/MCP composition and native frames."""
import time
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_pr34_remediation import runtime as runtime_fixture, send_message
from test_runtime_commands import codex_session

runtime = runtime_fixture


def configure(runtime, *, depth=2, outcome="completed", kind="codex"):
    deps, client, root, _, operator, _ = runtime
    deps.config.max_relay_depth = depth
    adapter = "claude_code.stream" if kind == "claude_code" else kind
    # Create a separate explicitly approved endpoint; existing defaults remain
    # non-relaying. No policy inserted behind the production service.
    for agent in ("worker", "caller"):
        response = client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator}, json={
            "endpoint_id": "relay-" + agent, "agent_id": agent, "adapter_id": adapter, "project_root": root,
            "profile_id": "profile-" + adapter, "enabled": True, "priority": 10,
            "response_policy": "conversation", "public_config": {"relay_results": True}})
        assert response.status_code == 200, response.text
    # Register the actual JSON-RPC fixture adapter through existing composition.
    codex_session(runtime)
    if kind == "claude_code":
        from okto_nexus.adapters.outbound.harness.claude_code_stream import ClaudeCodeStreamConnector
        from test_harness_claude_code_connector import _FAKE_CLAUDE_SCRIPT
        deps.harness_connector_factories[kind] = lambda **kwargs: ClaudeCodeStreamConnector(
            binary=sys._base_executable, argv=["-u", "-c", _FAKE_CLAUDE_SCRIPT], cwd=root, env=kwargs["backend"]["env"])
    elif kind == "pi":
        from okto_nexus.adapters.outbound.harness.pi import PiRpcConnector
        from test_harness_pi_connector import _FAKE_SERVER_SOURCE
        from pathlib import Path
        import itertools
        sequence = itertools.count()
        deps.harness_connector_factories[kind] = lambda **kwargs: PiRpcConnector(
            command=[sys._base_executable, "-u", "-c", _FAKE_SERVER_SOURCE, str(Path(root) / f"pi-{next(sequence)}.jsonl")],
            cwd=root, env=kwargs["backend"]["env"])
    if outcome != "completed":
        from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
        from test_harness_codex_connector import _FAKE_SERVER_SOURCE
        source = _FAKE_SERVER_SOURCE.replace('"status": "completed"', '"status": "' + outcome + '"')
        deps.harness_connector_factories["codex"] = lambda **kwargs: CodexAppServerConnector(
            command=[sys._base_executable, "-u", "-c", source], cwd=root, env=kwargs["backend"]["env"])
    for agent in ("worker", "caller"):
        response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
            "agent_id": agent, "kind": kind, "endpoint_id": "relay-" + agent, "project_root": root})
        assert response.status_code == 200, response.text


def wait_blocked(runtime, count=1):
    deps = runtime[0]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            rows = [dict(r) for r in uow.connection.execute("SELECT * FROM runtime_results ORDER BY captured_at,result_id")]
        if sum(r["relay_state"] == "BLOCKED" for r in rows) >= count:
            return rows
        time.sleep(.01)
    raise AssertionError(rows)


@pytest.mark.parametrize("kind", ["codex", "pi", "claude_code"])
def test_bidirectional_relay_stops_at_persistent_depth_and_keeps_result(runtime, kind):
    configure(runtime, kind=kind)
    send_message(runtime, body="bounded conversational exchange")
    rows = wait_blocked(runtime)
    assert len(rows) == 3, rows
    assert [r["delivery_outcome"] for r in rows] == ["success"] * 3
    assert [r["relay_state"] for r in rows] == ["ENQUEUED", "ENQUEUED", "BLOCKED"]
    assert all(r["publication_state"] == "PUBLISHED" and r["publication_message_id"] for r in rows)
    deps = runtime[0]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        operations = [dict(r) for r in uow.connection.execute("SELECT * FROM delivery_outbox ORDER BY created_at,operation_id")]
        assert len(operations) == 3
        assert [r["recipient_agent_id"] for r in operations] == ["worker", "caller", "worker"]
        assert len({r["root_operation_id"] for r in operations}) == 1
        assert {r["actor_agent_id"] for r in operations} == {"caller"}
        root = uow.connection.execute("SELECT * FROM runtime_causal_roots").fetchone()
        assert root["generated_messages"] == 2
        assert root["admitted_executions"] == 3
        assert uow.connection.execute("SELECT count(*) FROM runtime_handoff_bindings").fetchone()[0] == 0
        assert [r[0] for r in uow.connection.execute("SELECT delivery_outcome FROM harness_events WHERE delivery_phase='terminal' ORDER BY sequence")] == ["success"] * 3
        receipts = uow.connection.execute("SELECT message_id FROM messages WHERE subject LIKE 'runtime processing receipt:%'").fetchall()
        assert len(receipts) == 3
        for receipt in receipts:
            assert not uow.connection.execute("SELECT 1 FROM delivery_outbox WHERE message_id=?", (receipt[0],)).fetchone()
        assert uow.connection.execute("SELECT count(*) FROM events WHERE type='runtime.relay_blocked'").fetchone()[0] == 1


@pytest.mark.parametrize("outcome,normalized", [("failed", "failed"), ("interrupted", "interrupted"), ("unknown", None)])
def test_failed_interrupted_and_unknown_results_do_not_relay(runtime, outcome, normalized):
    configure(runtime, outcome=outcome)
    send_message(runtime)
    rows = wait_blocked(runtime)
    assert len(rows) == 1
    assert rows[0]["publication_state"] == "PUBLISHED"
    assert rows[0]["delivery_outcome"] == normalized
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1


def test_self_loop_is_recorded_without_starting_another_turn(runtime):
    configure(runtime)
    send_message(runtime, target={"strategy": "direct", "agent_id": "caller"})
    rows = wait_blocked(runtime)
    assert len(rows) == 1 and rows[0]["relay_reason"] == "PERMISSION_DENIED"


def test_execution_budget_rolls_back_child_reservation_but_preserves_output(runtime):
    runtime[0].config.max_executions_per_root = 2
    configure(runtime, depth=4)
    send_message(runtime)
    rows = wait_blocked(runtime)
    assert len(rows) == 2
    assert rows[-1]["publication_state"] == "PUBLISHED"
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        root = uow.connection.execute("SELECT * FROM runtime_causal_roots").fetchone()
        assert root["generated_messages"] == 1
        assert root["admitted_executions"] == 2
        assert uow.connection.execute("SELECT purpose FROM runtime_message_causality WHERE message_id=?",
            (rows[-1]["publication_message_id"],)).fetchone()[0] == "observation"


def test_repeated_publication_does_not_charge_or_dispatch_again(runtime):
    from okto_nexus.adapters.inbound.mcp.tools.messages import build_service
    configure(runtime, depth=1)
    send_message(runtime)
    rows = wait_blocked(runtime)
    messages = build_service(runtime[0])
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        bound = messages._runtime_results.row(uow, rows[0]["result_id"])
    with ThreadPoolExecutor(max_workers=8) as pool:
        replies = list(pool.map(lambda _: messages.create_message(
            **messages._runtime_results.arguments(bound), _runtime_result_id=bound["result_id"]), range(8)))
    assert {again["message_id"] for again in replies} == {bound["publication_message_id"]}
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 2
        assert uow.connection.execute("SELECT generated_messages FROM runtime_causal_roots").fetchone()[0] == 1


def test_source_relay_revocation_before_dispatch_prevents_next_turn(runtime, monkeypatch):
    from okto_nexus.application.runtime_results import RuntimeResultService
    configure(runtime)
    finish = RuntimeResultService.finish

    def revoke(uow, **kwargs):
        finish(uow, **kwargs)
        # Deterministic cut after publication admission and before dispatcher.
        uow.connection.execute("UPDATE agent_endpoints SET enabled=0,revision=revision+1 WHERE endpoint_id='relay-worker'")

    monkeypatch.setattr(RuntimeResultService, "finish", staticmethod(revoke))
    send_message(runtime)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with runtime[0].connection_factory.unit_of_work(write=False) as uow:
            child = uow.connection.execute("SELECT * FROM delivery_outbox WHERE source_result_id IS NOT NULL").fetchone()
            if child and child["status"] == "REJECTED":
                assert uow.connection.execute("SELECT count(*) FROM runtime_results").fetchone()[0] == 1
                return
        time.sleep(.01)
    raise AssertionError(dict(child) if child else None)


def test_interleaved_roots_share_sessions_without_sharing_budgets(runtime):
    configure(runtime, depth=1)
    entries = [send_message(runtime, body="independent root one"),
               send_message(runtime, body="independent root two")]
    rows = wait_blocked(runtime, count=2)
    assert len(rows) == 4
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        roots = uow.connection.execute("SELECT generated_messages,admitted_executions FROM runtime_causal_roots").fetchall()
        assert [tuple(r) for r in roots] == [(1, 2), (1, 2)]
        assert uow.connection.execute("SELECT count(DISTINCT runtime_session_id) FROM delivery_outbox").fetchone()[0] == 2
        for entry in entries:
            parent = uow.connection.execute("SELECT * FROM delivery_outbox WHERE operation_id=?",
                (entry["runtime_operations"][0],)).fetchone()
            child = uow.connection.execute("""SELECT child.*, result.publication_message_id
                FROM delivery_outbox child JOIN runtime_results result ON result.result_id=child.source_result_id
                WHERE result.operation_id=?""", (parent["operation_id"],)).fetchone()
            assert child["root_operation_id"] == parent["root_operation_id"]
            assert child["message_id"] == child["publication_message_id"]
            message = uow.connection.execute("SELECT parent_message_id FROM messages WHERE message_id=?",
                (child["message_id"],)).fetchone()
            assert message[0] == entry["message_id"]


def test_same_agent_on_distinct_endpoints_keeps_operation_parent(runtime):
    deps, client, root, _, operator, _ = runtime
    configure(runtime, depth=1)
    first = send_message(runtime, body="first worker endpoint")
    wait_blocked(runtime)
    response = client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator}, json={
        "endpoint_id": "relay-worker-second", "agent_id": "worker", "adapter_id": "codex",
        "project_root": root, "profile_id": "profile-codex", "enabled": True, "priority": 20,
        "response_policy": "conversation", "public_config": {"relay_results": True}})
    assert response.status_code == 200, response.text
    response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "codex", "endpoint_id": "relay-worker-second", "project_root": root})
    assert response.status_code == 200, response.text
    second = send_message(runtime, body="second worker endpoint")
    assert len(wait_blocked(runtime, count=2)) == 4
    with deps.connection_factory.unit_of_work(write=False) as uow:
        parents = [dict(uow.connection.execute("SELECT * FROM delivery_outbox WHERE operation_id=?",
            (entry["runtime_operations"][0],)).fetchone()) for entry in (first, second)]
        assert {p["endpoint_id"] for p in parents} == {"relay-worker", "relay-worker-second"}
        assert len({p["runtime_session_id"] for p in parents}) == 2
        assert len({p["root_operation_id"] for p in parents}) == 2
        for parent in parents:
            child = uow.connection.execute("""SELECT child.* FROM delivery_outbox child
                JOIN runtime_results result ON result.result_id=child.source_result_id
                WHERE result.operation_id=?""", (parent["operation_id"],)).fetchone()
            assert child["root_operation_id"] == parent["root_operation_id"]
            assert child["recipient_agent_id"] == "caller"
            causal = uow.connection.execute("SELECT * FROM runtime_causal_roots WHERE root_operation_id=?",
                (parent["root_operation_id"],)).fetchone()
            assert (causal["generated_messages"], causal["admitted_executions"]) == (1, 2)


def test_explicit_three_agent_chain_preserves_initiator_and_budget(runtime):
    deps, client, root, _, operator, _ = runtime
    configure(runtime, depth=1)
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id="observer")
    response = client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator}, json={
        "endpoint_id": "relay-observer", "agent_id": "observer", "adapter_id": "codex",
        "project_root": root, "profile_id": "profile-codex", "enabled": True,
        "response_policy": "conversation", "public_config": {"relay_results": True}})
    assert response.status_code == 200, response.text
    response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "observer", "kind": "codex", "endpoint_id": "relay-observer", "project_root": root})
    assert response.status_code == 200, response.text
    response = client.patch("/api/v1/harness/endpoints/relay-worker", headers={"x-api-key": operator}, json={
        "expected_revision": 1, "public_config": {"relay_results": True,
            "notify_target": {"strategy": "direct", "agent_id": "observer"}}})
    assert response.status_code == 200, response.text
    send_message(runtime, body="authorized caller to worker to observer")
    results = wait_blocked(runtime)
    assert len(results) == 2
    assert [r["relay_state"] for r in results] == ["ENQUEUED", "BLOCKED"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        operations = uow.connection.execute("SELECT * FROM delivery_outbox ORDER BY created_at,operation_id").fetchall()
        assert [r["recipient_agent_id"] for r in operations] == ["worker", "observer"]
        assert {r["actor_agent_id"] for r in operations} == {"caller"}
        assert len({r["root_operation_id"] for r in operations}) == 1
        causal = uow.connection.execute("SELECT * FROM runtime_causal_roots").fetchone()
        assert (causal["generated_messages"], causal["admitted_executions"]) == (1, 2)


@pytest.mark.parametrize("agent_key,status", [(True, 403), (False, 422)])
def test_relay_configuration_cannot_be_self_authorized_or_attached_without_results(runtime, agent_key, status):
    _, client, root, _, operator, caller = runtime
    response = client.post("/api/v1/harness/endpoints", headers={"x-api-key": caller if agent_key else operator}, json={
        "endpoint_id": "untrusted-relay", "agent_id": "caller", "adapter_id": "claude_code.attach",
        "project_root": root, "enabled": True, "response_policy": "conversation",
        "public_config": {"relay_results": True, "target_pid": 12345}})
    assert response.status_code == status, response.text


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_result_relay_obeys_canonical_human_approval(runtime, decision):
    from test_governance import _attach, _rule
    from test_runtime_result_publication import result
    deps, client, _, _, operator, _ = runtime
    configure(runtime, depth=1)
    deps.config.feature_hitl = True
    _attach(deps, "worker", governance=[_rule("message_create", "require_approval")])
    source = send_message(runtime, body="human-controlled relay")
    pending = result(runtime, source["runtime_operations"][0], "PENDING_APPROVAL")
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
    response = client.post(f'/api/v1/approvals/{pending["publication_approval_id"]}/decision',
        headers={"x-api-key": operator}, json={"decision": decision})
    assert response.status_code == 200, response.text
    deps.runtime_dispatcher.wake()
    if decision == "approve":
        rows = wait_blocked(runtime)
        assert len(rows) == 2 and rows[0]["relay_state"] == "ENQUEUED"
    else:
        result(runtime, source["runtime_operations"][0], "BLOCKED")
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1


@pytest.mark.parametrize("kind,native,payload,expected", [
    ("pi", "message_end", {"role": "assistant", "stopReason": "aborted"}, "interrupted"),
    ("pi", "message_end", {"message": {"role": "assistant", "stopReason": "error"}}, "failed"),
    ("pi", "agent_settled", {"delivery_outcome": "success"}, None),
    ("claude_code", "result:success", {"interrupted_by_connector": True}, "interrupted"),
    ("claude_code", "result:success", {"is_error": True}, "failed"),
    ("claude_code", "result:error_during_execution", {}, "failed"),
])
def test_adapter_outcome_mapping_does_not_promote_errors_or_payload_claims(kind, native, payload, expected):
    from okto_nexus.adapters.outbound.harness.pi import PiRpcConnector
    from okto_nexus.adapters.outbound.harness.claude_code_stream import ClaudeCodeStreamConnector
    from okto_nexus.domain.harness import HarnessEvent
    event = HarnessEvent(session_id="fixture", harness_kind=kind, kind="turn_completed",
        native_event=native, payload=payload, occurred_at="2026-09-23T00:00:00.000Z")
    adapter = PiRpcConnector if kind == "pi" else ClaudeCodeStreamConnector
    assert adapter.delivery_outcome(event) == expected
