"""Native structured work results use the governed completion transaction."""
import asyncio
import json
import sys
import threading
import time

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff import prepare
from test_canonical_result_publication import current_turn, wait_result, workspace
from test_canonical_grant_regressions import mcp_helpers
from test_harness_codex_connector import _FAKE_SERVER_SOURCE


def native_work(connected, monkeypatch, *, action="complete", mutation=None, verify=False):
    from nexus_connector_core.native.adapters.codex import CodexAppServerConnector
    from nexus_connector_core.native.runtime_bridge import CopiedAdapterSession
    setup, binding, _ = connected
    setup[0].config.feature_verification = verify
    change = ""
    if mutation:
        field, value = mutation
        change = f"    decision[{field!r}] = {value!r}\n"
    transform = ('    envelope = json.loads(text.split("\\n", 1)[1])\n'
        '    decision = {"schema_version":1, "operation_id":envelope["operation_id"], '
        '"handoff_id":envelope["handoff_id"], "claim_epoch":envelope["claim_epoch"], '
        f'"action":{action!r}, {("result" if action == "complete" else "reason")!r}:"Native governed evidence"}}\n'
        + change + '    text = json.dumps({"nexus_work_result": decision})\n')
    source = _FAKE_SERVER_SOURCE.replace('    item_id = "item_" + turn_id', transform + '    item_id = "item_" + turn_id')
    assert source != _FAKE_SERVER_SOURCE
    peers = []
    class Factory:
        async def open(self, prepared, session_id, context, *, stream_epoch):
            peer = CodexAppServerConnector(command=[sys._base_executable, "-u", "-c", source], cwd=str(setup[-1]), env={})
            peers.append(peer)
            native = await asyncio.to_thread(peer.start, owning_agent_id=context.agent_id)
            return CopiedAdapterSession(peer, native, session_id=session_id, stream_epoch=stream_epoch, context=context)
    setup[1].state.embedded_dispatch_owner.native_factory = Factory()
    hid, grant, claim, call = prepare(setup, binding, monkeypatch, workspace_id=workspace(setup))
    if verify:
        with setup[0].connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE handoffs SET acceptance_criteria=? WHERE handoff_id=?", (json.dumps(["Operator reviews evidence"]), hid))
    return setup, binding, hid, grant, claim, call, peers


def state(setup, hid):
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        return dict(uow.connection.execute("SELECT * FROM handoffs WHERE handoff_id=?", (hid,)).fetchone())


@pytest.mark.parametrize("mode", ["complete", "reject", "verify", "unapproved"])
def test_native_structured_work_preserves_explicit_completion_contract(connected_local, monkeypatch, mode):
    setup, _, hid, _, claim, call, peers = native_work(connected_local, monkeypatch,
        action="reject" if mode == "reject" else "complete", verify=mode == "verify")
    first = claim(completion_mode="authenticated_nexus_call" if mode == "unapproved" else "structured_result_v1")
    assert first["ok"], first
    result = wait_result(setup, "BLOCKED" if mode == "unapproved" else "WORK_APPLIED")
    row = state(setup, hid)
    assert row["status"] == dict(complete="COMPLETED", reject="REJECTED", verify="VERIFYING", unapproved="CLAIMED")[mode]
    if mode != "unapproved":
        assert row["rejected_reason" if mode == "reject" else "result"] == "Native governed evidence"
        viewed = call("harness_get", actor="operator", operation_id=first["data"]["runtime_operation"]["operation_id"])
        assert viewed["ok"] and viewed["data"]["work_outcome"]["state"] == "APPLIED", viewed
        assert viewed["data"]["result"]["publication_state"] == "WORK_APPLIED"
    else:
        assert row["result"] is None and "Native governed evidence" in result["output_text"]
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT COUNT(*) FROM runtime_work_outcomes").fetchone()[0] == 0
    assert len(peers) == 1


@pytest.mark.parametrize("mutation", [
    ("operation_id", "forged"), ("handoff_id", "forged"), ("claim_epoch", 2), ("claim_epoch", True),
    ("action", "verify"), ("agent_id", "operator"), ("actor_agent_id", "operator"),
    ("from_agent_id", "operator"), ("execution_grant_id", "forged"), ("root_operation_id", "forged"),
])
def test_native_structured_result_cannot_replace_its_authority(connected_local, monkeypatch, mutation):
    setup, _, hid, _, claim, _, _ = native_work(connected_local, monkeypatch, mutation=mutation)
    admitted = claim(completion_mode="structured_result_v1")
    assert admitted["ok"], admitted
    wait_result(setup, "BLOCKED")
    assert state(setup, hid)["status"] == "CLAIMED" and state(setup, hid)["result"] is None
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT state FROM runtime_work_outcomes").fetchone()[0] == "BLOCKED"


