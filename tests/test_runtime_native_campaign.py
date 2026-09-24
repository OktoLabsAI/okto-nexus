"""Explicit opt-in only. Real local CLI, isolated store/project/config, no personal MCP.

Set OKTO_NEXUS_NATIVE_CAMPAIGN to codex or claude_code, and explicitly supply
OKTO_NEXUS_TEST_EXECUTABLE and OKTO_NEXUS_TEST_AUTH_SOURCE. The latter is a path,
never a token. Only that login file is copied; settings, hooks and sessions are
not copied. The temporary copy is removed on exit. Default pytest makes no calls.
"""
import json
import os
from pathlib import Path
import shutil
import socket
import threading
import time

import httpx
import pytest
import uvicorn

from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key
from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.application.auth import AgentKeyAuthService
from test_pr34_remediation import send_message, tool


@pytest.fixture
def native_auth_config(tmp_path, kind):
    if os.environ.get("OKTO_NEXUS_NATIVE_CAMPAIGN") != kind:
        pytest.skip("NOT_RUN: native campaign requires explicit isolated configuration")
    executable = Path(os.environ["OKTO_NEXUS_TEST_EXECUTABLE"])
    source = Path(os.environ["OKTO_NEXUS_TEST_AUTH_SOURCE"])
    assert executable.is_absolute() and executable.is_file()
    assert source.is_absolute() and source.is_file()
    config_dir = tmp_path / "native-config"
    config_dir.mkdir(mode=0o700)
    auth_copy = config_dir / ("auth.json" if kind == "codex" else ".credentials.json")
    shutil.copyfile(source, auth_copy)
    os.chmod(auth_copy, 0o600)
    try:
        yield executable, config_dir
    finally:
        auth_copy.unlink(missing_ok=True)


@pytest.mark.parametrize("kind", ["codex", "claude_code"])
def test_native_two_turns_via_canonical_inbox_and_journal(tmp_path, kind, native_auth_config):
    _run_native_campaign(tmp_path, kind, native_auth_config)


@pytest.mark.parametrize("kind", ["codex"])
def test_native_active_close_observes_interrupt_terminal(tmp_path, kind, native_auth_config):
    _run_native_campaign(tmp_path, kind, native_auth_config, active_close=True)


@pytest.mark.parametrize("kind", ["codex", "claude_code"])
def test_native_explicit_work_result_preserves_verification(tmp_path, kind, native_auth_config):
    _run_native_campaign(tmp_path, kind, native_auth_config, managed_work=True)


@pytest.mark.parametrize("kind", ["codex", "claude_code"])
def test_native_approval_denial_preserves_security_controls(tmp_path, kind, native_auth_config):
    _run_native_campaign(tmp_path, kind, native_auth_config, native_approval=True)


@pytest.mark.parametrize("kind", ["claude_code"])
def test_native_question_roundtrip_uses_operator_input(tmp_path, kind, native_auth_config):
    _run_native_campaign(tmp_path, kind, native_auth_config, native_input=True)


