"""Remaining work acceptance stimuli through production HTTP/MCP and native pipes."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import threading
import time

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_commands import wait_operation
from test_runtime_grants import issue
from test_runtime_handoff_dispatch import claim, work

runtime = runtime_fixture


def test_competitive_claim_losers_cannot_read_winning_payload_or_runtime(runtime):
    from okto_nexus.application.auth import AgentKeyAuthService
    from test_pr34_remediation import wait_sent
    deps, client, root, peers, operator, _ = runtime
    payload = "private executable payload for the single winning claimant"
    hid, _ = work(runtime, target={"strategy": "role", "role": "reviewer"}, payload=payload)
    identities = []
    for index, agent in enumerate(("worker", "reviewer-two", "reviewer-three")):
        with deps.connection_factory.unit_of_work() as uow:
            deps.repos.agents.upsert(uow, agent_id=agent, role="reviewer")
            key = AgentKeyAuthService(deps.repos.agents, deps.clock).issue_key(uow, agent_id=agent)
            ws = uow.connection.execute("SELECT workspace_id FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[0]
        endpoint = "endpoint-codex" if index == 0 else agent
        if index:
            added = client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator}, json={
                "endpoint_id": endpoint, "agent_id": agent, "adapter_id": "codex", "profile_id": "profile-codex",
                "project_root": root, "enabled": True, "response_policy": "conversation"})
            assert added.status_code == 200, added.text
        opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
            "agent_id": agent, "kind": "codex", "endpoint_id": endpoint, "project_root": root})
        assert opened.status_code == 200, opened.text
        grant = issue(runtime, ["execute_work", "read"], actor_agent_id=agent, endpoint_id=endpoint)
        offer = tool(client, key, "handoff_get", {"project_root": root, "handoff_id": hid, "agent_id": agent})
        assert offer["ok"] and offer["data"]["status"] == "OPEN", offer
        assert payload not in json.dumps(offer)
        identities.append((agent, endpoint, key, grant["grant_id"]))
    barrier = threading.Barrier(3)
    def compete(index):
        agent, endpoint, key, grant = identities[index]
        args = {"agent_id": agent, "runtime_endpoint_id": endpoint, "execution_grant_id": grant,
            "idempotency_key": f"private-pool-{index}"}
        barrier.wait(timeout=5)
        if index == 0:
            reply = client.post(f"/api/v1/workspaces/{ws}/handoffs/{hid}/claim", headers={"x-api-key": key}, json=args)
            return reply.json() | {"ok": reply.status_code == 200}
        return tool(client, key, "handoff_claim", args | {"project_root": root, "handoff_id": hid})
    with ThreadPoolExecutor(max_workers=3) as pool:
        replies = list(pool.map(compete, range(3)))
    winners = [i for i, reply in enumerate(replies) if reply["ok"]]
    assert len(winners) == 1, replies
    winner = winners[0]
    op = replies[winner]["data"]["runtime_operation"]["operation_id"]
    wait_sent(peers)
    for index, (agent, _, key, _) in enumerate(identities):
        handoff = tool(client, key, "handoff_get", {"project_root": root, "handoff_id": hid, "agent_id": agent})
        observed = tool(client, key, "harness_get", {"operation_id": op})
        rest = client.get(f"/api/v1/harness/operations/{op}", headers={"x-api-key": key})
        if index == winner:
            assert handoff["ok"] and handoff["data"]["payload"] == payload
            assert observed["ok"] and rest.status_code == 200
        else:
            assert payload not in json.dumps(replies[index])
            assert payload not in json.dumps(handoff)
            assert "runtime_execution" not in handoff.get("data", {})
            assert not observed["ok"] and observed["error"]["code"] == "PERMISSION_DENIED"
            assert rest.status_code == 403
            assert op not in json.dumps(handoff)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_handoff_bindings WHERE handoff_id=?", (hid,)).fetchone()[0] == 1
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
        assert uow.connection.execute("SELECT sum(used_executions) FROM runtime_execution_grants").fetchone()[0] == 1
    assert sum(len(peer.sent) for peer in peers) == 1


@pytest.mark.parametrize("surface", ["rest", "mcp"])
def test_managed_interrupt_ack_waits_for_native_terminal(runtime, surface):
    from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE
    deps, client, root, _, operator, caller = runtime
    release, ack = Path(root) / "release-interrupt", Path(root) / "interrupt-ack"
    marker = '            write_msg(\n                {\n                    "method": "turn/completed",'
    assert _FAKE_SERVER_SOURCE.count(marker) == 1
    gate = (f'            Path({str(ack)!r}).write_text("ack")\n'
            '            deadline = time.monotonic() + 15\n'
            f'            while not Path({str(release)!r}).exists():\n'
            '                assert time.monotonic() < deadline\n'
            '                time.sleep(.01)\n')
    source = 'from pathlib import Path\n' + _FAKE_SERVER_SOURCE.replace(marker, gate + marker)
    peers = []
    def factory(**kwargs):
        peer = CodexAppServerConnector(command=[sys._base_executable, "-u", "-c", source],
            cwd=root, env=kwargs["backend"]["env"])
        peers.append(peer)
        return peer
    deps.harness_connector_factories["codex"] = factory
    hid, _ = work(runtime, payload="TRIGGER_HOLD executable fixture")
    grant = issue(runtime, ["execute_work"], endpoint_id="endpoint-codex")
    admitted = claim(runtime, hid, grant, caller)
    assert admitted["ok"], admitted
    op = admitted["data"]["runtime_operation"]["operation_id"]
    active = wait_operation(runtime, op, lambda row: row["external_acceptance"] == "observed")
    sid = active["session_id"]
    try:
        args = {"expected_operation_id": op}
        if surface == "rest":
            response = client.post(f"/api/v1/harness/sessions/{sid}/interrupt", headers={"x-api-key": operator}, json=args)
            assert response.status_code == 200, response.text
            command = response.json()["data"]
        else:
            response = tool(client, operator, "harness_interrupt", args | {"session_id": sid})
            assert response["ok"], response
            command = response["data"]
        deadline = time.monotonic() + 5
        while not ack.exists():
            assert time.monotonic() < deadline
            time.sleep(.01)
        pending = wait_operation(runtime, command["operation_id"], lambda row: row["state"] == "SENT_UNCONFIRMED")
        assert pending["verb"] == "interrupt" and pending["expected_operation_id"] == op
        assert not pending["result_durable"]
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert tuple(uow.connection.execute("SELECT status,result FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()) == ("CLAIMED", None)
            assert not uow.connection.execute("SELECT 1 FROM runtime_results WHERE operation_id=?", (op,)).fetchone()
            assert not uow.connection.execute("SELECT terminal_event_id FROM delivery_outbox WHERE operation_id=?", (op,)).fetchone()[0]
        assert not any(e.kind == "turn_completed" for e in deps.harness_supervisor.replay_events(sid))
    finally:
        release.touch()
    terminal = wait_operation(runtime, op, lambda row: row["result_durable"])
    assert terminal["result"]["delivery_outcome"] == "interrupted"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert tuple(uow.connection.execute("SELECT status,result FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()) == ("CLAIMED", None)
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
    events = deps.harness_supervisor.replay_events(sid)
    assert len([e for e in events if e.kind == "turn_completed"]) == 1
    assert len(peers) == 1


def test_restricted_work_profile_keeps_qualified_conversation_useful(runtime):
    from test_runtime_effective_capabilities import open_codex
    deps, client, root, _, operator, caller = runtime
    session = open_codex(runtime, disabled=["managed_work", "approvals"])
    caps = session["compatibility_report"]["effective_capabilities"]
    assert caps["conversation"] and not caps["managed_work"] and not caps["approvals"]
    hid, _ = work(runtime)
    grant = issue(runtime, ["execute_work"], endpoint_id="endpoint-codex")
    denied = claim(runtime, hid, grant, caller)
    assert not denied["ok"] and denied["error"]["code"] == "PERMISSION_DENIED", denied
    incompatible = client.patch("/api/v1/harness/profiles/profile-codex", headers={"x-api-key": operator},
        json={"expected_revision": 2, "config": {"disabled_capabilities": ["approvals", "managed_work"],
            "required_native_requests": ["item/commandExecution/requestApproval"]}})
    assert incompatible.status_code == 422, incompatible.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[0] == "OPEN"
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 0
        assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?", (grant["grant_id"],)).fetchone()[0] == 0
    for index in range(2):
        sent = tool(client, operator, "harness_send", {"session_id": session["session_id"], "payload": {"text": f"safe conversation {index}"}})
        assert sent["ok"], sent
        result = wait_operation(runtime, sent["data"]["operation_id"], lambda row: row["result_durable"])
        assert f"safe conversation {index}" in result["result"]["output_text"]
    wire = [json.loads(line) for line in (Path(root) / "capability-wire.jsonl").read_text().splitlines()]
    assert sum(row.get("request_method") == "turn/start" for row in wire) == 2


@pytest.mark.parametrize("requirement", [{"sandbox": "read-only"}, {"approval_policy": "untrusted"}])
def test_unsupported_sandbox_profile_cannot_replace_compatible_conversation(runtime, requirement):
    from okto_nexus.adapters.outbound.harness.claude_code_stream import ClaudeCodeStreamConnector
    from test_harness_claude_code_connector import _FAKE_CLAUDE_SCRIPT
    deps, client, root, _, operator, _ = runtime
    peers = []
    def factory(**kwargs):
        peer = ClaudeCodeStreamConnector(binary=sys._base_executable, argv=["-u", "-c", _FAKE_CLAUDE_SCRIPT],
            version_argv=["-c", "print('2.1.281 (Claude Code)')"], cwd=root, env=kwargs["backend"]["env"])
        peers.append(peer)
        return peer
    deps.harness_connector_factories["claude_code"] = factory
    denied = client.patch("/api/v1/harness/profiles/profile-claude_code.stream", headers={"x-api-key": operator},
        json={"expected_revision": 1, "config": requirement})
    assert denied.status_code == 422 and denied.json()["error"]["code"] == "VALIDATION_ERROR", denied.text
    assert not peers
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT revision,config FROM runtime_profiles WHERE profile_id='profile-claude_code.stream'").fetchone()
        assert row[0] == 1 and json.loads(row[1]) == {}
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "claude_code", "substrate": "stream",
        "endpoint_id": "endpoint-claude_code.stream", "project_root": root})
    assert opened.status_code == 200, opened.text
    sid = opened.json()["data"]["session_id"]
    sent = tool(client, operator, "harness_send", {"session_id": sid, "payload": {"text": "compatible conversation"}})
    assert sent["ok"], sent
    result = wait_operation(runtime, sent["data"]["operation_id"], lambda row: row["result_durable"])
    assert "echo:compatible conversation" in result["result"]["output_text"]
    assert len(peers) == 1
