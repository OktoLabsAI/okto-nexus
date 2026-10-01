"""Public handoff lifecycle over a logical workspace with no Server path."""
from pathlib import Path

import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_canonical_handoff import prepare


def forbid_paths(monkeypatch):
    from okto_nexus.application import handoff
    def forbidden(*args, **kwargs):
        raise AssertionError("Logical handoff probed a Server-local path")
    monkeypatch.setattr(handoff, "resolve_workspace_id", forbidden)


def workspace(setup):
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT workspace_id,root_realpath FROM workspaces").fetchone()
        assert row[1] is None
        return row[0]


def test_logical_handoff_mcp_create_http_claim_mcp_complete(connected_local, monkeypatch):
    setup, binding, native = connected_local
    wid = workspace(setup)
    forbid_paths(monkeypatch)
    hid, grant, claim, call = prepare(setup, binding, monkeypatch, workspace_id=wid)
    deps, _, client, headers, *_ = setup
    response = client.post(f"/api/v1/workspaces/{wid}/handoffs/{hid}/claim", headers=headers["subject"], json=dict(
        runtime_endpoint_id=binding["endpoint_id"], execution_grant_id=grant, idempotency_key="canonical-work"))
    assert response.status_code == 200, response.text
    replay = claim()
    assert replay["ok"], replay
    assert response.json()["data"]["runtime_operation"]["operation_id"] == replay["data"]["runtime_operation"]["operation_id"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        turn = dict(uow.connection.execute("SELECT operation_id,session_id FROM execution_operations WHERE action='turn.submit'").fetchone())
    wait_receipt(setup, turn)
    viewed = call("handoff_get", handoff_id=hid, agent_id="subject")
    assert viewed["ok"], viewed
    completed = call("handoff_complete", handoff_id=hid, agent_id="subject", claim_epoch=1, result="Reviewed")
    assert completed["ok"], completed
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[0] == "COMPLETED"
        assert uow.connection.execute("SELECT root_realpath FROM workspaces WHERE workspace_id=?", (wid,)).fetchone()[0] is None
    assert native.opens == 1 and len(native.native.sent) == 1
    wait_receipt(setup, admit(setup, binding, "logical-work-close", "runtime.close", session_id=turn["session_id"]), stages=("SUCCEEDED",))


@pytest.mark.parametrize("selector,code", [
    ({"workspace_id": "missing"}, "NOT_FOUND"),
    ({"workspace_id": ""}, "VALIDATION_ERROR"),
    ({"workspace_id": "x", "project_root": "C:/unavailable"}, "VALIDATION_ERROR"),
])
def test_invalid_workspace_leaves_no_handoff(connected_local, monkeypatch, selector, code):
    setup, _, native = connected_local
    forbid_paths(monkeypatch)
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    deps, _, client, headers, *_ = setup
    client.headers["host"] = "127.0.0.1:8000"
    result = tool(client, headers["operator"]["Authorization"].removeprefix("Bearer "), "handoff_create",
        dict(from_agent_id="operator", target=dict(strategy="direct", agent_id="subject"), visibility="eligible", **selector))
    assert not result["ok"] and result["error"]["code"] == code, result
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ("handoffs", "execution_operations", "delivery_outbox"):
            assert uow.connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0
    assert native.opens == 0


def test_logical_handoff_approval_retains_workspace(connected_local, monkeypatch):
    setup, _, _ = connected_local
    wid = workspace(setup)
    forbid_paths(monkeypatch)
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    from test_hitl import _attach, _rule
    deps, _, client, headers, *_ = setup
    deps.config.feature_hitl = True
    _attach(deps, "operator", governance=[_rule("handoff_create", "require_approval")])
    client.headers["host"] = "127.0.0.1:8000"
    result = tool(client, headers["operator"]["Authorization"].removeprefix("Bearer "), "handoff_create",
        dict(workspace_id=wid, from_agent_id="operator", target=dict(strategy="direct", agent_id="subject"), visibility="eligible"))
    assert result["ok"] and result["data"]["status"] == "pending_approval", result
    aid = result["data"]["approval_id"]
    kwargs = deps.approvals.get_approval(approval_id=aid)["request_payload"]["kwargs"]
    assert kwargs["workspace_id"] == wid and kwargs["project_root"] is None
    response = client.post(f"/api/v1/approvals/{aid}/decision", headers=headers["operator"], json={"decision": "approve"})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["executed_result"]["workspace_id"] == wid
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT workspace_id FROM handoffs").fetchone()[0] == wid
