"""Competing Core bindings have one authorized winner and private work history."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, connect_local, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_notify_targets import runtime
from test_agent_recovery_isolation import create_agent
from test_canonical_grant_regressions import mcp_helpers
from test_canonical_result_publication import workspace


def test_competitive_claim_losers_cannot_read_winning_payload_or_runtime(runtime):
    from test_pr34_remediation import tool
    from okto_nexus.domain.base import iso_plus
    added = create_agent(runtime.setup, "reviewer-three")
    added, binding, _ = connect_local(added, agent_id="reviewer-three")
    runtime.setups["reviewer-three"], runtime.bindings["reviewer-three"] = added, binding
    runtime.setup[1].state.embedded_dispatch_owner.native_factory = runtime.factory
    client, deps = runtime.client, runtime.deps
    candidates = ("subject", "observer", "reviewer-three")
    with deps.connection_factory.unit_of_work() as uow:
        for actor in candidates:
            uow.connection.execute("UPDATE agents SET role='reviewer' WHERE agent_id=?", (actor,))
        uow.connection.execute("UPDATE agent_endpoints SET consumption='exclusive',response_policy='none'")
    ws = workspace(runtime.setup)
    def call(actor, name, **kwargs):
        key = runtime.setups[actor][3]["subject"]["Authorization"].removeprefix("Bearer ")
        return tool(client, key, name, dict(workspace_id=ws, **kwargs))
    payload = "Private executable work for the single winner"
    created = call("caller", "handoff_create", from_agent_id="caller", visibility="eligible",
        target=dict(strategy="role", role="reviewer"), payload=payload)
    assert created["ok"], created
    hid = created["data"]["handoff_id"]
    grants = {}
    for actor in candidates:
        grant = client.post("/api/v1/harness/grants", headers=runtime.headers["operator"], json=dict(
            actor_agent_id=actor, endpoint_id=runtime.bindings[actor]["endpoint_id"], actions=["execute_work", "read"],
            max_executions=4, expires_at=iso_plus(deps.clock.now_iso(), 600)))
        assert grant.status_code == 200, grant.text
        grants[actor] = grant.json()["data"]["grant_id"]
        offered = call(actor, "handoff_get", handoff_id=hid, agent_id=actor)
        assert offered["ok"] and payload not in json.dumps(offered), offered
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM delivery_outbox").fetchone()[0] == 0
    barrier = threading.Barrier(3)
    def compete(actor):
        args = dict(agent_id=actor, runtime_endpoint_id=runtime.bindings[actor]["endpoint_id"],
            execution_grant_id=grants[actor], idempotency_key="pool-" + actor)
        barrier.wait(5)
        if actor == "subject":
            return client.post(f"/api/v1/workspaces/{ws}/handoffs/{hid}/claim",
                headers=runtime.setups[actor][3]["subject"], json=args).json()
        return call(actor, "handoff_claim", handoff_id=hid, **args)
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(compete, candidates))
    winners = [actor for actor, response in zip(candidates, responses) if response["ok"]]
    assert len(winners) == 1, responses
    winner = winners[0]
    op = responses[candidates.index(winner)]["data"]["runtime_operation"]["operation_id"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        turn = dict(uow.connection.execute("SELECT p.operation_id FROM execution_operations p JOIN execution_domain_deliveries m USING(server_id,executor_id,operation_id) WHERE m.domain_operation_id=? AND p.action='turn.submit'", (op,)).fetchone())
    wait_receipt(runtime.setups[winner], turn)
    for actor, response in zip(candidates, responses):
        handoff = call(actor, "handoff_get", handoff_id=hid, agent_id=actor)
        observed = call(actor, "harness_get", operation_id=op)
        rest = client.get("/api/v1/harness/operations/" + op, headers=runtime.setups[actor][3]["subject"])
        if actor == winner:
            assert handoff["ok"] and handoff["data"]["payload"] == payload
            assert observed["ok"] and rest.status_code == 200
        else:
            assert payload not in json.dumps(response) + json.dumps(handoff)
            assert op not in json.dumps(handoff)
            assert not observed["ok"] and observed["error"]["code"] == "PERMISSION_DENIED"
            assert rest.status_code == 403
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM runtime_handoff_bindings WHERE handoff_id=?", (hid,)).fetchone()[0] == 1
        assert uow.connection.execute("SELECT COUNT(*) FROM delivery_outbox").fetchone()[0] == 1
        assert uow.connection.execute("SELECT SUM(used_executions) FROM runtime_execution_grants WHERE grant_id IN (?,?,?)", tuple(grants.values())).fetchone()[0] == 1
    assert runtime.factory.opens == 1 and sum(len(p.sent) for p in runtime.peers.values()) == 1
