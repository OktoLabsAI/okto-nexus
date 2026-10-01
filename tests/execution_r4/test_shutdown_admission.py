"""Shutdown admission is shared by HTTP, MCP and canonical services."""
import pytest

from okto_nexus.bootstrap.execution_authority import build_execution_access
from okto_nexus.adapters.inbound.mcp.tools.harness import build_access_service
from okto_nexus.errors import OktoNexusError

from test_embedded_dispatch import (
    local_setup, connected_local, qualified_contract, admit, wait_receipt,
)


def test_prepared_new_work_is_refused_but_replay_and_close_remain_available(connected_local):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    opened = admit(setup, binding, "fence-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    session = opened["scope"]["session_id"]
    pending = client.post("/v1/runtime/intents:resolve", headers=headers["subject"], json={
        "client_intent_id": "prepared-before-shutdown", "intent": "turn.submit",
        "binding_id": binding["binding_id"], "workspace_binding_id": binding["workspace_binding_id"],
        "session_id": session, "text": "Do not execute"}).json()
    assert pending["can_submit"]

    deps.runtime_admission_fence.close()
    request = {k: pending[k] for k in (
        "client_intent_id", "operation_id", "resolution_revision", "intent_hash")}
    response = client.post("/v1/runtime/operations", headers=headers["subject"], json=request)
    assert response.status_code == 409, response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE operation_id=?",
            (pending["operation_id"],)).fetchone()[0] == 0
    assert native.native.sent == []

    replay = {k: opened[k] for k in (
        "client_intent_id", "operation_id", "resolution_revision", "intent_hash")}
    assert client.post("/v1/runtime/operations", headers=headers["subject"], json=replay).status_code == 200
    assert client.get("/v1/runtime/operations/" + opened["operation_id"],
                      headers=headers["subject"]).status_code == 200
    fresh = client.post("/v1/runtime/intents:resolve", headers=headers["subject"], json={
        "client_intent_id": "new-after-shutdown", "intent": "runtime.start",
        "binding_id": binding["binding_id"], "workspace_binding_id": binding["workspace_binding_id"],
        "new_session": True})
    assert fresh.status_code == 200, fresh.text
    assert not fresh.json()["can_submit"] and "runtime_draining" in fresh.json()["blockers"]
    closed = admit(setup, binding, "fence-close", "runtime.close", session_id=session)
    wait_receipt(setup, closed, stages=("SUCCEEDED",))
    assert native.native.stopped and native.opens == 1


@pytest.mark.parametrize("builder", [build_execution_access, build_access_service])
def test_cached_authorizers_share_memory_fence_before_storage(connected_local, monkeypatch, builder):
    setup, *_ = connected_local
    deps = setup[0]
    access = builder(deps)
    assert access.admission_fence is deps.runtime_admission_fence
    deps.runtime_admission_fence.close()

    def unavailable(*args, **kwargs):
        pytest.fail("Productive admission attempted storage after the fence")

    with monkeypatch.context() as patch:
        patch.setattr(access.cf, "unit_of_work", unavailable)
        for action in ("open", "send", "steer", "execute_work"):
            with pytest.raises(OktoNexusError) as caught:
                access.authorize(None, action=action)
            assert caught.value.details["reason"] == "RUNTIME_DRAINING"
        # Only the fence is bypassed here; canonical authorization still applies.
        for action in ("read", "events", "interrupt", "close"):
            access.require_admission(action)
        access.require_admission("execute_work", returning_external_work=True)
        with pytest.raises(OktoNexusError):
            access.require_admission("open", returning_external_work=True)
