"""Opt-in real providers through public Connector onboarding and runtime CLI."""
import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import time

import httpx
import pytest
import uvicorn

from nexus_connector_core import R4_PREVIEW_REVISION
from okto_nexus.adapters.inbound.http import connections_v1, executor_link, runtime_v1
from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.domain.base import iso_plus
from test_mcp_session_capabilities import seed_work


@pytest.mark.skipif(os.environ.get("OKTO_NEXUS_REAL_CONNECTOR") != "1",
                    reason="The real Connector provider campaign is opt-in.")
@pytest.mark.parametrize("adapter", ["pi_rpc", "codex_app_server", "claude_stream"])
def test_real_provider_through_public_connector_cli(tmp_path, monkeypatch, adapter):
    from okto_nexus_connector.cli.main import build_parser
    from okto_nexus_connector.cli.output import Output
    from okto_nexus_connector.cli.commands.identity import run_identity, _vault
    from okto_nexus_connector.cli.commands.executor import run_executor
    from okto_nexus_connector.cli.commands.discover import run_discover
    from okto_nexus_connector.cli.commands.bind import run_bind
    from okto_nexus_connector.cli.commands.runtime import run_runtime
    from okto_nexus_connector.daemon.app import DaemonApp
    from okto_nexus_connector.identity.vault import KeyringVault, namespace_of
    from okto_nexus_connector.platform import paths
    from okto_nexus_connector.storage.state_store import StateStore

    user_home = Path.home()
    codex = user_home / "AppData/Roaming/npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe"
    claude = user_home / ".local/bin/claude.exe"
    node = Path(os.environ.get("OKTO_NEXUS_REAL_PI_NODE", "C:/Program Files/nodejs/node.exe"))
    pi_install = Path(os.environ.get("OKTO_NEXUS_REAL_PI_HOME", str(user_home / ".pi/agent"))) / "install"
    binary = {"pi_rpc": node, "codex_app_server": codex, "claude_stream": claude}[adapter]
    assert binary.is_file(), "The selected real provider executable is missing."
    monkeypatch.setenv("PATH", str(binary.parent) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.delenv("OKTO_NEXUS_CONNECTOR_VAULT", raising=False)
    info = executor_link.protocol_info()
    qualified = {**info, "remote_execution_ready": True, "nxl_accepted": [R4_PREVIEW_REVISION]}
    for module in (executor_link, connections_v1, runtime_v1):
        monkeypatch.setattr(module, "protocol_info", lambda: qualified)
    deps = bootstrap({}, ["--home", str(tmp_path / "nexus"), "--feature-harness-integrations", "true",
                          "--feature-hitl", "true"])
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    origin = "http://127.0.0.1:" + str(listener.getsockname()[1])
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
    parser, output = build_parser(), Output(json_mode=True, stream=io.StringIO())
    report = dict(adapter=adapter, server_release_gate_override=True, native_qualification_override=False,
                  synthetic_native_factory=False, public_connector_cli=True, protected_os_vault=False,
                  topology="Single Windows host; actual loopback HTTP/WSS; Server and daemon owners.")
    def checkpoint(phase):
        report["phase"] = phase
        destination = os.environ.get("OKTO_NEXUS_REAL_CONNECTOR_REPORT")
        if destination:
            Path(destination + "-" + adapter + "-progress.json").write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8")

    async def run():
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False,
                                               timeout_graceful_shutdown=5))
        serving = asyncio.create_task(server.serve(sockets=[listener]))
        daemon = daemon_task = None
        async with httpx.AsyncClient(base_url=origin, timeout=30, trust_env=False) as http:
            async def cli(group, *words):
                args = parser.parse_args(["--non-interactive", group, *words])
                caller = {"identity": run_identity, "executor": run_executor, "discover": run_discover,
                          "bind": run_bind, "runtime": run_runtime}[group]
                checkpoint(group + "." + (words[0] if words else "preview"))
                result = await caller(args, output, root)
                checkpoint(group + ".returned")
                return result
            async def post(path, body):
                response = await http.post(path, headers=headers["operator"], json=body)
                assert response.status_code in (200, 201, 202), (response.status_code, response.text)
                return response.json()
            try:
                async with asyncio.timeout(120):
                    while not server.started:
                        if serving.done():
                            await serving
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
                async with asyncio.timeout(120):
                    while True:
                        control = daemon.r4_controls.get(server_id)
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
                    "--profile-revision", "1", "--provider-home", str(user_home))
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
                            view = await cli("runtime", "operation", "--alias", "assistant", "--client-intent-id", intent_id)
                            operation = view.get("operation") or {}
                            stage = operation.get("executor_stage")
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
                report["completed"] = True
            except BaseException as error:
                report["failure_type"] = type(error).__name__
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
                    server.should_exit = True
                    await asyncio.wait_for(serving, 45)
                    listener.close()
                    destination = os.environ.get("OKTO_NEXUS_REAL_CONNECTOR_REPORT")
                    if destination:
                        checkpoint("finished")
                        Path(destination + "-" + adapter + ".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    asyncio.run(run())
