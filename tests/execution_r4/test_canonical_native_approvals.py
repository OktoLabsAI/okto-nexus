"""Native permission requests traverse actual Core pipes and operator decisions."""
import asyncio
import json
import sys
import threading
import time

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_canonical_grant_regressions import mcp_helpers
from test_harness_codex_connector import _FAKE_SERVER_SOURCE


def approval_peer(connected, *, method="item/commandExecution/requestApproval", cancel_only=False, operator_turn=False):
    from nexus_connector_core.native.adapters.codex import CodexAppServerConnector
    from nexus_connector_core.native.runtime_bridge import CopiedAdapterSession
    setup, binding, _ = connected
    setup[0].config.feature_hitl = True
    source = _FAKE_SERVER_SOURCE.replace("_thread_counter = 0", "_approval_ready = threading.Event()\n_approval_reply = {}\n_thread_counter = 0")
    begin = source.index('    if "TRIGGER_SERVER_REQUEST" in text:')
    end = source.index('    if "TRIGGER_MALFORMED" in text:', begin)
    extra = ', "availableDecisions":["accept", {"acceptWithExecpolicyAmendment":{"execpolicy_amendment":["fixture-only"]}}, "cancel"]' if cancel_only else ""
    source = source[:begin] + (
        '    if "TRIGGER_SERVER_REQUEST" in text:\n'
        f'        write_msg({{"jsonrpc":"2.0", "id":9001, "method":{method!r}, "params":{{"threadId":thread_id, "turnId":turn_id, "itemId":"command-fixture", "command":"echo isolated fixture"{extra}}}}})\n'
        '        if not _approval_ready.wait(30):\n            return\n'
        '        text = json.dumps(_approval_reply)\n') + source[end:]
    source = source.replace('            log({"response_to_server_request": msg})',
        '            log({"response_to_server_request": msg})\n            _approval_reply.update(msg)\n            _approval_ready.set()')
    peers = []
    log = setup[-1] / "native-approval-wire.jsonl"
    class Factory:
        async def open(self, prepared, session_id, context, *, stream_epoch):
            peer = CodexAppServerConnector(command=[sys._base_executable, "-u", "-c", source, str(log)], cwd=str(setup[-1]), env={})
            peer.native_approvals_enabled = True
            peers.append(peer)
            native = await asyncio.to_thread(peer.start, owning_agent_id=context.agent_id)
            return CopiedAdapterSession(peer, native, session_id=session_id, stream_epoch=stream_epoch, context=context)
    setup[1].state.embedded_dispatch_owner.native_factory = Factory()
    opened = admit(setup, binding, "approval-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    if operator_turn:
        from test_operator_runtime import resolve, submit
        response = resolve(setup, binding, intent_id="approval-turn", intent="turn.submit",
                           session_id=opened["session_id"], text="TRIGGER_SERVER_REQUEST")
        assert response.status_code == 200, response.text
        turn = response.json()
        submitted = submit(setup, turn)
        assert submitted.status_code == 202, submitted.text
    else:
        turn = admit(setup, binding, "approval-turn", "turn.submit", session_id=opened["session_id"], text="TRIGGER_SERVER_REQUEST")
    wait_receipt(setup, turn)
    deadline = time.monotonic() + 15
    while True:
        response = setup[2].get("/api/v1/approvals", headers=setup[3]["operator"], params=dict(workspace=binding["workspace_id"], status="pending"))
        assert response.status_code == 200, response.text
        rows = [r for r in response.json()["data"]["items"] if r["action"] == "execution.native.respond"]
        if rows:
            break
        assert time.monotonic() < deadline, response.text
        time.sleep(.02)
    assert len(rows) == 1
    detail = setup[2].get("/api/v1/approvals/" + rows[0]["approval_id"], headers=setup[3]["operator"])
    assert detail.status_code == 200, detail.text
    proposal = detail.json()["data"]["request_payload"]["kwargs"]
    body = {k: proposal[k] for k in ("approval_key", "expected_revision", "request_hash", "cas_token")}
    body.update(client_intent_id="native-permission", decision="approve")
    return setup, binding, turn, body, peers[0], log


@pytest.mark.parametrize("method", ["item/commandExecution/requestApproval", "item/fileChange/requestApproval"])
@pytest.mark.parametrize("choice", ["approve", "deny"])
def test_real_native_approval_is_durable_operator_only_and_idempotent(connected_local, method, choice):
    setup, _, turn, body, peer, log = approval_peer(connected_local, method=method)
    body["decision"] = choice
    path = "/v1/runtime/approval-decisions"
    assert setup[2].post(path, headers=setup[3]["subject"], json=body).status_code == 403
    first = setup[2].post(path, headers=setup[3]["operator"], json=body)
    assert first.status_code == 202, first.text
    again = setup[2].post(path, headers=setup[3]["operator"], json=body)
    assert again.status_code == 200 and again.json()["native_operation_id"] == first.json()["native_operation_id"], again.text
    changed = setup[2].post(path, headers=setup[3]["operator"], json=dict(body, decision="deny" if choice == "approve" else "approve"))
    assert changed.status_code == 409, changed.text
    wait_receipt(setup, turn, stages=("SUCCEEDED",))
    replies = [r["response_to_server_request"] for r in map(json.loads, log.read_text(encoding="utf-8").splitlines()) if "response_to_server_request" in r]
    assert len(replies) == 1 and replies[0]["result"]["decision"] == ("accept" if choice == "approve" else "decline"), replies
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_native_requests").fetchone()[0] == 1
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_decisions").fetchone()[0] == 1


@pytest.mark.parametrize("choice,wire", [("approve", "accept"), ("deny", "cancel")])
def test_real_cancel_only_request_cannot_mint_policy_amendment(connected_local, choice, wire):
    setup, _, turn, body, _, log = approval_peer(connected_local, cancel_only=True)
    response = setup[2].post("/v1/runtime/approval-decisions", headers=setup[3]["operator"], json=dict(body, decision=choice))
    assert response.status_code == 202, response.text
    wait_receipt(setup, turn, stages=("SUCCEEDED",))
    replies = [r["response_to_server_request"] for r in map(json.loads, log.read_text(encoding="utf-8").splitlines()) if "response_to_server_request" in r]
    assert len(replies) == 1 and replies[0]["result"]["decision"] == wire, replies
    assert "acceptWithExecpolicyAmendment" not in json.dumps(replies)


def test_operator_initiated_turn_uses_same_native_permission_workflow(connected_local):
    setup, _, turn, body, _, log = approval_peer(connected_local, operator_turn=True)
    response = setup[2].post("/v1/runtime/approval-decisions", headers=setup[3]["operator"], json=body)
    assert response.status_code == 202, response.text
    wait_receipt(setup, turn, stages=("SUCCEEDED",))
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT actor_agent_id,subject_agent_id FROM execution_operations WHERE operation_id=?", (turn["operation_id"],)).fetchone()[:] == ("operator", "subject")
    replies = [r["response_to_server_request"] for r in map(json.loads, log.read_text(encoding="utf-8").splitlines()) if "response_to_server_request" in r]
    assert len(replies) == 1 and replies[0]["result"]["decision"] == "accept"


@pytest.mark.parametrize("change", ["permission", "flag", "expiry"])
def test_changed_native_approval_authority_cannot_reach_the_pipe(connected_local, change):
    setup, _, _, body, _, log = approval_peer(connected_local)
    if change == "flag":
        setup[0].config.feature_hitl = False
    else:
        with setup[0].connection_factory.unit_of_work() as uow:
            if change == "permission":
                uow.connection.execute("UPDATE agents SET permissions=? WHERE agent_id='subject'", ('{"messages":{"send_direct":false}}',))
            else:
                uow.connection.execute("UPDATE execution_native_requests SET expires_at='2000-01-01T00:00:00Z'")
    response = setup[2].post("/v1/runtime/approval-decisions", headers=setup[3]["operator"], json=body)
    if response.status_code == 202:
        deadline = time.monotonic() + 10
        while True:
            view = setup[2].get("/v1/runtime/approval-decisions/" + response.json()["decision_id"], headers=setup[3]["operator"])
            assert view.status_code == 200, view.text
            if view.json()["native_stage"] == "REFUSED_BEFORE_EFFECT":
                break
            assert time.monotonic() < deadline, view.text
            time.sleep(.02)
    else:
        assert response.status_code in (403, 409), response.text
    assert "response_to_server_request" not in log.read_text(encoding="utf-8")


def test_native_approval_projection_rollback_recovers_without_duplicate_request(connected_local, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from okto_nexus.application import execution_events
    original = execution_events.project_native_request
    failed, retried, allow = threading.Event(), threading.Event(), threading.Event()
    attempts = []
    def cut(conn, **kwargs):
        original(conn, **kwargs)
        if kwargs["event"].get("category") == "approval_request" and not allow.is_set():
            attempts.append(1)
            failed.set()
            if len(attempts) > 1:
                retried.set()
            raise OSError("Fixture native request projection cut")
    monkeypatch.setattr(execution_events, "project_native_request", cut)
    with ThreadPoolExecutor(max_workers=1) as pool:
        opening = pool.submit(approval_peer, connected_local)
        try:
            assert failed.wait(12)
            assert retried.wait(5), "Server projection was not retried automatically"
            assert "subject" not in connected_local[0][1].state.embedded_dispatch_owner.agents.blocked
            with connected_local[0][0].connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute("SELECT COUNT(*) FROM execution_native_requests").fetchone()[0] == 0
                assert uow.connection.execute("SELECT COUNT(*) FROM approvals WHERE action='execution.native.respond'").fetchone()[0] == 0
                assert uow.connection.execute("SELECT lifecycle_state,lease_state FROM execution_sessions").fetchone()[:] == ("READY", "ACTIVE")
        finally:
            allow.set()
        setup, _, turn, body, peer, log = opening.result(timeout=15)
    assert peer._transport._proc.poll() is None
    response = setup[2].post("/v1/runtime/approval-decisions", headers=setup[3]["operator"], json=dict(body, decision="deny"))
    assert response.status_code == 202, response.text
    wait_receipt(setup, turn, stages=("SUCCEEDED",))
    assert log.read_text(encoding="utf-8").count("response_to_server_request") == 1
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_native_requests").fetchone()[0] == 1


def test_lost_native_approval_reply_never_reexecutes_on_decision_replay(connected_local, monkeypatch):
    from nexus_connector_core.native.runtime_bridge import CopiedAdapterSession
    setup, _, turn, body, _, log = approval_peer(connected_local)
    original = CopiedAdapterSession.reply_native_approval
    calls = []
    async def cut(self, *args, **kwargs):
        await original(self, *args, **kwargs)
        calls.append(1)
        raise OSError("Fixture lost acknowledgement after native approval write")
    monkeypatch.setattr(CopiedAdapterSession, "reply_native_approval", cut)
    path = "/v1/runtime/approval-decisions"
    first = setup[2].post(path, headers=setup[3]["operator"], json=body)
    assert first.status_code == 202, first.text
    deadline = time.monotonic() + 10
    while True:
        view = setup[2].get(path + "/" + first.json()["decision_id"], headers=setup[3]["operator"])
        assert view.status_code == 200, view.text
        if view.json()["native_stage"] == "OUTCOME_UNKNOWN" and calls:
            break
        assert time.monotonic() < deadline, view.text
        time.sleep(.02)
    assert view.json()["possible_effect"] is True
    repeated = setup[2].post(path, headers=setup[3]["operator"], json=body)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["native_operation_id"] == first.json()["native_operation_id"]
    assert calls == [1]
    assert log.read_text(encoding="utf-8").count("response_to_server_request") == 1


def test_old_native_permission_cannot_control_a_subsequent_turn(connected_local):
    setup, binding, turn, body, _, log = approval_peer(connected_local)
    interrupted = admit(setup, binding, "interrupt-native-permission", "turn.interrupt", session_id=turn["session_id"],
                        target=dict(kind="current_run", expected_turn_id=None))
    wait_receipt(setup, interrupted)
    wait_receipt(setup, turn, stages=("CANCELLED",))
    refused = setup[2].post("/v1/runtime/approval-decisions", headers=setup[3]["operator"], json=body)
    assert refused.status_code in (403, 409), refused.text
    subsequent = admit(setup, binding, "after-interrupted-permission", "turn.submit", session_id=turn["session_id"], text="New authorized turn")
    wait_receipt(setup, subsequent, stages=("SUCCEEDED",))
    assert "response_to_server_request" not in log.read_text(encoding="utf-8")


def test_native_permission_is_rechecked_after_decision_before_dispatch(connected_local):
    setup, _, _, body, _, log = approval_peer(connected_local)
    lock = setup[1].state.embedded_dispatch_owner.pump.send_lock
    setup[2].portal.call(lock.acquire)
    try:
        confirmed = setup[2].post("/v1/runtime/approval-decisions", headers=setup[3]["operator"], json=body)
        assert confirmed.status_code == 202, confirmed.text
        with setup[0].connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at='revoked-before-permission-write'")
    finally:
        setup[2].portal.call(lock.release)
    deadline = time.monotonic() + 10
    while True:
        viewed = setup[2].get("/v1/runtime/approval-decisions/" + confirmed.json()["decision_id"], headers=setup[3]["operator"])
        assert viewed.status_code == 200, viewed.text
        if viewed.json()["native_stage"] == "REFUSED_BEFORE_EFFECT":
            break
        assert time.monotonic() < deadline, viewed.text
        time.sleep(.02)
    assert "response_to_server_request" not in log.read_text(encoding="utf-8")


def test_server_restart_does_not_replay_pending_native_permission(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from fastapi.testclient import TestClient
    from test_embedded_dispatch import connect_local
    from test_embedded_inventory import app_for
    with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, None) as initial:
        setup, _, _, body, peer, log = approval_peer(connect_local(initial))
        headers = setup[3]
    assert peer._transport._proc.poll() is not None
    before = log.read_text(encoding="utf-8")
    deps, app = app_for(tmp_path / "home")
    with TestClient(app) as client:
        owner = app.state.embedded_dispatch_owner
        class ForbiddenFactory:
            async def open(self, *args, **kwargs):
                raise AssertionError("Old native approval attempted to launch a provider")
        owner.native_factory = ForbiddenFactory()
        response = client.post("/v1/runtime/approval-decisions", headers=headers["operator"], json=body)
        assert response.status_code in (403, 409), response.text
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT COUNT(*) FROM execution_decisions").fetchone()[0] == 0
            assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='approval.decide'").fetchone()[0] == 0
        assert log.read_text(encoding="utf-8") == before
