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
from test_pr34_remediation import send_message


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


def _run_native_campaign(tmp_path, kind, native_auth_config, *, active_close=False):
    executable, config_dir = native_auth_config
    root = tmp_path / "project"
    root.mkdir()
    deps = bootstrap({}, ["--home", str(tmp_path / "nexus-home")])
    deps.config.feature_harness_integrations = True
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
            native = deps.harness_supervisor._live[session_id].connector.native
            native_process = native._transport._proc if kind == "codex" else native._proc
            assert native_process is not None and native_process.poll() is None
            assert operator_key not in json.dumps(native._env)
            assert not any("NEXUS" in name and name != "_NEXUS_PROFILE_ENV_SEALED" for name in native._env)
            runtime = deps, client, str(root), [], operator_key, caller_key
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
                assert response.json()["data"]["lifecycle_state"] == "stopped"
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
