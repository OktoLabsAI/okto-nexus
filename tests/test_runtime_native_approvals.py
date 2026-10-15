"""Native approval wire crosses durable journal and canonical operator HITL."""
import sys
import time
import threading

import pytest

from test_pr34_remediation import runtime as runtime_fixture, send_message

runtime = runtime_fixture




def approval_peer(runtime, *, method="item/commandExecution/requestApproval", extra_params=None,
                  control_contract=False):
    from legacy_native_fixture.codex import CodexAppServerConnector
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE
    deps, client, root, _, operator, _ = runtime
    deps.config.feature_hitl = True
    source = _FAKE_SERVER_SOURCE.replace("_thread_counter = 0", "_approval_ready = threading.Event()\n_approval_reply = {}\n_thread_counter = 0")
    if control_contract:
        source = source.replace('"result": {"userAgent": "okto-nexus/0.156.1"}',
            '"result": {"userAgent": "okto-nexus/0.156.1"}', 1)
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
    if extra_params:
        source = source.replace('"startedAtMs": 0, "command": "echo isolated approval fixture"',
                                '"startedAtMs": 0, **' + repr(extra_params))
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