def test_structured_completion_and_receipt_roll_back_then_recover_once(connected_local, monkeypatch):
    from okto_nexus.application.runtime_work import RuntimeWorkService
    setup, _, hid, _, claim, _, peers = native_work(connected_local, monkeypatch)
    original = RuntimeWorkService.record_result
    failed = threading.Event()
    def cut(service, uow, **kwargs):
        original(service, uow, **kwargs)
        if kwargs["state"] == "APPLIED":
            failed.set()
            raise OSError("Fixture atomic structured completion cut")
    with monkeypatch.context() as patch:
        patch.setattr(RuntimeWorkService, "record_result", cut)
        admitted = claim(completion_mode="structured_result_v1")
        assert admitted["ok"], admitted
        assert failed.wait(15)
        assert state(setup, hid)["status"] == "CLAIMED" and state(setup, hid)["result"] is None
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT COUNT(*) FROM runtime_work_outcomes").fetchone()[0] == 0
    setup[0].runtime_dispatcher.wake()
    wait_result(setup, "WORK_APPLIED")
    setup[0].runtime_dispatcher.publish_results()
    assert state(setup, hid)["status"] == "COMPLETED"


def test_revoked_work_grant_blocks_structured_completion_and_preserves_output(connected_local, monkeypatch):
    from okto_nexus.application.handoff import HandoffService
    setup, _, hid, grant, claim, _, _ = native_work(connected_local, monkeypatch)
    original = HandoffService.handoff_complete
    entered, release = threading.Event(), threading.Event()
    def paused(service, **kwargs):
        if kwargs.get("_runtime_result_id"):
            entered.set()
            assert release.wait(20)
        return original(service, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(HandoffService, "handoff_complete", paused)
        try:
            admitted = claim(completion_mode="structured_result_v1")
            assert admitted["ok"], admitted
            assert entered.wait(15)
            response = setup[2].delete("/api/v1/harness/grants/" + grant, headers=setup[3]["operator"])
            assert response.status_code == 200, response.text
        finally:
            release.set()
        result = wait_result(setup, "BLOCKED")
    assert "Native governed evidence" in result["output_text"]
    assert state(setup, hid)["status"] == "CLAIMED" and state(setup, hid)["result"] is None
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT state FROM runtime_work_outcomes").fetchone()[0] == "BLOCKED"


def test_managed_work_revalidation_keeps_read_snapshot_read_only(connected_local, monkeypatch):
    from okto_nexus.adapters.inbound.mcp.tools.handoff import build_service
    setup, _, _, _, claim, _, _ = native_work(connected_local, monkeypatch)
    admitted = claim()
    assert admitted["ok"], admitted
    wait_result(setup, "BLOCKED")  # No implicit completion or conversation disclosure.
    service = build_service(setup[0]).runtime_work
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        before = uow.connection.total_changes
        operation = service.outbox.get(uow, admitted["data"]["runtime_operation"]["operation_id"])
        service.revalidate(uow, operation=operation)
        assert uow.connection.total_changes == before


def test_rest_structured_claim_replays_through_mcp_without_changing_contract(connected_local, monkeypatch):
    setup, binding, hid, grant, claim, _, peers = native_work(connected_local, monkeypatch)
    arguments = dict(agent_id="subject", runtime_endpoint_id=binding["endpoint_id"], execution_grant_id=grant,
                      idempotency_key="canonical-work", completion_mode="structured_result_v1")
    response = setup[2].post(f"/api/v1/workspaces/{workspace(setup)}/handoffs/{hid}/claim",
                            headers=setup[3]["subject"], json=arguments)
    assert response.status_code == 200, response.text
    again = claim(completion_mode="structured_result_v1")
    assert again["ok"] and again["data"]["runtime_operation"]["operation_id"] == response.json()["data"]["runtime_operation"]["operation_id"], again
    assert again["data"]["runtime_operation"]["completion_mode"] == "structured_result_v1"
    changed = claim(completion_mode="authenticated_nexus_call")
    assert not changed["ok"] and changed["error"]["code"] == "CONFLICT", changed
    wait_result(setup, "WORK_APPLIED")
    assert state(setup, hid)["status"] == "COMPLETED" and len(peers) == 1
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM runtime_work_outcomes").fetchone()[0] == 1
        assert not uow.connection.execute("PRAGMA foreign_key_check").fetchall()
    assert len(peers) == 1


def test_conversation_scan_cannot_consume_pending_structured_work(connected_local, monkeypatch):
    from okto_nexus.application.handoff import HandoffService
    from okto_nexus.adapters.inbound.mcp.tools.messages import build_service
    setup, _, hid, _, claim, _, _ = native_work(connected_local, monkeypatch)
    original = HandoffService.process_runtime_results
    entered, release = threading.Event(), threading.Event()
    def paused(service):
        entered.set()
        assert release.wait(20)
        return original(service)
    with monkeypatch.context() as patch:
        patch.setattr(HandoffService, "process_runtime_results", paused)
        setup[0].runtime_dispatcher.wake()
        try:
            assert entered.wait(10)
            admitted = claim(completion_mode="structured_result_v1")
            assert admitted["ok"], admitted
            result = wait_result(setup, "PENDING_AUTHORIZATION")
            messages = build_service(setup[0])
            messages._runtime_results.scan_once(messages)
            with setup[0].connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute("SELECT publication_state FROM runtime_results WHERE result_id=?", (result["result_id"],)).fetchone()[0] == "PENDING_AUTHORIZATION"
                assert uow.connection.execute("SELECT COUNT(*) FROM runtime_work_outcomes").fetchone()[0] == 0
        finally:
            release.set()
        wait_result(setup, "WORK_APPLIED")
    assert state(setup, hid)["status"] == "COMPLETED"
