"""Logical message workspaces do not require a Server-local path."""
from pathlib import Path

import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt


def call(setup, monkeypatch, **selector):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    _, _, client, headers, *_ = setup
    client.headers["host"] = "127.0.0.1:8000"
    return tool(client, headers["operator"]["Authorization"].removeprefix("Bearer "), "message_create",
        dict(from_agent_id="operator", subject="Logical workspace", body="Review this message.",
             target=dict(strategy="direct", agent_id="subject"), **selector))


def forbid_paths(monkeypatch):
    from okto_nexus.application import messages
    def forbidden(*args, **kwargs):
        raise AssertionError("Logical workspace selection probed a local path")
    monkeypatch.setattr(messages, "resolve_realpath", forbidden)
    monkeypatch.setattr(messages, "resolve_workspace_id", forbidden)


def test_message_by_logical_workspace_reaches_core(connected_local, monkeypatch):
    setup, binding, native = connected_local
    deps = setup[0]
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET consumption='exclusive',response_policy='conversation' WHERE endpoint_id=?", (binding["endpoint_id"],))
        workspace = uow.connection.execute("SELECT workspace_id FROM agent_endpoints WHERE endpoint_id=?", (binding["endpoint_id"],)).fetchone()[0]
        assert uow.connection.execute("SELECT root_realpath FROM workspaces WHERE workspace_id=?", (workspace,)).fetchone()[0] is None
    forbid_paths(monkeypatch)
    result = call(setup, monkeypatch, workspace_id=workspace)
    assert result["ok"] and result["data"]["workspace_id"] == workspace, result
    assert not result["data"].get("workspace_created", False)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        turn = dict(uow.connection.execute("SELECT operation_id,session_id FROM execution_operations WHERE action='turn.submit'").fetchone())
        assert uow.connection.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0] == 1
        assert uow.connection.execute("SELECT root_realpath FROM workspaces WHERE workspace_id=?", (workspace,)).fetchone()[0] is None
    wait_receipt(setup, turn)
    assert native.opens == 1 and len(native.native.sent) == 1
    closed = admit(setup, binding, "logical-close", "runtime.close", session_id=turn["session_id"])
    wait_receipt(setup, closed, stages=("SUCCEEDED",))


@pytest.mark.parametrize("selector,code", [
    ({"workspace_id": "missing-logical-workspace"}, "NOT_FOUND"),
    ({"workspace_id": ""}, "VALIDATION_ERROR"),
    ({"workspace_id": "x", "project_root": "C:/unavailable"}, "VALIDATION_ERROR"),
])
def test_invalid_logical_workspace_creates_nothing(connected_local, monkeypatch, selector, code):
    setup, _, native = connected_local
    forbid_paths(monkeypatch)
    result = call(setup, monkeypatch, **selector)
    assert not result["ok"] and result["error"]["code"] == code, result
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        for table in ("messages", "message_deliveries", "execution_operations"):
            assert uow.connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0] == 1
    assert native.opens == 0


def test_logical_workspace_survives_approval_reexecution(connected_local, monkeypatch):
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_hitl import _attach, _rule
    deps.config.feature_hitl = True
    _attach(deps, "operator", governance=[_rule("message_create", "require_approval")])
    with deps.connection_factory.unit_of_work(write=False) as uow:
        workspace = uow.connection.execute("SELECT workspace_id FROM agent_endpoints WHERE endpoint_id=?", (binding["endpoint_id"],)).fetchone()[0]
    forbid_paths(monkeypatch)
    pending = call(setup, monkeypatch, workspace_id=workspace)
    assert pending["ok"] and pending["data"]["status"] == "pending_approval", pending
    approval_id = pending["data"]["approval_id"]
    detail = deps.approvals.get_approval(approval_id=approval_id)
    assert detail["request_payload"]["kwargs"]["workspace_id"] == workspace
    assert detail["request_payload"]["kwargs"]["project_root"] is None
    response = client.post(f"/api/v1/approvals/{approval_id}/decision", headers=headers["operator"], json={"decision": "approve"})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["executed_result"]["workspace_id"] == workspace
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT workspace_id FROM messages").fetchone()[0] == workspace
        assert uow.connection.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0] == 1
    assert native.opens == 0
