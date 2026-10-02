"""Opt-in real providers through public Connector onboarding and runtime CLI."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import time

import httpx
import pytest

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.domain.base import iso_plus
from test_mcp_session_capabilities import seed_work


@pytest.mark.skipif(os.environ.get("OKTO_NEXUS_REAL_CONNECTOR") != "1",
                    reason="The real Connector provider campaign is opt-in.")
@pytest.mark.parametrize("adapter", ["pi_rpc", "codex_app_server", "claude_stream"])
def test_real_provider_through_public_connector_cli(tmp_path, monkeypatch, adapter):
    from okto_nexus_connector.cli.commands.identity import _vault
    from okto_nexus_connector.daemon.app import DaemonApp
    from okto_nexus_connector.identity.vault import KeyringVault, namespace_of
    from okto_nexus_connector.platform import paths
    from okto_nexus_connector.storage.state_store import StateStore

    user_home = Path.home()
    missing_login = os.environ.get("OKTO_NEXUS_REAL_CONNECTOR_MISSING_LOGIN") == "1"
    codex = Path(os.environ.get("OKTO_NEXUS_REAL_CODEX_BINARY", str(user_home / "AppData/Roaming/npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe")))
    claude = Path(os.environ.get("OKTO_NEXUS_REAL_CLAUDE_BINARY", str(user_home / ".local/bin/claude.exe")))
    node = Path(os.environ.get("OKTO_NEXUS_REAL_PI_NODE", "C:/Program Files/nodejs/node.exe"))
    pi_install = Path(os.environ.get("OKTO_NEXUS_REAL_PI_HOME", str(user_home / ".pi/agent"))) / "install"
    provider_home = user_home
    if missing_login:
        provider_home = tmp_path / "empty-provider-home"
        provider_home.mkdir()
        (provider_home / ".codex").mkdir()
        pi_home = provider_home / ".pi/agent"
        pi_home.mkdir(parents=True)
        (pi_home / "settings.json").write_text(json.dumps({
            "defaultProvider": "anthropic", "defaultModel": "claude-haiku-4-5"}), encoding="utf-8")
    binary = {"pi_rpc": node, "codex_app_server": codex, "claude_stream": claude}[adapter]
    assert binary.is_file(), "The selected real provider executable is missing."
    monkeypatch.setenv("PATH", str(binary.parent) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.delenv("OKTO_NEXUS_CONNECTOR_VAULT", raising=False)
    deps = bootstrap({}, ["--home", str(tmp_path / "nexus"), "--feature-harness-integrations", "true",
                          "--feature-hitl", "true"])
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    origin = "http://127.0.0.1:" + str(port)
    app = build_app(deps, runtime_owner_api_url=origin)
    headers = {}
    with deps.connection_factory.unit_of_work() as uow:
        for actor in ("operator", "subject"):
            uow.connection.execute("INSERT OR IGNORE INTO agents(agent_id,created_at) VALUES (?,?)",
                                   (actor, deps.clock.now_iso()))
            headers[actor] = {"Authorization": "Bearer " + app.state.auth.issue_key(uow, agent_id=actor)}
    root, workspace = tmp_path / "connector", tmp_path / "workspace"
    workspace.mkdir()
    store = StateStore(paths.state_file(root))
    report = dict(adapter=adapter, missing_login=missing_login, server_release_gate_override=False, native_qualification_override=False,
                  synthetic_native_factory=False, public_connector_cli=True, cli_subprocess=True, protected_os_vault=False,
                  topology="Single Windows host; actual loopback HTTP/WSS; separate Server and daemon processes.")
    def checkpoint(phase):
        report["phase"] = phase
        destination = os.environ.get("OKTO_NEXUS_REAL_CONNECTOR_REPORT")
        if destination:
            Path(destination + "-" + adapter + "-progress.json").write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if os.environ.get("OKTO_NEXUS_PI_STREAM_DIAGNOSTIC") == "1" and adapter == "pi_rpc":
        import traceback
        from nexus_connector_core.runtime import LocalRuntimeCore
        from okto_nexus_connector.services import launch_configuration
        from okto_nexus_connector.transport.native_actions import RefreshingNativeActionBridge
        report["stream_diagnostic"] = True
        original_loss = LocalRuntimeCore._record_stream_loss
        original_resolve = launch_configuration._resolve
        original_invoke = RefreshingNativeActionBridge.invoke
        async def observed_loss(runtime, session, binding):
            error = sys.exception()
            report.setdefault("stream_failures", []).append(dict(
                exception_type=type(error).__name__ if error is not None else "unexpected_eof",
                code=getattr(error, "code", None),
                frames=[dict(file=Path(frame.filename).name, function=frame.name, line=frame.lineno)
                        for frame in traceback.extract_tb(error.__traceback__)] if error is not None else []))
            checkpoint("native_stream_loss")
            return await original_loss(runtime, session, binding)
        def observed_resolve(*args, **kwargs):
            started = time.monotonic()
            try:
                return original_resolve(*args, **kwargs)
            finally:
                report.setdefault("selection_check_seconds", []).append(time.monotonic() - started)
        async def observed_invoke(bridge, request, context):
            started = time.monotonic()
            outcome = "returned"
            try:
                return await original_invoke(bridge, request, context)
            except BaseException as error:
                outcome = type(error).__name__ + ":" + str(getattr(error, "code", ""))
                raise
            finally:
                report.setdefault("native_bridge_calls", []).append(dict(
                    seconds=time.monotonic() - started, outcome=outcome))
        monkeypatch.setattr(LocalRuntimeCore, "_record_stream_loss", observed_loss)
        monkeypatch.setattr(launch_configuration, "_resolve", observed_resolve)
        monkeypatch.setattr(RefreshingNativeActionBridge, "invoke", observed_invoke)
    async def run():
        server = await asyncio.create_subprocess_exec(
            sys.executable, "-I", str(Path(__file__).with_name("real_provider_server.py")),
            "--home", str(tmp_path / "nexus"), "--port", str(port),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL)
        daemon = daemon_task = None
        async with httpx.AsyncClient(base_url=origin, timeout=30, trust_env=False) as http:
            async def cli(group, *words):
                checkpoint(group + "." + (words[0] if words else "preview"))
                process = await asyncio.create_subprocess_exec(
                    sys.executable, "-I", "-m", "okto_nexus_connector.cli.main",
                    "--json", "--non-interactive", "--state-dir", str(root), group,
                    *map(str, words), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                # The public CLI owns a separate process, like a real operator.
                # Retain it until the command settles, even if its observer cancels.
                capture = asyncio.create_task(process.communicate())
                try:
                    stdout, stderr = await asyncio.shield(capture)
                except asyncio.CancelledError:
                    await asyncio.shield(capture)
                    raise
                assert process.returncode == 0, (process.returncode, stdout.decode(), stderr.decode())
                result = json.loads(stdout)
                checkpoint(group + ".returned")
                return result
            async def post(path, body):
                response = await http.post(path, headers=headers["operator"], json=body)
                assert response.status_code in (200, 201, 202), (response.status_code, response.text)
                return response.json()
            try:
                async with asyncio.timeout(120):
                    while True:
                        assert server.returncode is None, "The Server exited before readiness."
                        try:
                            ready = await http.get("/v1/connections/protocol")
                            if ready.status_code == 200:
                                break
                        except httpx.ConnectError:
                            pass
                        await asyncio.sleep(.05)
                monkeypatch.setenv("OKTO_REAL_CONNECTOR_IDENTITY", headers["subject"]["Authorization"][7:])
                imported = await cli("identity", "add", "--server", origin, "--alias", "subject",
                    "--agent", "subject", "--credential-env", "OKTO_REAL_CONNECTOR_IDENTITY")
                monkeypatch.delenv("OKTO_REAL_CONNECTOR_IDENTITY")
                server_id = imported["server_id"]
                registered = await cli("executor", "register", "--identity", "subject",
                                       "--label", "Real provider campaign", "--client-intent-id", "register")
                discovery = ["configure-discovery", "--server-id", server_id, "--harness-root", str(binary.parent)]
                if adapter == "pi_rpc":
                    discovery += ["--harness-root", str(pi_install), "--pi-install-root", str(pi_install),
                                  "--pi-node", str(node)]
                await cli("executor", *discovery)
                daemon = DaemonApp(root)
                assert isinstance(daemon.vault, KeyringVault), "The campaign requires a protected OS vault."
                report["protected_os_vault"] = True
                report["vault_backend"] = daemon.vault.backend_name()
                daemon_task = asyncio.create_task(daemon.run_forever())
                checkpoint("waiting_for_control_readiness")
                async with asyncio.timeout(120):
                    while True:
                        control = daemon.r4_controls.get(server_id)
                        if (os.environ.get("OKTO_NEXUS_REAL_DISCOVERY_STOP") == "1"
                                and control is not None and control.phase == "PUBLISHING_INVENTORY"
                                and control.publication_sequence == 0):
                            checkpoint("stopping_during_passive_discovery")
                            started = time.monotonic()
                            daemon.request_stop()
                            code = await asyncio.wait_for(asyncio.shield(daemon_task), 10)
                            report["discovery_stop_seconds"] = time.monotonic() - started
                            assert code == 0 and control._task.done()
                            assert control.phase == "STOPPED" and control.publication_sequence == 0
                            assert not daemon.r4_controls and not daemon.r4_executions
                            with deps.connection_factory.unit_of_work(write=False) as uow:
                                assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 0
                            report["discovery_stopped_before_publication"] = True
                            report["completed"] = True
                            return
                        if control and control.status()["control_ready"]:
                            break
                        if daemon_task.done():
                            raise AssertionError("The Connector daemon exited before readiness.")
                        await asyncio.sleep(.1)
                inventory = await cli("discover", "--server-id", server_id)
                row = next(r for r in inventory["availability"]["rows"]
                           if r["adapter_id"] == adapter and r["candidate_ref"])
                report["candidate_ref"] = row["candidate_ref"]
                config = await cli("executor", "configure-launch", "--identity", "subject",
                    "--harness", adapter, "--local-consent-id", "authorized-real-provider-campaign",
                    "--profile-revision", "1", "--provider-home", str(provider_home))
                realized = await cli("executor", "realize", "--identity", "subject", "--client-intent-id", "realize",
                    "--harness", adapter, "--candidate-ref", row["candidate_ref"],
                    "--inventory-revision", inventory["availability"]["executor_revision"],
                    "--configuration-digest", config["configuration_digest"], "--project", str(workspace),
                    "--label", "Real Connector work")
                proposal = (await cli("bind", "prepare", "--identity", "subject",
                    "--realization-ref", realized["realization_ref"], "--alias", "assistant",
                    "--client-intent-id", "prepare"))["proposal"]
                proof = next(r for r in proposal["required_approvals"] if r.startswith("apr_"))
                await post("/api/v1/approvals/" + proof + "/decision", {"decision": "approve"})
                bound = await cli("bind", "apply", "--identity", "subject", "--prepare-intent-id", "prepare",
                    "--client-intent-id", "apply", "--approved-diff-hash", proposal["approved_diff_hash"],
                    "--operator-proof-ref", proof)
                binding = bound["binding"]
                await post("/api/v1/harness/grants", dict(actor_agent_id="subject", endpoint_id=binding["endpoint_id"],
                    actions=["open", "send", "steer", "interrupt", "close"], max_executions=3,
                    expires_at=iso_plus(deps.clock.now_iso(), 900)))
                async with asyncio.timeout(120):
                    while not control.status()["execution_ready"]:
                        assert not daemon_task.done()
                        await asyncio.sleep(.1)
                owner = control.execution.owner
                scope = None
                approved = set()
                entry = None
                async def decisions():
                    if adapter == "pi_rpc" or scope is None:
                        return
                    response = await http.get("/api/v1/approvals", headers=headers["operator"],
                        params={"workspace": scope["workspace_id"], "status": "pending"})
                    assert response.status_code == 200, response.text
                    for item in response.json()["data"]["items"]:
                        if item["action"] != "execution.native.respond" or item["approval_id"] in approved:
                            continue
                        detail = await http.get("/api/v1/approvals/" + item["approval_id"], headers=headers["operator"])
                        assert detail.status_code == 200, detail.text
                        proposal = detail.json()["data"]["request_payload"]["kwargs"]
                        key = proposal["approval_key"]
                        assert all(key[k] == scope[k] for k in ("server_id", "executor_id", "binding_id", "agent_id",
                                                              "workspace_id", "session_id", "session_owner_generation"))
                        params = proposal["display"]["params"]
                        tools = ("handoff_get", "handoff_claim", "handoff_complete")
                        if adapter == "codex_app_server":
                            assert key["kind"] == "native_input"
                            assert proposal["display"]["method"] == "mcpServer/elicitation/request"
                            assert params["mode"] == "form" and params["serverName"] == entry
                            assert params["requestedSchema"] == {"type": "object", "properties": {}}
                            assert params["_meta"]["codex_approval_kind"] == "mcp_tool_call"
                            assert params["message"] in {f'Allow the {entry} MCP server to run tool "{name}"?' for name in tools}
                            arguments = params["_meta"]["tool_params"]
                        else:
                            assert key["kind"] == "native_approval"
                            assert params["tool_name"] in {"mcp__" + entry + "__" + name for name in tools}
                            arguments = params["input"]
                        assert arguments["project_root"] == scope["workspace_id"]
                        assert arguments["agent_id"] == "subject" and arguments["handoff_id"] == "work"
                        body = {k: proposal[k] for k in ("approval_key", "expected_revision", "request_hash", "cas_token")}
                        body.update(client_intent_id="decision-" + item["approval_id"], decision="approve")
                        if adapter == "codex_app_server":
                            body["response"] = {"content": {}}
                        await post("/v1/runtime/approval-decisions", body)
                        approved.add(item["approval_id"])
                async def receipt(intent_id, stages):
                    async with asyncio.timeout(240):
                        while True:
                            await decisions()
                            if scope is not None:
                                with deps.connection_factory.unit_of_work(write=False) as uow:
                                    failures = uow.connection.execute(
                                        "SELECT COUNT(*) FROM execution_event_ingress WHERE session_id=? "
                                        "AND event_type='error' AND json_extract(payload_json,'$.native_type')='core.event_pump_failed'",
                                        (scope["session_id"],)).fetchone()[0]
                                assert failures == 0, "Native event observation failed."
                            view = await cli("runtime", "operation", "--alias", "assistant", "--client-intent-id", intent_id)
                            operation = view.get("operation") or {}
                            stage = operation.get("executor_stage")
                            if missing_login and stages == ("FAILED",):
                                assert stage != "SUCCEEDED", "An empty approved provider home unexpectedly authenticated."
                            if missing_login and stage == "FAILED" and stage in stages:
                                return operation
                            assert operation.get("error") is None, operation
                            assert stage not in ("FAILED", "REJECTED", "OUTCOME_UNKNOWN"), operation
                            assert owner.failure is None, type(owner.failure).__name__
                            if stage in stages:
                                return operation
                            await asyncio.sleep(.2)
                opened = await cli("runtime", "start", "assistant", "--new-session", "--client-intent-id", "open")
                assert opened["state"] == "ADMITTED", opened
                report["open_stage"] = (await receipt("open", ("SUBMITTED", "SUCCEEDED")))["executor_stage"]
                saved = next(r for r in store.load().runtime_intents if r.client_intent_id == "open")
                scope = saved.resolution["scope"]
                session = scope["session_id"]
                report["scope"] = scope
                if missing_login:
                    prompt = "Do not call tools. Reply with OK."
                    await cli("runtime", "submit", session, prompt, "--alias", "assistant",
                              "--client-intent-id", "missing-login")
                    failed = await receipt("missing-login", ("FAILED",))
                    error = failed["error"]
                    assert error["code"] == "PROVIDER_AUTH_REQUIRED", error
                    assert error["possible_effect"] is True and error["retry_safe"] is False
                    assert scope["executor_id"] in error["action"] and scope["binding_id"] in error["action"]
                    assert "Complete provider sign-in locally" in error["action"]
                    assert error["action"].startswith("Query this operation and reconcile")
                    response = await http.get("/v1/runtime/operations/" + failed["operation_id"],
                                              headers=headers["subject"])
                    assert response.status_code == 200
                    assert response.json()["error"] == error
                    await cli("runtime", "submit", session, prompt, "--alias", "assistant",
                              "--client-intent-id", "missing-login")
                    replay = await receipt("missing-login", ("FAILED",))
                    assert replay["operation_id"] == failed["operation_id"]
                    assert replay["error"] == error
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        assert uow.connection.execute(
                            "SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 1
                    report["authentication_error"] = error
                    report["replayed_operation_id"] = replay["operation_id"]
                    report["single_admitted_turn"] = True
                    await cli("runtime", "stop", session, "--alias", "assistant", "--client-intent-id", "close")
                    report["close_stage"] = (await receipt("close", ("SUCCEEDED",)))["executor_stage"]
                    report["completed"] = True
                    return
                seed_work((deps,), workspace=scope["workspace_id"])
                async with asyncio.timeout(120):
                    while True:
                        with deps.connection_factory.unit_of_work(write=False) as uow:
                            serial = uow.connection.execute("SELECT MAX(lease_serial) FROM execution_leases WHERE status='ACTIVE'").fetchone()[0]
                        if serial is not None and serial >= 2:
                            break
                        assert owner.failure is None, type(owner.failure).__name__
                        await asyncio.sleep(.2)
                report["lease_serial_before_turn"] = serial
                if adapter == "pi_rpc":
                    prompt = ('Use only the Nexus native tools. Call nexus_handoff_get for handoff_id work, '
                        'then nexus_handoff_claim for work with idempotency_key real-connector-work, then '
                        'nexus_handoff_complete for work with the returned claim_epoch and result '
                        '{"summary":"Reviewed by real Pi."}. Do not use filesystem or shell tools. Finish with OK.')
                else:
                    cap = next(r for r in store.load().session_capabilities
                               if r.session_id == session and r.audience == "nexus-mcp-session")
                    entry = "nexus_" + hashlib.sha256(cap.capability_ref.encode()).hexdigest()[:16]
                    prompt = (f'Use only the MCP server {entry}. Call handoff_get for handoff_id work, then '
                        'handoff_claim for work, then handoff_complete for work with the returned claim_epoch '
                        'and result string "Reviewed by real provider.". '
                        f'For these calls use project_root "{scope["workspace_id"]}" and agent_id "subject". '
                        'Do not use filesystem, shell or other MCP servers. Finish with OK.')
                submitted = await cli("runtime", "submit", session, prompt, "--alias", "assistant",
                                      "--client-intent-id", "work")
                assert submitted["state"] == "ADMITTED", submitted
                report["turn_stage"] = (await receipt("work", ("SUCCEEDED",)))["executor_stage"]
                report["explicit_operator_decisions"] = len(approved)
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    report["handoff_status"] = uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id='work'").fetchone()[0]
                    report["native_action_count"] = uow.connection.execute("SELECT COUNT(*) FROM execution_native_actions").fetchone()[0]
                    report["tool_claim_count"] = uow.connection.execute("SELECT COUNT(*) FROM execution_tool_claims").fetchone()[0]
                    report["wss_ticket_count"] = uow.connection.execute("SELECT COUNT(*) FROM execution_link_tickets").fetchone()[0]
                assert report["handoff_status"] == "COMPLETED", report
                assert report["wss_ticket_count"] > 0, report
                assert report["native_action_count"] >= 3 if adapter == "pi_rpc" else report["tool_claim_count"] >= 1
                await cli("runtime", "stop", session, "--alias", "assistant", "--client-intent-id", "close")
                report["close_stage"] = (await receipt("close", ("SUCCEEDED",)))["executor_stage"]
                if os.environ.get("OKTO_NEXUS_REAL_REBIND") == "1":
                    replacement_root = tmp_path / "replacement-workspace"
                    replacement_root.mkdir()
                    current_inventory = await cli("discover", "--server-id", server_id)
                    current_row = next(r for r in current_inventory["availability"]["rows"]
                        if r["adapter_id"] == adapter and r["candidate_ref"] == row["candidate_ref"])
                    replacement = await cli("executor", "realize", "--identity", "subject",
                        "--client-intent-id", "replacement-realize", "--harness", adapter,
                        "--candidate-ref", current_row["candidate_ref"],
                        "--inventory-revision", current_inventory["availability"]["executor_revision"],
                        "--configuration-digest", config["configuration_digest"], "--project", str(replacement_root),
                        "--workspace-id", binding["workspace_id"], "--label", "Replacement Connector work")
                    proposed = (await cli("bind", "prepare", "--identity", "subject",
                        "--realization-ref", replacement["realization_ref"], "--alias", "assistant",
                        "--client-intent-id", "replacement-prepare",
                        "--replace-binding-id", binding["binding_id"]))["proposal"]
                    replacement_proof = next(r for r in proposed["required_approvals"] if r.startswith("apr_"))
                    await post("/api/v1/approvals/" + replacement_proof + "/decision", {"decision": "approve"})
                    rebound = (await cli("bind", "apply", "--identity", "subject",
                        "--prepare-intent-id", "replacement-prepare", "--client-intent-id", "replacement-apply",
                        "--approved-diff-hash", proposed["approved_diff_hash"],
                        "--operator-proof-ref", replacement_proof))["binding"]
                    assert rebound["binding_id"] == binding["binding_id"]
                    assert rebound["endpoint_id"] == binding["endpoint_id"]
                    assert rebound["binding_revision"] == binding["binding_revision"] + 1
                    assert rebound["realization_ref"] == replacement["realization_ref"] != binding["realization_ref"]
                    checkpoint("waiting_for_replacement_readiness")
                    async with asyncio.timeout(120):
                        while True:
                            control = daemon.r4_controls.get(server_id)
                            execution = control.execution if control else None
                            lane = execution.lanes.get(binding["binding_id"]) if execution else None
                            if (control and control.status()["execution_ready"] and lane
                                    and lane.binding.binding_revision == rebound["binding_revision"]):
                                break
                            assert not daemon_task.done(), "The Connector exited during replacement reconciliation."
                            await asyncio.sleep(.1)
                    previous_scope = scope
                    reopened = await cli("runtime", "start", "assistant", "--new-session",
                                         "--client-intent-id", "replacement-open")
                    assert reopened["state"] == "ADMITTED", reopened
                    saved = next(r for r in store.load().runtime_intents if r.client_intent_id == "replacement-open")
                    scope = saved.resolution["scope"]
                    assert scope["session_id"] != session
                    assert scope["workspace_binding_id"] != previous_scope["workspace_binding_id"]
                    owner = control.execution.owner
                    report["replacement_open_stage"] = (await receipt("replacement-open", ("SUBMITTED", "SUCCEEDED")))["executor_stage"]
                    current_local = next(r for r in store.load().realizations if r.realization_ref == rebound["realization_ref"])
                    assert Path(current_local.workspace_root) == replacement_root
                    report["replacement_workspace_selected"] = True
                    report["replacement_scope"] = scope
                    await cli("runtime", "submit", scope["session_id"], "Do not call tools. Reply with OK.",
                              "--alias", "assistant", "--client-intent-id", "replacement-turn")
                    report["replacement_turn_stage"] = (await receipt("replacement-turn", ("SUCCEEDED",)))["executor_stage"]
                    await cli("runtime", "stop", scope["session_id"], "--alias", "assistant",
                              "--client-intent-id", "replacement-close")
                    report["replacement_close_stage"] = (await receipt("replacement-close", ("SUCCEEDED",)))["executor_stage"]
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        states = uow.connection.execute("SELECT session_id,lifecycle_state FROM execution_sessions").fetchall()
                        assert {r["session_id"]: r["lifecycle_state"] for r in states} == {
                            session: "CLOSED", scope["session_id"]: "CLOSED"}
                        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='runtime.open'").fetchone()[0] == 2
                    report["replacement_completed"] = True
                report["completed"] = True
            except BaseException as error:
                import traceback
                report["failure_type"] = type(error).__name__
                report["failure_phase"] = report.get("phase")
                report["failure_frames"] = [
                    dict(file=Path(frame.filename).name, function=frame.name, line=frame.lineno)
                    for frame in traceback.extract_tb(error.__traceback__)]
                if daemon is not None:
                    report["control_failures"] = [c.status() for c in daemon.r4_controls.values()]
                checkpoint("failed")
                raise
            finally:
                try:
                    try:
                        if daemon_task is not None:
                            daemon.request_stop()
                            report["daemon_exit_code"] = await asyncio.wait_for(daemon_task, 60)
                            if report.get("completed"):
                                assert report["daemon_exit_code"] == 0
                                assert not daemon.r4_controls and not daemon.r4_executions
                    finally:
                        from okto_nexus_connector.errors import ConnectorError
                        state = store.load()
                        handles = {r.secret_handle for r in (*state.identities, *state.session_capabilities) if r.secret_handle}
                        if handles:
                            vault = daemon.vault if daemon is not None else _vault(root, store)
                            for handle in handles:
                                vault.remove(namespace_of(handle))
                                with pytest.raises(ConnectorError):
                                    vault.resolve(handle)
                            report["campaign_credentials_removed"] = True
                finally:
                    try:
                        if server.returncode is None:
                            try:
                                server.stdin.write(b"stop\n")
                                await server.stdin.drain()
                            except (BrokenPipeError, ConnectionResetError):
                                pass
                            try:
                                await asyncio.wait_for(server.wait(), 45)
                            except TimeoutError:
                                server.kill()
                                await server.wait()
                                report["server_forced_stop"] = True
                                raise
                        report["server_exit_code"] = server.returncode
                        if report.get("completed"):
                            assert server.returncode == 0
                    finally:
                        destination = os.environ.get("OKTO_NEXUS_REAL_CONNECTOR_REPORT")
                        if destination:
                            checkpoint("finished")
                            Path(destination + "-" + adapter + ".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    asyncio.run(run())
