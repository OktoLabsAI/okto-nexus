"""Archiving clears the queue without executing or fabricating a native answer."""
import pytest

from test_hitl import make_env, _ws_id, _client, _events, _issue_key
from okto_nexus.errors import OktoNexusError


def pending(deps, workspace, action="execution.native.respond"):
    with deps.connection_factory.unit_of_work() as uow:
        return deps.approvals.intercept(uow, workspace_id=workspace, agent_id="alpha",
            action=action, policy_id="native-runtime-permission",
            kwargs={"expires_at": "2000-01-01T00:00:00+00:00", "body": "private content"})["approval_id"]


@pytest.mark.parametrize("action", ["execution.native.respond", "runtime_native_approval", "message_create", "handoff_create"])
def test_archive_expired_or_pending_without_executing(tmp_path, action):
    deps, tools, root = make_env(tmp_path)
    workspace = _ws_id(tools, root)
    aid = pending(deps, workspace, action)
    def unexpected(*args, **kwargs):
        pytest.fail("Archiving must not execute or submit a native decision")
    deps.approvals.register_transactional_decision(action, unexpected)
    deps.approvals.register_executor(action, unexpected)
    before = deps.approvals.get_approval(approval_id=aid)
    with _client(deps) as client:
        response = client.post(f"/api/v1/approvals/{aid}/archive")
        assert response.status_code == 200, response.text
        archived = response.json()["data"]
        assert archived["status"] == "archived"
        assert archived["original_status"] == "pending"
        assert archived["archived_by"] == "operator"
        assert "private content" not in response.text
        assert client.post(f"/api/v1/approvals/{aid}/archive").json()["data"] == archived
        for decision in ["approve", "reject"]:
            assert client.post(f"/api/v1/approvals/{aid}/decision", json={"decision": decision}).status_code == 409
        assert client.get("/api/v1/approvals", params={"workspace": workspace, "status": "pending"}).json()["data"]["items"] == []
        assert client.get("/api/v1/approvals", params={"workspace": workspace, "status": "archived"}).json()["data"]["items"] == [archived]
    detail = deps.approvals.get_approval(approval_id=aid)
    assert detail["request_payload"] == before["request_payload"]
    assert detail["decided_at"] is None
    assert len(_events(deps, "approval.archived")) == 1
    assert not _events(deps, "approval.granted")
    assert not _events(deps, "approval.denied")
    with deps.connection_factory.unit_of_work() as uow:
        assert not deps.repos.approvals.mark_decided(uow, approval_id=aid, status="approved",
            decided_by="operator", justification=None, decided_at=deps.clock.now_iso())


def test_archive_operator_only_missing_and_workspace_isolation(tmp_path):
    deps, tools, root = make_env(tmp_path)
    workspace = _ws_id(tools, root)
    aid = pending(deps, workspace)
    with _client(deps) as client:
        assert client.post("/api/v1/approvals/missing/archive").status_code == 404
        client.headers["x-api-key"] = _issue_key(deps, "alpha")
        assert client.post(f"/api/v1/approvals/{aid}/archive").status_code == 403
    assert deps.approvals.get_approval(approval_id=aid)["status"] == "pending"
    deps.approvals.archive(approval_id=aid, archived_by="operator")
    assert deps.approvals.list_approvals(workspace_id="another", status="archived") == []


def test_preserve_decision_and_reject_archive_while_executing(tmp_path):
    deps, tools, root = make_env(tmp_path)
    aid = pending(deps, _ws_id(tools, root), "message_create")
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.approvals.mark_decided(uow, approval_id=aid, status="approved",
            decided_by="operator", justification=None, decided_at=deps.clock.now_iso())
    with pytest.raises(OktoNexusError, match="still executing"):
        deps.approvals.archive(approval_id=aid, archived_by="operator")
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.approvals.set_executed_result(uow, approval_id=aid, executed_result='{"message_id":"msg_test"}')
    before = deps.approvals.get_approval(approval_id=aid)
    deps.approvals.archive(approval_id=aid, archived_by="operator")
    after = deps.approvals.get_approval(approval_id=aid)
    assert after["original_status"] == "approved"
    assert after["executed_result"] == before["executed_result"]
    assert after["decided_at"] == before["decided_at"]
