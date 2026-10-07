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
