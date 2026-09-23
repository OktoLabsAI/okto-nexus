"""Native approval wire crosses durable journal and canonical operator HITL."""
import sys
import time
import threading

import pytest

from test_pr34_remediation import runtime as runtime_fixture, send_message

runtime = runtime_fixture


def approval_peer(runtime, *, method="item/commandExecution/requestApproval"):
    from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE
    deps, client, root, _, operator, _ = runtime
    deps.config.feature_hitl = True
    source = _FAKE_SERVER_SOURCE.replace("_thread_counter = 0", "_approval_ready = threading.Event()\n_approval_reply = {}\n_thread_counter = 0")
    begin = source.index('    if "TRIGGER_SERVER_REQUEST" in text:')
    end = source.index('    if "TRIGGER_MALFORMED" in text:', begin)
    source = source[:begin] + '''
    if "TRIGGER_SERVER_REQUEST" in text:
        write_msg({"jsonrpc": "2.0", "id": 9001, "method": "item/commandExecution/requestApproval",
                   "params": {"threadId": thread_id, "turnId": turn_id, "itemId": "command-fixture",
                              "startedAtMs": 0, "command": "echo isolated approval fixture"}})
        if not _approval_ready.wait(15):
            return
        text = json.dumps(_approval_reply)
''' + source[end:]
    source = source.replace('            log({"response_to_server_request": msg})',
        '            log({"response_to_server_request": msg})\n            _approval_reply.update(msg)\n            _approval_ready.set()')
    source = source.replace('"item/commandExecution/requestApproval"', repr(method))
    deps.harness_connector_factories["codex"] = lambda **kwargs: CodexAppServerConnector(
        command=[sys._base_executable, "-u", "-c", source], cwd=root, env=kwargs["backend"]["env"])
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert opened.status_code == 200, opened.text
    return opened.json()["data"]["session_id"]


def pending(runtime):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        with runtime[0].connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT * FROM approvals WHERE action='runtime_native_approval'").fetchone()
        if row:
            return dict(row)
        time.sleep(.01)
    runtime[0].runtime_dispatcher.native_approvals.scan_once()
    pytest.fail("Native approval never reached the canonical HITL queue")


@pytest.mark.parametrize("decision,wire", [("approve", "accept"), ("reject", "decline")])
@pytest.mark.parametrize("method", ["item/commandExecution/requestApproval", "item/fileChange/requestApproval"])
def test_native_request_is_durable_and_only_operator_can_decide(runtime, decision, wire, method):
    from test_runtime_handoff_dispatch import wait_result
    _, client, _, _, operator, caller = runtime
    approval_peer(runtime, method=method)
    sent = send_message(runtime, body="TRIGGER_SERVER_REQUEST")
    request = pending(runtime)
    url = f"/api/v1/approvals/{request['approval_id']}/decision"
    assert client.post(url, headers={"x-api-key": caller}, json={"decision": "approve"}).status_code == 403
    approved = client.post(url, headers={"x-api-key": operator}, json={"decision": decision})
    assert approved.status_code == 200, approved.text
    result = wait_result(runtime, sent["runtime_operations"][0])
    assert f'"decision": "{wire}"' in result["output_text"]
    again = client.post(url, headers={"x-api-key": operator}, json={"decision": decision})
    assert again.status_code == 200 and again.json()["data"]["reused"], again.text
    assert client.post(url, headers={"x-api-key": operator}, json={"decision": "reject" if decision == "approve" else "approve"}).status_code == 409
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute("SELECT * FROM runtime_native_approvals").fetchall()
        assert len(rows) == 1
        assert rows[0]["decision"] == wire and rows[0]["state"] == "SENT_UNCONFIRMED"


