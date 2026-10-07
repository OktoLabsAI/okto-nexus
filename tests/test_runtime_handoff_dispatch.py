"""Managed work uses the canonical handoff, inbox reservation and dispatcher."""
from test_pr34_remediation import runtime as runtime_fixture, tool
from okto_nexus.application.auth import AgentKeyAuthService
from test_runtime_grants import issue
from test_runtime_commands import codex_session
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest

runtime = runtime_fixture


def test_competitive_pool_with_multiple_agents_and_endpoints_has_one_executor(runtime):
    from test_pr34_remediation import wait_sent
    deps, client, root, peers, operator, caller = runtime
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id="worker2", role="reviewer")
        AgentKeyAuthService(deps.repos.agents, deps.clock).issue_key(uow, agent_id="worker2")
    headers = {"x-api-key": operator}
    for endpoint, agent in [("pool-worker2", "worker2"), ("pool-worker-extra", "worker")]:
        response = client.post("/api/v1/harness/endpoints", headers=headers, json={
            "endpoint_id": endpoint, "agent_id": agent, "adapter_id": "codex", "project_root": root,
            "profile_id": "profile-codex", "enabled": True, "response_policy": "conversation"})
        assert response.status_code == 200, response.text
    choices = [("worker", "endpoint-codex"), ("worker2", "pool-worker2"), ("worker", "pool-worker-extra")]
    grants = []
    for agent, endpoint in choices:
        response = client.post("/api/v1/harness/sessions", headers=headers, json={
            "agent_id": agent, "kind": "codex", "endpoint_id": endpoint, "project_root": root})
        assert response.status_code == 200, response.text
        grants.append(issue(runtime, ["execute_work"], endpoint_id=endpoint))
    hid, _ = work(runtime, target={"strategy": "role", "role": "reviewer"})
    # Canonical pool offer must not become executable prompt fan-out.
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 0
    barrier = threading.Barrier(3)
    def compete(index):
        agent, endpoint = choices[index]
        barrier.wait(timeout=5)
        return tool(client, caller, "handoff_claim", {"project_root": root, "handoff_id": hid,
            "agent_id": agent, "runtime_endpoint_id": endpoint, "execution_grant_id": grants[index]["grant_id"],
            "idempotency_key": f"pool-claim-{index}"})
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(compete, range(3)))
    winners = [result for result in results if result["ok"]]
    assert len(winners) == 1, results
    wait_sent(peers)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_handoff_bindings WHERE handoff_id=?", (hid,)).fetchone()[0] == 1
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
        assert uow.connection.execute("SELECT sum(used_executions) FROM runtime_execution_grants").fetchone()[0] == 1
    assert sum(bool(peer.sent) for peer in peers) == 1


def work(runtime, **options):
    deps, client, root, _, _, caller = runtime
    with deps.connection_factory.unit_of_work() as uow:
        key = AgentKeyAuthService(deps.repos.agents, deps.clock).issue_key(uow, agent_id="worker")
    created = tool(client, caller, "handoff_create", {
        "project_root": root, "from_agent_id": "caller", "visibility": "eligible",
        "target": {"strategy": "direct", "agent_id": "worker"}, "payload": "fixture managed work", **options,
    })
    assert created["ok"], created
    return created["data"]["handoff_id"], key




def claim(runtime, hid, grant, key, *, request_key="fixture-work", epoch=None):
    return tool(runtime[1], key, "handoff_claim", {
        "project_root": runtime[2], "handoff_id": hid, "agent_id": "worker",
        "runtime_endpoint_id": "endpoint-codex", "execution_grant_id": grant["grant_id"],
        "idempotency_key": request_key, **({"claim_epoch": epoch} if epoch else {}),
    })


def wait_result(runtime, op):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        with runtime[0].connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT * FROM runtime_results WHERE operation_id=?", (op,)).fetchone()
            if row:
                return dict(row)
        time.sleep(.01)
    raise AssertionError("No durable native result")
