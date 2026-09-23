"""Canonical claim generations, including the same logical agent reclaiming."""
import pytest

from okto_nexus.domain.base import iso_plus
from okto_nexus.errors import OktoNexusError
from test_handoff import StubClock, make_service, mkdir, row_of, seed_workspace


@pytest.mark.parametrize("verb", ["complete", "reject"])
def test_late_unfenced_result_cannot_transition_reclaimed_work(
    migrated_factory, tmp_config, tmp_path, verb,
):
    clock = StubClock()
    service = make_service(migrated_factory, tmp_config, clock)
    root = str(mkdir(tmp_path, "epoch"))
    seed_workspace(migrated_factory, root, clock)
    hid = service.handoff_create(project_root=root, from_agent_id="creator",
                                 target={"strategy": "broadcast"}, visibility="public")["handoff_id"]
    old = service.handoff_claim(project_root=root, handoff_id=hid, agent_id="worker")
    clock.set(iso_plus(old["lease_expires_at"], 1))
    service.expire_old_leases(project_root=root)
    service.handoff_claim(project_root=root, handoff_id=hid, agent_id="worker")
    # Existing public call, no new symbol/argument: the RED must be actual
    # acceptance of a stale unfenced transition, not an absent API.
    with pytest.raises(OktoNexusError):
        getattr(service, "handoff_" + verb)(project_root=root, handoff_id=hid, agent_id="worker")
    assert row_of(migrated_factory, hid)["status"] == "CLAIMED"
    current = service.handoff_get(project_root=root, handoff_id=hid, agent_id="worker")
    assert current["claim_epoch"] == 2
    for epoch in (1, True, "2", -1):
        with pytest.raises(OktoNexusError):
            getattr(service, "handoff_" + verb)(project_root=root, handoff_id=hid,
                                               agent_id="worker", claim_epoch=epoch)
    done = getattr(service, "handoff_" + verb)(project_root=root, handoff_id=hid,
                                              agent_id="worker", claim_epoch=current["claim_epoch"])
    assert done["status"] == ("COMPLETED" if verb == "complete" else "REJECTED")


def test_authenticated_mcp_and_rest_fence_rework_and_keep_verifier_separate(tmp_path):
    from fastapi.testclient import TestClient
    from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key
    from okto_nexus.application.auth import AgentKeyAuthService
    from test_pr34_remediation import mcp_call
    from test_verification import make_env, _ok

    deps, tools, root = make_env(tmp_path)
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    ensure_operator_key(deps, auth)
    with deps.connection_factory.unit_of_work() as uow:
        author = auth.issue_key(uow, agent_id="alpha")
        worker = auth.issue_key(uow, agent_id="beta")
    with TestClient(build_app(deps), base_url="http://127.0.0.1:18790") as client:
        def tool(client, key, name, arguments):
            import json
            response = mcp_call(client, key, "tools/call", {"name": name, "arguments": arguments})
            assert not response.get("isError"), response
            return response.get("structuredContent") or json.loads(response["content"][0]["text"])

        def call(key, name, agent, **kwargs):
            return tool(client, key, name, dict(project_root=root, agent_id=agent, **kwargs))

        created = _ok(tool(client, author, "handoff_create", {
            "project_root": root, "from_agent_id": "alpha",
            "target": {"strategy": "direct", "agent_id": "beta"},
            "payload": "fixture work", "acceptance_criteria": ["fixture evidence"],
            "visibility": "eligible",
        }))
        hid, ws = created["handoff_id"], created["workspace_id"]
        claimed = _ok(call(worker, "handoff_claim", "beta", handoff_id=hid))
        assert claimed["claim_epoch"] == 1
        _ok(call(worker, "handoff_complete", "beta", handoff_id=hid,
                 claim_epoch=1, result="v1"))
        url = f"/api/v1/workspaces/{ws}/handoffs/{hid}/verify"
        rework = client.post(url, headers={"x-api-key": author},
                             json={"verdict": "fail", "claim_epoch": 1, "feedback": "revise"})
        assert rework.status_code == 200, rework.text
        assert rework.json()["data"]["claim_epoch"] == 2
        stale = call(worker, "handoff_complete", "beta", handoff_id=hid,
                     claim_epoch=1, result="late v1")
        assert stale["error"]["code"] == "INVALID_TRANSITION"
        _ok(call(worker, "handoff_complete", "beta", handoff_id=hid,
                 claim_epoch=2, result="v2"))
        for epoch in (None, 1):
            body = {"verdict": "pass", **({"claim_epoch": epoch} if epoch else {})}
            rejected = client.post(url, headers={"x-api-key": author}, json=body)
            assert rejected.json()["error"]["code"] == "INVALID_TRANSITION"
            rejected_mcp = call(author, "handoff_verify", "alpha", handoff_id=hid,
                                verdict="pass", claim_epoch=epoch)
            assert rejected_mcp["error"]["code"] == "INVALID_TRANSITION"
        self_verify = call(worker, "handoff_verify", "beta", handoff_id=hid,
                           verdict="pass", claim_epoch=2)
        assert self_verify["error"]["code"] == "PERMISSION_DENIED"
        final = client.post(url, headers={"x-api-key": author},
                            json={"verdict": "pass", "claim_epoch": 2})
        assert final.status_code == 200, final.text
        assert final.json()["data"]["status"] == "COMPLETED"