def test_late_approval_does_not_reach_another_turn(runtime):
    from test_pr34_remediation import tool
    from test_runtime_handoff_dispatch import wait_result
    from test_runtime_commands import wait_operation
    deps, client, _, _, operator, _ = runtime
    sid = approval_peer(runtime)
    sent = send_message(runtime, body="TRIGGER_SERVER_REQUEST")
    request = pending(runtime)
    interrupted = tool(client, operator, "harness_interrupt", {"session_id": sid,
        "expected_operation_id": sent["runtime_operations"][0]})
    assert interrupted["ok"], interrupted
    wait_operation(runtime, interrupted["data"]["operation_id"], lambda row: row["state"] == "SENT_UNCONFIRMED")
    wait_result(runtime, sent["runtime_operations"][0])
    approved = client.post(f"/api/v1/approvals/{request['approval_id']}/decision",
        headers={"x-api-key": operator}, json={"decision": "approve"})
    assert approved.status_code == 200, approved.text
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            state = uow.connection.execute("SELECT state FROM runtime_native_approvals").fetchone()[0]
        if state == "NOT_SENT":
            break
        time.sleep(.01)
    assert state == "NOT_SENT"


@pytest.mark.parametrize("change", ["permission", "flag", "expiry"])
def test_changed_authority_or_expiry_declines_the_native_request(runtime, change):
    from test_runtime_handoff_dispatch import wait_result
    deps, client, _, _, operator, _ = runtime
    approval_peer(runtime)
    sent = send_message(runtime, body="TRIGGER_SERVER_REQUEST")
    request = pending(runtime)
    if change == "flag":
        deps.config.feature_hitl = False
    else:
        with deps.connection_factory.unit_of_work() as uow:
            if change == "permission":
                uow.connection.execute("UPDATE agents SET permissions=? WHERE agent_id='caller'", ('{"messages":{"send_direct":false}}',))
            else:
                uow.connection.execute("UPDATE runtime_native_approvals SET expires_at='2000-01-01T00:00:00.000000Z'")
    approved = client.post(f"/api/v1/approvals/{request['approval_id']}/decision",
        headers={"x-api-key": operator}, json={"decision": "approve"})
    assert approved.status_code == 200, approved.text
    result = wait_result(runtime, sent["runtime_operations"][0])
    assert '"decision": "decline"' in result["output_text"]


def test_journal_retries_approval_projection_without_duplicating_request(runtime, monkeypatch):
    from okto_nexus.application.approvals import ApprovalService
    from test_runtime_handoff_dispatch import wait_result
    deps, client, _, _, operator, _ = runtime
    approval_peer(runtime)
    intercept = ApprovalService.intercept
    failed = threading.Event()
    def cut(self, uow, **kwargs):
        value = intercept(self, uow, **kwargs)
        if kwargs["action"] == "runtime_native_approval":
            failed.set()
            raise OSError("fixture approval projection commit cut")
        return value
    with monkeypatch.context() as patch:
        patch.setattr(ApprovalService, "intercept", cut)
        sent = send_message(runtime, body="TRIGGER_SERVER_REQUEST")
        assert failed.wait(5)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT count(*) FROM approvals").fetchone()[0] == 0
            assert uow.connection.execute("SELECT state FROM runtime_native_approvals").fetchone()[0] == "NEW"
    deps.runtime_dispatcher.wake()
    request = pending(runtime)
    approved = client.post(f"/api/v1/approvals/{request['approval_id']}/decision",
        headers={"x-api-key": operator}, json={"decision": "reject"})
    assert approved.status_code == 200, approved.text
    assert '"decision": "decline"' in wait_result(runtime, sent["runtime_operations"][0])["output_text"]


def test_uncertain_native_reply_is_never_replayed(runtime, monkeypatch):
    from test_runtime_handoff_dispatch import wait_result
    deps, client, _, _, operator, _ = runtime
    approval_peer(runtime)
    sent = send_message(runtime, body="TRIGGER_SERVER_REQUEST")
    request = pending(runtime)
    original, calls = deps.harness_supervisor.reply_native_approval, []
    def cut(*args, **kwargs):
        original(*args, **kwargs)
        calls.append(1)
        raise OSError("fixture cut after native response write")
    with monkeypatch.context() as patch:
        patch.setattr(deps.harness_supervisor, "reply_native_approval", cut)
        url = f"/api/v1/approvals/{request['approval_id']}/decision"
        assert client.post(url, headers={"x-api-key": operator}, json={"decision": "approve"}).status_code == 200
        assert '"decision": "accept"' in wait_result(runtime, sent["runtime_operations"][0])["output_text"]
        assert client.post(url, headers={"x-api-key": operator}, json={"decision": "approve"}).status_code == 200
        deps.runtime_dispatcher.native_approvals.scan_once()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT state FROM runtime_native_approvals").fetchone()[0] == "OUTCOME_UNKNOWN"
    assert calls == [1]


