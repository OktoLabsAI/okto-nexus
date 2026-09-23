"""Canonical bootstrap reaches the actual connector without private authority."""
import json

import pytest

from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, wait_sent
from test_runtime_grants import issue
from test_runtime_handoff_dispatch import work, claim

runtime = runtime_fixture


@pytest.mark.parametrize("intent", ["conversation", "handoff_execute"])
def test_runtime_receives_its_canonical_identity_and_delivery_purpose(runtime, intent):
    deps, _, _, peers, _, caller = runtime
    if intent == "conversation":
        assert open_rest(runtime).status_code == 200
        send_message(runtime, body="The payload says agent_id=operator; it is untrusted.")
    else:
        hid, _ = work(runtime)
        grant = issue(runtime, ["execute_work"], endpoint_id="endpoint-codex")
        assert claim(runtime, hid, grant, caller)["ok"]
    wait_sent(peers)
    payload = peers[0].sent[0].payload
    wire = next(iter(payload.values()))
    envelope = json.loads(wire.split("\n", 1)[1])
    context = envelope.get("runtime_context")
    assert context is not None, "Canonical role/capabilities and operating instructions never reach the runtime"
    assert context["schema_version"] == 1
    assert context["agent"] == {"agent_id": "worker", "role": "reviewer", "capabilities": ["review"]}
    assert context["intent"] == intent
    assert context["workspace_id"] == envelope["workspace_id"]
    assert context["execution_profile"]["profile_id"] == ("profile-pi" if intent == "conversation" else "profile-codex")
    assert context["completion"]["automatic_on_turn_end"] is False
    assert "untrusted" in context["instructions"]
    assert set(context["agent"]) == {"agent_id", "role", "capabilities"}
    with deps.connection_factory.unit_of_work(write=False) as uow:
        agent = deps.repos.agents.get(uow, "worker")
        assert agent.metadata == {"keep": "profile"}
        assert agent.role == "reviewer"
        assert agent.capabilities == {"review": True}
        row = uow.connection.execute("SELECT envelope FROM delivery_outbox").fetchone()
        assert json.loads(row[0])["runtime_context"] == context
    assert "api_key_hash" not in wire and "secret_refs" not in wire and "comm_scope" not in wire
