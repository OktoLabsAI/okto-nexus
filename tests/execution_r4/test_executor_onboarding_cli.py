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


def test_connector_public_commands_publish_realization_over_tcp(tmp_path, monkeypatch):
    from okto_nexus_connector.daemon import app as daemon_module
    from okto_nexus_connector.cli.main import build_parser
    from okto_nexus_connector.cli.output import Output
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
            assert key not in store.path.read_text() and "nxt4_" not in store.path.read_text()
            assert str(project) not in str(result) and str(binary) not in str(result)
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute("SELECT COUNT(*) FROM execution_realizations").fetchone()[0] == 1
                assert uow.connection.execute("SELECT COUNT(*) FROM execution_bindings").fetchone()[0] == 0
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