def test_native_approval_on_administrative_turn_uses_same_hitl(runtime):
    from test_pr34_remediation import tool
    from test_runtime_commands import wait_operation
    deps, client, _, _, operator, _ = runtime
    sid = approval_peer(runtime)
    sent = tool(client, operator, "harness_send", {"session_id": sid,
        "payload": {"text": "TRIGGER_SERVER_REQUEST"}, "idempotency_key": "approval-admin"})
    assert sent["ok"], sent
    request = pending(runtime)
    approved = client.post(f"/api/v1/approvals/{request['approval_id']}/decision",
        headers={"x-api-key": operator}, json={"decision": "approve"})
    assert approved.status_code == 200, approved.text
    result = wait_operation(runtime, sent["data"]["operation_id"], lambda r: r["result_durable"])
    assert '"decision": "accept"' in result["result"]["output_text"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT source_kind FROM runtime_native_approvals").fetchone()[0] == "runtime_commands"


def test_authority_changed_after_decision_before_write_is_declined(runtime, monkeypatch):
    from test_runtime_handoff_dispatch import wait_result
    deps, client, _, _, operator, _ = runtime
    approval_peer(runtime)
    sent = send_message(runtime, body="TRIGGER_SERVER_REQUEST")
    request = pending(runtime)
    reply = deps.harness_supervisor.reply_native_approval
    entered, release = threading.Event(), threading.Event()
    def held(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return reply(*args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(deps.harness_supervisor, "reply_native_approval", held)
        try:
            approved = client.post(f"/api/v1/approvals/{request['approval_id']}/decision",
                headers={"x-api-key": operator}, json={"decision": "approve"})
            assert approved.status_code == 200, approved.text
            assert entered.wait(5)
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute("UPDATE agents SET permissions=? WHERE agent_id='caller'", ('{"messages":{"send_direct":false}}',))
        finally:
            release.set()
        result = wait_result(runtime, sent["runtime_operations"][0])
        assert '"decision": "decline"' in result["output_text"]


def test_owner_restart_never_replays_a_pending_native_approval(runtime):
    from okto_nexus.adapters.inbound.mcp.server import bootstrap
    from okto_nexus.adapters.inbound.mcp.tools.harness import build_dispatcher
    from okto_nexus.application.runtime_shutdown import shutdown_runtime
    deps = runtime[0]
    sid = approval_peer(runtime)
    send_message(runtime, body="TRIGGER_SERVER_REQUEST")
    request = pending(runtime)
    supervisor, old = deps.harness_supervisor, deps.runtime_dispatcher
    supervisor.close(sid)
    old.close()
    supervisor.event_ingress.close()
    old._shutdown_finished.set()
    recovered = bootstrap({}, ["--home", str(deps.config.home_dir)])
    recovered.config.feature_harness_integrations = True
    recovered.config.feature_hitl = True
    launches = []
    def forbidden(**kwargs):
        launches.append(kwargs)
        raise AssertionError("Native approval recovery spawned another peer")
    recovered.harness_connector_factories = {kind: forbidden for kind in ("pi", "codex", "claude_code")}
    dispatcher = build_dispatcher(recovered)
    assert dispatcher.start()
    try:
        dispatcher.native_approvals.scan_once()
        with recovered.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT * FROM runtime_native_approvals WHERE approval_id=?", (request["approval_id"],)).fetchone()
            assert row["state"] == "NOT_SENT" and row["reason"] == "owner_changed"
        assert not launches
    finally:
        shutdown_runtime(dispatcher, recovered.harness_supervisor)
