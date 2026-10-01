"""Connector public onboarding commands against the real Nexus HTTP routes."""
import asyncio
import io
import os
import shutil
import socket
import sys

import pytest
import uvicorn

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.bootstrap.dependencies import bootstrap


@pytest.mark.parametrize("bind_flow", [False, True])
def test_connector_public_commands_publish_realization_over_tcp(tmp_path, monkeypatch, bind_flow, replacement_flow=False):
    from okto_nexus_connector.daemon import app as daemon_module
    from okto_nexus_connector.cli.main import build_parser
    from okto_nexus_connector.cli.output import Output
    from okto_nexus_connector.cli.commands.bind import run_bind
    from okto_nexus_connector.cli.commands import identity as identity_cli
    from okto_nexus_connector.cli.commands.executor import run_executor
    from okto_nexus_connector.cli.commands.discover import run_discover
    from okto_nexus_connector.cli.commands import executor as executor_cli
    from okto_nexus_connector.platform import paths
    from okto_nexus_connector.storage.state_store import ConnectorState, StateStore, IdentityRecord, ServerProfileRecord

    deps = bootstrap({}, ["--home", str(tmp_path / "nexus"), "--feature-harness-integrations", "true"])
    app = build_app(deps)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("INSERT OR IGNORE INTO agents(agent_id,created_at) VALUES (?,?)",
                               ("subject", deps.clock.now_iso()))
        key = app.state.auth.issue_key(uow, agent_id="subject")
        uow.connection.execute("INSERT OR IGNORE INTO agents(agent_id,created_at) VALUES (?,?)",
                               ("operator", deps.clock.now_iso()))
        operator_key = app.state.auth.issue_key(uow, agent_id="operator")
        server_id = uow.connection.execute("SELECT server_id FROM execution_installation").fetchone()[0]
    binary_root = tmp_path / "binaries"
    binary_root.mkdir()
    binary = binary_root / ("codex.exe" if os.name == "nt" else "codex")
    shutil.copy2(sys.executable, binary)
    monkeypatch.setenv("PATH", str(binary_root))
    project = tmp_path / "project"
    project.mkdir()
    root = tmp_path / "connector"
    store = StateStore(paths.state_file(root))
    parser, output = build_parser(), Output(json_mode=True, stream=io.StringIO())
    class Vault:
        def resolve(self, handle):
            assert handle == "vault:identity"
            return key
    monkeypatch.setattr(executor_cli, "_vault", lambda *args: Vault())
    monkeypatch.setattr(identity_cli, "_vault", lambda *args: Vault())
    monkeypatch.setattr(daemon_module, "open_vault", lambda *args, **kwargs: Vault())

    async def run():
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        base = "http://127.0.0.1:" + str(sock.getsockname()[1])
        state = ConnectorState(connector_id="onboarding-connector")
        state.servers[server_id] = ServerProfileRecord(server_id, base, base, "now")
        state.identities.append(IdentityRecord("subject", server_id, "subject", "vault:identity", 1, "now"))
        store.save(state)
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on"))
        serving = asyncio.create_task(server.serve(sockets=[sock]))
        daemon = daemon_task = None
        try:
            async with asyncio.timeout(15):
                while not server.started:
                    assert not serving.done()
                    await asyncio.sleep(.01)
            async def execute(words):
                return await run_executor(parser.parse_args(["executor", *words]), output, root)
            registered = await execute(["register", "--identity", "subject", "--label", "Test executor",
                                        "--client-intent-id", "register"])
            await execute(["configure-discovery", "--server-id", server_id, "--harness-root", str(binary_root)])
            daemon = daemon_module.DaemonApp(root)
            daemon_task = asyncio.create_task(daemon.run_forever())
            async with asyncio.timeout(15):
                while True:
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        published = uow.connection.execute("SELECT 1 FROM execution_inventory_current WHERE executor_id=?",
                                                          (registered["executor_id"],)).fetchone()
                    if published: break
                    assert not daemon_task.done()
                    await asyncio.sleep(.02)
            inventory = await run_discover(parser.parse_args(["discover", "--server-id", server_id]), output, root)
            row = next(r for r in inventory["availability"]["rows"]
                       if r["adapter_id"] == "codex_app_server" and r["candidate_ref"])
            configuration = await execute(["configure-launch", "--identity", "subject",
                "--harness", "codex_app_server", "--local-consent-id", "explicit-test-consent",
                "--profile-revision", "1"])
            words = ["realize", "--identity", "subject", "--client-intent-id", "realize",
                "--harness", "codex_app_server", "--candidate-ref", row["candidate_ref"],
                "--inventory-revision", inventory["availability"]["executor_revision"],
                "--configuration-digest", configuration["configuration_digest"],
                "--project", str(project), "--label", "Test project"]
            result = await execute(words)
            assert await execute(words) == result
            local = store.load()
            assert len(local.realizations) == 1 and local.realizations[0].status == "PENDING_APPROVAL"
            assert local.realizations[0].executor_id == registered["executor_id"]
            assert not local.execution_bindings
            import httpx
            from okto_nexus_connector.services.realization_service import publication_body
            from okto_nexus_connector.transport.https_client import MANAGEMENT_REVISION
            async with httpx.AsyncClient() as http:
                denied = await http.post(base + "/v1/runtime/executors/" + registered["executor_id"] + "/realizations",
                    json=publication_body(local.realizations[0]),
                    headers={"Authorization": "Bearer nxt4_" + "x" * 48})
            assert denied.status_code == 403, denied.text
            assert denied.headers["X-Nexus-Connections-Revision"] == MANAGEMENT_REVISION
            assert denied.json()["error"]["code"] == "PERMISSION_DENIED"
            if bind_flow:
                from okto_nexus_connector.errors import ConnectorError
                async def bind(words):
                    return await run_bind(parser.parse_args(["bind", *words]), output, root)
                draft = await bind(["prepare", "--identity", "subject", "--realization-ref", result["realization_ref"],
                                   "--alias", "assistant", "--client-intent-id", "prepare-binding"])
                proposal = draft["proposal"]
                proof = next(ref for ref in proposal["required_approvals"] if ref.startswith("apr_"))
                apply_words = ["apply", "--identity", "subject", "--prepare-intent-id", "prepare-binding",
                    "--client-intent-id", "apply-binding", "--approved-diff-hash", proposal["approved_diff_hash"],
                    "--operator-proof-ref", proof]
                with pytest.raises(ConnectorError) as pending:
                    await bind(apply_words)
                assert pending.value.code == "PERMISSION_DENIED"
                assert not store.load().execution_bindings
                async with httpx.AsyncClient() as http:
                    decision = await http.post(base + "/api/v1/approvals/" + proof + "/decision",
                        json={"decision": "approve"}, headers={"Authorization": "Bearer " + operator_key})
                assert decision.status_code == 200, decision.text
                bound = await bind(apply_words)
                assert bound["state"] == "APPLIED"
                assert await bind(apply_words) == bound
                assert await bind(["show", "assistant"]) == bound
                assert (await bind(["list"]))["execution_bindings"] == [bound]
                local = store.load()
                assert len(local.execution_bindings) == 1 and not local.bindings
                assert local.realizations[0].status == "BOUND"
                if replacement_flow:
                    replacement_project = tmp_path / "replacement-project"
                    replacement_project.mkdir()
                    replacement_words = list(words)
                    replacement_words[replacement_words.index("--client-intent-id") + 1] = "realize-replacement"
                    replacement_words[replacement_words.index("--project") + 1] = str(replacement_project)
                    replacement_words += ["--workspace-id", bound["binding"]["workspace_id"]]
                    replacement = await execute(replacement_words)
                    draft = await bind(["prepare", "--identity", "subject", "--realization-ref", replacement["realization_ref"],
                        "--alias", "assistant", "--client-intent-id", "prepare-replacement",
                        "--replace-binding-id", bound["binding"]["binding_id"]])
                    proposal = draft["proposal"]
                    assert "Replace binding" in proposal["summary"]
                    proof = next(ref for ref in proposal["required_approvals"] if ref.startswith("apr_"))
                    async with httpx.AsyncClient() as http:
                        decision = await http.post(base + "/api/v1/approvals/" + proof + "/decision",
                            json={"decision": "approve"}, headers={"Authorization": "Bearer " + operator_key})
                    assert decision.status_code == 200, decision.text
                    replaced = await bind(["apply", "--identity", "subject", "--prepare-intent-id", "prepare-replacement",
                        "--client-intent-id", "apply-replacement", "--approved-diff-hash", proposal["approved_diff_hash"],
                        "--operator-proof-ref", proof])
                    assert replaced["binding"]["binding_id"] == bound["binding"]["binding_id"]
                    assert replaced["binding"]["binding_revision"] == bound["binding"]["binding_revision"] + 1
                    assert replaced["binding"]["realization_ref"] == replacement["realization_ref"]
                    assert (await bind(apply_words))["binding"] == bound["binding"]
                    assert await bind(["show", "assistant"]) == replaced
                    assert (await bind(["list"]))["execution_bindings"] == [replaced]
                    assert len(store.load().execution_bindings) == 1
                from okto_nexus_connector.cli.commands.runtime import run_runtime
                runtime_args = parser.parse_args(["runtime", "start", "assistant", "--new-session",
                                                  "--client-intent-id", "open-runtime"])
                reserved = await run_runtime(runtime_args, output, root)
                assert reserved["state"] == "RESOLVED" and reserved["blockers"]
                assert await run_runtime(runtime_args, output, root) == reserved
                query_args = parser.parse_args(["runtime", "operation", "--alias", "assistant",
                                                "--client-intent-id", "open-runtime"])
                observed = await run_runtime(query_args, output, root)
                assert observed["operation_id"] == reserved["operation_id"]
                assert observed["operation_found"] is False
                assert len(store.load().runtime_intents) == 1
                import json
                import subprocess
                for command in (["show", "assistant"], ["list"]):
                    process = await asyncio.to_thread(subprocess.run,
                        [sys.executable, "-I", "-m", "okto_nexus_connector.cli.main", "--json",
                         "--state-dir", str(root), "bind", *command],
                        capture_output=True, text=True, encoding="utf-8", timeout=30)
                    assert process.returncode == 0, process.stderr
                    payload = json.loads(process.stdout)
                    assert payload["state"] == "APPLIED" if command[0] == "show" else len(payload["execution_bindings"]) == 1
            assert key not in store.path.read_text() and "nxt4_" not in store.path.read_text()
            assert str(project) not in str(result) and str(binary) not in str(result)
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute("SELECT COUNT(*) FROM execution_realizations").fetchone()[0] == 1 + int(replacement_flow)
                assert uow.connection.execute("SELECT COUNT(*) FROM execution_bindings").fetchone()[0] == int(bind_flow)
                assert uow.connection.execute("SELECT COUNT(*) FROM execution_sessions").fetchone()[0] == 0
                assert uow.connection.execute("SELECT COUNT(*) FROM execution_dispatch_outbox").fetchone()[0] == 0
        finally:
            if daemon is not None:
                daemon.request_stop()
                await asyncio.wait_for(daemon_task, 15)
            server.should_exit = True
            await asyncio.wait_for(serving, 15)
            sock.close()
    asyncio.run(run())


def test_connector_public_replacement_commands_preserve_binding_identity(tmp_path, monkeypatch):
    test_connector_public_commands_publish_realization_over_tcp(tmp_path, monkeypatch, True, replacement_flow=True)
