"""Causal roots come from canonical parents, independent of optional tracing."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, tool

runtime = runtime_fixture


def reply(runtime, parent):
    _, client, root, _, _, caller = runtime
    return tool(client, caller, "message_create", {"project_root": root, "from_agent_id": "caller",
        "target": {"strategy": "direct", "agent_id": "worker"}, "subject": "fixture", "body": "continuation",
        "parent_message_id": parent})


def test_retention_preserves_runtime_fences_and_prunes_unrelated_history(runtime):
    deps = runtime[0]
    from test_runtime_commands import codex_session
    from test_runtime_result_publication import result
    codex_session(runtime)
    source = send_message(runtime)
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
    deps = runtime[0]
    setattr(deps.config, budget, 1 if budget.startswith("max_generated") else 2)
    assert open_rest(runtime).status_code == 200
    first = send_message(runtime)
    # A later configuration change cannot refill the existing root.
    setattr(deps.config, budget, 100)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: reply(runtime, first["message_id"]), range(2)))
    assert sum(bool(r["ok"]) for r in outcomes) == 1, outcomes
    assert [r["error"]["code"] for r in outcomes if not r["ok"]] == ["QUOTA_EXCEEDED"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_message_causality").fetchone()[0] == 2
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 2
        row = uow.connection.execute("SELECT * FROM runtime_causal_roots").fetchone()
        assert row["generated_messages"] == 1
        assert row["admitted_executions"] == 2


def test_expired_root_rejects_continuation_but_allows_explicit_new_entry(runtime):
    deps = runtime[0]
    assert open_rest(runtime).status_code == 200
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
    from test_runtime_commands import codex_session
    from test_runtime_result_publication import result
    deps = runtime[0]
    original = RuntimeCausalityService.record

    def after_deadline(self, uow, **kwargs):
        if kwargs.get("source_result_id"):
            uow.connection.execute("UPDATE runtime_causal_roots SET deadline='2000-01-01T00:00:00.000Z'")
        return original(self, uow, **kwargs)

    monkeypatch.setattr(RuntimeCausalityService, "record", after_deadline)
    codex_session(runtime)
    source = send_message(runtime, body="late result still retained")
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
    deps, client, root, _, _, caller = runtime
    setattr(deps.config, limit, 1)
    assert open_rest(runtime).status_code == 200
    send_message(runtime)
    denied = tool(client, caller, "message_create", {"project_root": root, "from_agent_id": "caller",
        "target": {"strategy": "direct", "agent_id": "worker"}, "subject": "new", "body": "new root"})
    assert not denied["ok"] and denied["error"]["code"] == "QUOTA_EXCEEDED", denied
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_causal_roots").fetchone()[0] == 1


@pytest.mark.parametrize("name,value", [("max_relay_depth", -1), ("max_relay_depth", True),
    ("max_generated_messages_per_root", 0), ("max_executions_per_root", 1025),
    ("root_deadline_seconds", 86401), ("max_new_roots_per_agent_per_minute", 0),
    ("max_new_roots_per_workspace_per_minute", 16385)])
def test_invalid_causal_configuration_fails_closed(name, value):
    from okto_nexus.config import NexusConfig
    from okto_nexus.errors import OktoNexusError
    with pytest.raises(OktoNexusError):
        NexusConfig(**{name: value})


def test_slow_chain_keeps_original_deadline_across_fresh_composition(runtime, monkeypatch):
    from okto_nexus.adapters.inbound.mcp.server import bootstrap
    from okto_nexus.application.runtime_causality import RuntimeCausalityService
    from okto_nexus.domain.base import iso_plus
    deps = runtime[0]
    # No transport needed: this exercises canonical admission with a logical
    # inbox while independent compositions reopen the same isolated store.
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET enabled=0")
    beginning = deps.clock.now_iso()
    monkeypatch.setattr(deps.clock, "now_iso", lambda: beginning)
    parent = send_message(runtime)["message_id"]
    root = None
    for elapsed in (600, 1200, 1800):
        now = iso_plus(beginning, elapsed)
        monkeypatch.setattr(deps.clock, "now_iso", lambda: now)
        reopened = bootstrap({}, ["--home", str(deps.config.home_dir)])
        with reopened.connection_factory.unit_of_work(write=False) as uow:
            node = RuntimeCausalityService.node(uow, parent)
            root = root or node["root_operation_id"]
            assert node["root_operation_id"] == root
            assert node["deadline"] == iso_plus(beginning, 1800)
        child = reply(runtime, parent)
        if elapsed == 1800:
            assert not child["ok"] and child["error"]["code"] == "QUOTA_EXCEEDED", child
        else:
            assert child["ok"], child
            parent = child["data"]["message_id"]


def test_authenticated_reply_inherits_root_instead_of_starting_a_new_budget(runtime):
    deps, client, root, _, _, caller = runtime
    deps.config.feature_trace = False
    assert open_rest(runtime).status_code == 200
    first = send_message(runtime, body="first causal fixture")
    second = tool(client, caller, "message_create", {"project_root": root, "from_agent_id": "caller",
        "target": {"strategy": "direct", "agent_id": "worker"}, "subject": "fixture",
        "body": json.dumps({"root_operation_id": "forged-root", "hop_count": 0,
                            "causation_id": "forged-parent", "max_depth": 99999}),
        "parent_message_id": first["message_id"]})
    assert second["ok"], second
    with deps.connection_factory.unit_of_work(write=False) as uow:
        envelopes = [json.loads(row[0]) for row in uow.connection.execute("SELECT envelope FROM delivery_outbox ORDER BY created_at,operation_id")]
    assert len(envelopes) == 2
    assert envelopes[1]["root_operation_id"] == envelopes[0]["root_operation_id"]
    assert envelopes[1]["root_operation_id"] != "forged-root"
    assert envelopes[1]["hop_count"] == 1
    assert envelopes[1]["causation_id"] == first["message_id"]
