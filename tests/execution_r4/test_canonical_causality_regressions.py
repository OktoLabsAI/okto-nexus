"""Causal admission budgets and retained lineage use canonical runtime bindings."""
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local, enable
from test_agent_recovery_isolation import create_agent
from test_canonical_result_publication import current_turn, emit, wait_result, workspace


@pytest.fixture
def runtime(connected_local, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    setup, binding, _ = connected_local
    setup[2].headers["host"] = "127.0.0.1:8000"
    setup[3]["caller"] = create_agent(setup, "caller")[3]["subject"]
    enable(setup, binding)
    setup[0].runtime_dispatcher.recovery_seconds = .2
    setup[0].runtime_dispatcher.wake()
    return connected_local


def message(runtime, *, body="Causal input", parent=None):
    from test_pr34_remediation import tool
    setup = runtime[0]
    args = dict(workspace_id=workspace(setup), from_agent_id="caller", subject="Causal test",
                body=body, target=dict(strategy="direct", agent_id="subject"))
    if parent:
        args["parent_message_id"] = parent
    return tool(setup[2], setup[3]["caller"]["Authorization"].removeprefix("Bearer "),
                "message_create", args)


def send_message(runtime, *, body="Causal input", finish=False):
    sent = message(runtime, body=body)
    assert sent["ok"], sent
    # Child admission is measured after the initial session is ready. Arrivals
    # during open/recovery intentionally enter the durable pending inbox.
    with runtime[0][0].connection_factory.unit_of_work(write=False) as uow:
        first = uow.connection.execute("SELECT COUNT(*) FROM delivery_outbox").fetchone()[0] == 1
    if sent["data"]["runtime_operations"] and first:
        wait_receipt(runtime[0], current_turn(runtime[0]))
    if finish:
        turn = current_turn(runtime[0])
        wait_receipt(runtime[0], turn)
        emit(runtime[0], runtime[2], turn, body)
    return sent["data"]


def reply(runtime, parent):
    return message(runtime, parent=parent, body="Continuation")


def result(runtime, operation_id, state):
    row = wait_result(runtime[0], state)
    assert row["operation_id"] == operation_id
    return row


def test_retention_preserves_runtime_fences_and_prunes_unrelated_history(runtime):
    deps = runtime[0][0]
    source = send_message(runtime, finish=True)
    result(runtime, source["runtime_operations"][0], "PUBLISHED")
    with deps.connection_factory.unit_of_work() as uow:
        workspace = uow.connection.execute("SELECT workspace_id FROM messages WHERE message_id=?", (source["message_id"],)).fetchone()[0]
        deps.repos.messages.create(uow, message_id="ordinary-old", workspace_id=workspace,
                                  from_agent_id="caller", created_at="2000-01-01T00:00:00.000Z")
    with deps.connection_factory.unit_of_work() as uow:
        cutoff = "2099-01-01T00:00:00.000Z"
        ordinary = uow.connection.execute("SELECT count(*) FROM messages").fetchone()[0] - 2
        assert deps.repos.messages.count_before(uow, cutoff=cutoff) == ordinary
        assert deps.repos.messages.prune_before(uow, cutoff=cutoff, limit=100) == ordinary
        assert deps.repos.deliveries.count_read_before(uow, cutoff=cutoff) == 0
        assert deps.repos.deliveries.prune_read_before(uow, cutoff=cutoff, limit=100) == 0
        assert uow.connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert uow.connection.execute("SELECT count(*) FROM runtime_message_causality").fetchone()[0] == 2


@pytest.mark.parametrize("budget", ["max_generated_messages_per_root", "max_executions_per_root"])
def test_concurrent_children_cannot_exceed_snapshotted_budget(runtime, budget):
    deps = runtime[0][0]
    setattr(deps.config, budget, 1 if budget.startswith("max_generated") else 2)
    first = send_message(runtime)
    # A later configuration change cannot refill the existing root.
    setattr(deps.config, budget, 100)
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: reply(runtime, first["message_id"]), range(8)))
    assert sum(bool(r["ok"]) for r in outcomes) == 1, outcomes
    assert [r["error"]["code"] for r in outcomes if not r["ok"]] == ["QUOTA_EXCEEDED"] * 7
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_message_causality").fetchone()[0] == 2
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 2
        row = uow.connection.execute("SELECT * FROM runtime_causal_roots").fetchone()
        assert row["generated_messages"] == 1
        assert row["admitted_executions"] == 2


def test_expired_root_rejects_continuation_but_allows_explicit_new_entry(runtime):
    deps = runtime[0][0]
    first = send_message(runtime)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_causal_roots SET deadline='2000-01-01T00:00:00.000Z'")
    rejected = reply(runtime, first["message_id"])
    assert not rejected["ok"] and rejected["error"]["code"] == "QUOTA_EXCEEDED", rejected
    send_message(runtime, body="explicit independent entry")
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_causal_roots").fetchone()[0] == 2


def test_late_result_preserves_lineage_without_admitting_execution(runtime, monkeypatch):
    from okto_nexus.application.runtime_causality import RuntimeCausalityService
    deps = runtime[0][0]
    original = RuntimeCausalityService.record

    def after_deadline(self, uow, **kwargs):
        if kwargs.get("source_result_id"):
            uow.connection.execute("UPDATE runtime_causal_roots SET deadline='2000-01-01T00:00:00.000Z'")
        return original(self, uow, **kwargs)

    monkeypatch.setattr(RuntimeCausalityService, "record", after_deadline)
    source = send_message(runtime, body="late result still retained", finish=True)
    published = result(runtime, source["runtime_operations"][0], "PUBLISHED")
    with deps.connection_factory.unit_of_work(write=False) as uow:
        parent = RuntimeCausalityService.node(uow, source["message_id"])
        child = RuntimeCausalityService.node(uow, published["publication_message_id"])
        assert child["root_operation_id"] == parent["root_operation_id"]
        assert child["purpose"] == "observation"
        assert child["hop_count"] == parent["hop_count"] + 1
        assert uow.connection.execute("SELECT admitted_executions FROM runtime_causal_roots").fetchone()[0] == 1


@pytest.mark.parametrize("limit", ["max_new_roots_per_agent_per_minute", "max_new_roots_per_workspace_per_minute"])
def test_new_root_quota_is_independent_of_endpoint_count(runtime, limit):
    deps, _, client, headers, *_ = runtime[0]
    setattr(deps.config, limit, 1)
    send_message(runtime)
    denied = message(runtime, body="New root")
    assert not denied["ok"] and denied["error"]["code"] == "QUOTA_EXCEEDED", denied
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_causal_roots").fetchone()[0] == 1


def test_authenticated_reply_inherits_root_instead_of_starting_a_new_budget(runtime):
    deps, _, client, headers, *_ = runtime[0]
    deps.config.feature_trace = False
    first = send_message(runtime, body="first causal fixture")
    second = message(runtime, parent=first["message_id"], body=json.dumps({"root_operation_id": "forged-root", "hop_count": 0, "causation_id": "forged-parent", "max_depth": 99999}))
    assert second["ok"], second
    with deps.connection_factory.unit_of_work(write=False) as uow:
        envelopes = [json.loads(row[0]) for row in uow.connection.execute("SELECT envelope FROM delivery_outbox ORDER BY created_at,operation_id")]
    assert len(envelopes) == 2
    assert envelopes[1]["root_operation_id"] == envelopes[0]["root_operation_id"]
    assert envelopes[1]["root_operation_id"] != "forged-root"
    assert envelopes[1]["hop_count"] == 1
    assert envelopes[1]["causation_id"] == first["message_id"]