def _run_native_campaign(tmp_path, kind, native_auth_config, *, active_close=False, managed_work=False, native_approval=False, native_input=False):
    executable, config_dir = native_auth_config
    root = tmp_path / "project"
    root.mkdir()
    deps = bootstrap({}, ["--home", str(tmp_path / "nexus-home")])
    deps.config.feature_harness_integrations = True
    deps.config.feature_hitl = native_approval or native_input
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    _, operator_key = ensure_operator_key(deps, auth)
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id="worker", role="reviewer", metadata={"fixture": True})
        deps.repos.agents.upsert(uow, agent_id="caller")
        caller_key = auth.issue_key(uow, agent_id="caller")
    ready = threading.Event()

    class Server(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets)
            ready.set()

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    app = build_app(deps, runtime_owner_api_url=f"http://127.0.0.1:{port}")
    server = Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    session_id, native_process = None, None
    try:
        thread.start()
        assert ready.wait(15)
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=45, trust_env=False) as client:
            headers = {"x-api-key": operator_key}
            adapter = "codex" if kind == "codex" else "claude_code.stream"
            environment_key = "CODEX_HOME" if kind == "codex" else "CLAUDE_CONFIG_DIR"
            command = [str(executable), "app-server"] if kind == "codex" else [str(executable)]
            response = client.post("/api/v1/harness/profiles", headers=headers, json={
                "profile_id": "native-fixture", "adapter_id": adapter, "enabled": True,
                "inherit_ambient": False, "config": {"command": command,
                    "env": {environment_key: str(config_dir)}}})
            assert response.status_code == 200, response.text
            response = client.post("/api/v1/harness/endpoints", headers=headers, json={
                "endpoint_id": "native-fixture", "agent_id": "worker", "adapter_id": adapter,
                "project_root": str(root), "profile_id": "native-fixture", "enabled": True,
                "response_policy": "conversation"})
            assert response.status_code == 200, response.text
            response = client.post("/api/v1/harness/sessions", headers=headers, json={
                "agent_id": "worker", "kind": kind, "project_root": str(root),
                "endpoint_id": "native-fixture", "idempotency_key": "campaign-open"})
            assert response.status_code == 200, response.text
            session_id = response.json()["data"]["session_id"]
            if kind == "codex":
                compatibility = response.json()["data"]["compatibility_report"]
                assert compatibility["native_version"] and compatibility["observation"] == "initialize_version"
                assert compatibility["capabilities_verified"] is False
            native = deps.harness_supervisor._live[session_id].connector.native
            native_process = native._transport._proc if kind == "codex" else native._proc
            assert native_process is not None and native_process.poll() is None
            assert operator_key not in json.dumps(native._env)
            assert not any("NEXUS" in name and name != "_NEXUS_PROFILE_ENV_SEALED" for name in native._env)
            runtime = deps, client, str(root), [], operator_key, caller_key
            if native_approval or native_input:
                from okto_nexus.domain.base import iso_plus
                marker = root / "approval-denied-fixture.txt"
                handoff = tool(client, caller_key, "handoff_create", {
                    "project_root": str(root), "from_agent_id": "caller", "visibility": "eligible",
                    "target": {"strategy": "direct", "agent_id": "worker"}, "payload": (
                    "Use AskUserQuestion to ask one question: Choose fixture color. Offer exactly blue and green as labels, "
                    "with multiSelect false. Wait for the operator answer. Then reply with that selected color and stop. "
                    "Use no other tools, read or write no files, do not access network or credentials."
                    if native_input else
                    "This is a permission-denial integration test in an empty temporary project. " +
                    ("Request approval using the shell tool with sandbox_permissions=require_escalated before attempting "
                     if kind == "codex" else "Use the Write tool, requesting permission before attempting ") +
                    "to write the literal text fixture into approval-denied-fixture.txt in this project. "
                    "Do not execute an unapproved write or use any other tool to create the file. "
                    "Do not access network, credentials, personal paths or files outside this project. "
                    "If the operator declines, do not retry or seek an alternative; reply DENIED and stop.")})
                assert handoff["ok"], handoff
                grant = client.post("/api/v1/harness/grants", headers=headers, json={
                    "actor_agent_id": "caller", "endpoint_id": "native-fixture", "actions": ["execute_work"],
                    "expires_at": iso_plus(deps.clock.now_iso(), 3600)})
                assert grant.status_code == 200, grant.text
                sent = tool(client, caller_key, "handoff_claim", {
                    "project_root": str(root), "handoff_id": handoff["data"]["handoff_id"], "agent_id": "worker",
                    "runtime_endpoint_id": "native-fixture", "execution_grant_id": grant.json()["data"]["grant_id"],
                    "idempotency_key": "native-approval-work"})
                assert sent["ok"], sent
                op = sent["data"]["runtime_operation"]["operation_id"]
                deadline = time.monotonic() + 90
                pending = None
                while time.monotonic() < deadline:
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        pending = uow.connection.execute("SELECT a.approval_id FROM approvals a JOIN runtime_native_approvals n "
                            "ON n.approval_id=a.approval_id WHERE n.operation_id=? AND a.status='pending'", (op,)).fetchone()
                        result = uow.connection.execute("SELECT 1 FROM runtime_results WHERE operation_id=?", (op,)).fetchone()
                    if pending or result:
                        break
                    time.sleep(.1)
                assert pending, "Native turn did not request a supported canonical approval"
                assert not marker.exists(), "Native write happened before authorization"
                decision_payload = {"decision": "reject", "justification": "Isolated native denial fixture"}
                if native_input:
                    detail = client.get(f"/api/v1/approvals/{pending['approval_id']}", headers=headers)
                    assert detail.status_code == 200, detail.text
                    request = detail.json()["data"]["request_payload"]["kwargs"]["payload"]
                    assert request["params"]["tool_name"] == "AskUserQuestion"
                    questions = request["params"]["input"]["questions"]
                    assert len(questions) == 1 and any(o["label"] == "blue" for o in questions[0]["options"])
                    decision_payload = {"decision": "approve", "response": {"answers": {questions[0]["question"]: "blue"}}}
                rejected = client.post(f"/api/v1/approvals/{pending['approval_id']}/decision", headers=headers,
                                       json=decision_payload)
                assert rejected.status_code == 200, rejected.text
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        result = uow.connection.execute("SELECT result_id FROM runtime_results WHERE operation_id=?", (op,)).fetchone()
                    if result:
                        break
                    time.sleep(.1)
                assert result, "Native turn did not settle after denial"
                assert not marker.exists()
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    reply = uow.connection.execute("SELECT decision,state FROM runtime_native_approvals WHERE operation_id=?", (op,)).fetchone()
                    assert reply["decision"] == ("accept" if native_input else "decline") and reply["state"] == "SENT_UNCONFIRMED"
                    if native_input:
                        output = uow.connection.execute("SELECT output_text FROM runtime_results WHERE operation_id=?", (op,)).fetchone()[0]
                        assert "blue" in output.lower()
                closed = client.post(f"/api/v1/harness/sessions/{session_id}/close", headers=headers, json={})
                from test_runtime_commands import wait_close_result
                assert wait_close_result(client, operator_key, closed)["lifecycle_state"] == "stopped"
                assert native_process.wait(timeout=15) is not None
                return
            if managed_work:
                from okto_nexus.domain.base import iso_plus
                deps.config.feature_verification = True
                handoff = tool(client, caller_key, "handoff_create", {
                    "project_root": str(root), "from_agent_id": "caller", "visibility": "eligible",
                    "target": {"strategy": "direct", "agent_id": "worker"},
                    "acceptance_criteria": ["Result contains the exact isolated fixture marker"],
                    "payload": "Connectivity test only. Do not use tools or modify files. Follow the structured_result_v1 completion contract in runtime_context. Return exactly its required_response JSON, replacing only result with the string OKTO_NEXUS_WORK_FIXTURE. No markdown, commentary or other text."})
                assert handoff["ok"], handoff
                hid = handoff["data"]["handoff_id"]
                grant = client.post("/api/v1/harness/grants", headers=headers, json={
                    "actor_agent_id": "caller", "endpoint_id": "native-fixture", "actions": ["execute_work"],
                    "expires_at": iso_plus(deps.clock.now_iso(), 3600)})
                assert grant.status_code == 200, grant.text
                admitted = tool(client, caller_key, "handoff_claim", {
                    "project_root": str(root), "handoff_id": hid, "agent_id": "worker",
                    "runtime_endpoint_id": "native-fixture", "execution_grant_id": grant.json()["data"]["grant_id"],
                    "idempotency_key": "native-managed-work", "completion_mode": "structured_result_v1"})
                assert admitted["ok"], admitted
                op = admitted["data"]["runtime_operation"]["operation_id"]
                deadline = time.monotonic() + 120
                outcome = None
                while time.monotonic() < deadline:
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        outcome = uow.connection.execute("SELECT state,reason FROM runtime_work_outcomes WHERE operation_id=?", (op,)).fetchone()
                    if outcome:
                        break
                    time.sleep(.1)
                assert outcome and outcome["state"] == "APPLIED", dict(outcome) if outcome else "No explicit native work outcome"
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    row = uow.connection.execute("SELECT status,result FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()
                    assert row["status"] == "VERIFYING"
                    assert row["result"] == "OKTO_NEXUS_WORK_FIXTURE"
                verified = tool(client, caller_key, "handoff_verify", {"project_root": str(root),
                    "handoff_id": hid, "agent_id": "caller", "claim_epoch": 1, "verdict": "pass"})
                assert verified["ok"] and verified["data"]["status"] == "COMPLETED", verified
                closed = client.post(f"/api/v1/harness/sessions/{session_id}/close", headers=headers, json={})
                assert closed.status_code == 200, closed.text
                from test_runtime_commands import wait_close_result
                assert wait_close_result(client, operator_key, closed)["lifecycle_state"] == "stopped"
                assert native_process.wait(timeout=15) is not None
                return
            if active_close:
                sent = send_message(runtime, subject="native interrupt fixture",
                    body="Write a 1000-word fictional story about a lighthouse. Do not use tools or modify files.")
                assert len(sent["runtime_operations"]) == 1
                deadline = time.monotonic() + 30
                started = None
                while time.monotonic() < deadline:
                    events = deps.harness_supervisor.replay_events(session_id)
                    started = next((item for item in events if item.native_event == "turn/started"), None)
                    if started:
                        break
                    time.sleep(.02)
                assert started is not None, "no native turn/started observed"
                response = client.post(f"/api/v1/harness/sessions/{session_id}/close", headers=headers, json={})
                assert response.status_code == 200, response.text
                from test_runtime_commands import wait_close_result
                assert wait_close_result(client, operator_key, response)["lifecycle_state"] == "stopped"
                events = deps.harness_supervisor.replay_events(session_id)
                terminals = [item for item in events if item.native_event == "turn/completed"]
                assert len(terminals) == 1
                assert terminals[0].turn_id == started.turn_id
                assert terminals[0].payload["turn"]["status"] == "interrupted"
                assert terminals[0].sequence < events[-1].sequence
                assert native_process.wait(timeout=15) is not None
                return
            cursor = 0
            native_sessions, native_threads = set(), set()
            for index in range(2):
                result = send_message(runtime, subject=f"native fixture turn {index}",
                    body=f"Connectivity test. Reply with OKTO_NEXUS_FIXTURE_{index}. Do not use tools or modify files.")
                assert len(result["runtime_operations"]) == 1
                deadline = time.monotonic() + 120
                terminal = None
                kinds = set()
                while time.monotonic() < deadline:
                    events = deps.harness_supervisor.replay_events(session_id, after_sequence=cursor, limit=1000)
                    for item in events:
                        cursor = item.sequence
                        kinds.add(item.kind)
                        if item.thread_id:
                            native_threads.add(item.thread_id)
                        if item.payload.get("session_id"):
                            native_sessions.add(item.payload["session_id"])
                        if item.kind == "turn_completed":
                            terminal = item
                    if terminal is not None:
                        break
                    if native_process.poll() is not None:
                        pytest.fail(f"Native process exited before turn completion; observed kinds={sorted(kinds)}")
                    time.sleep(.1)
                assert terminal is not None, f"No terminal in 120s; kinds={sorted(kinds)}"
                assert terminal.payload.get("is_error") is not True
                assert terminal.payload.get("turn", {}).get("status") not in {"failed", "interrupted"}
                assert terminal.payload.get("subtype", "success") == "success"
                assert terminal.operation_id == result["runtime_operations"][0]
                assert terminal.attempt_id and terminal.delivery_phase == "terminal"
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    delivered = uow.connection.execute("SELECT status,terminal_event_id FROM delivery_outbox WHERE operation_id=?",
                        (terminal.operation_id,)).fetchone()
                    assert delivered["status"] == "ACCEPTED" and delivered["terminal_event_id"] == terminal.event_id
                assert native_process.poll() is None, "multi-turn process must survive"
            if kind == "codex":
                assert len(native_threads) == 1
            else:
                assert len(native_sessions) == 1
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute("SELECT count(*) FROM runtime_results").fetchone()[0] == 2
                assert uow.connection.execute("SELECT count(*) FROM runtime_results WHERE output_text<>'' AND output_truncated=0").fetchone()[0] == 2
                assert uow.connection.execute("SELECT count(*) FROM message_deliveries WHERE consumer_kind='push' AND status='read'").fetchone()[0] == 2
                row = uow.connection.execute("SELECT role,metadata FROM agents WHERE agent_id='worker'").fetchone()
                assert row["role"] == "reviewer" and json.loads(row["metadata"]) == {"fixture": True}
            response = client.post(f"/api/v1/harness/sessions/{session_id}/close", headers=headers, json={})
            assert response.status_code == 200, response.text
            assert native_process.wait(timeout=15) is not None
    finally:
        supervisor = getattr(deps, "harness_supervisor", None)
        if supervisor and session_id and supervisor.get(session_id):
            supervisor.close(session_id)
        if native_process is not None and native_process.poll() is None:
            native_process.kill()
            native_process.wait(timeout=5)
        server.should_exit = True
        thread.join(20)
        sock.close()
        assert not thread.is_alive()
