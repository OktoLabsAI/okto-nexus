"""Real serve process retains HTTP while signal-triggered cleanup is pending."""
import asyncio
import os
from pathlib import Path
import socket
import site
import subprocess
import sys
import time
from types import SimpleNamespace

import httpx
import pytest
import okto_nexus
import uvicorn

from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.adapters.inbound.http.app import ensure_operator_key
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.adapters.inbound.cli.runtime_server import RuntimeServer


LAUNCHER = '''
import sys, threading, signal
from pathlib import Path
from types import SimpleNamespace
# dependency_paths
sys.path.insert(0, sys.argv[1])
from okto_nexus.bootstrap import embedded_inventory
from okto_nexus.adapters.inbound.cli.runtime_server import RuntimeServer
from okto_nexus.adapters.inbound.cli.serve import run_serve
root = Path(sys.argv[2])
embedded_inventory.discover_local_candidates = lambda **kwargs: SimpleNamespace(candidates=())
original_release = embedded_inventory.EmbeddedInventoryOwner._release
def release(self):
    if not (root / 'restore').exists():
        raise OSError('Technical inventory release unavailable')
    return original_release(self)
embedded_inventory.EmbeddedInventoryOwner._release = release
original_signal = RuntimeServer.handle_exit
seen = []
def observed_signal(self, sig, frame):
    original_signal(self, sig, frame)
    seen.append(sig)
    (root / 'signals.json').write_text(str(len(seen)))
RuntimeServer.handle_exit = observed_signal
def control():
    for line in sys.stdin:
        name = line.strip()
        if name in ('SIGINT', 'SIGTERM'):
            signal.raise_signal(getattr(signal, name))
threading.Thread(target=control, daemon=True).start()
raise SystemExit(run_serve(sys.argv[3:]))
'''


@pytest.mark.parametrize("signal_name", ["SIGINT", "SIGTERM"])
@pytest.mark.parametrize("first_request", ["signal", "http"])
def test_signal_keeps_serve_process_and_http_until_inventory_release(tmp_path, signal_name, first_request):
    home = tmp_path / "home"
    deps = bootstrap({}, ["--home", str(home)])
    _, key = ensure_operator_key(deps, AgentKeyAuthService(deps.repos.agents, deps.clock))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    launcher = tmp_path / "serve.py"
    # -I and the disposable USERPROFILE must isolate state, while retaining the
    # dependencies installed for the interpreter running this test (including
    # Windows --user installations). Source selection remains first on sys.path.
    dependency_paths = site.getsitepackages() + [site.getusersitepackages()]
    launcher.write_text(LAUNCHER.replace('# dependency_paths',
        f'sys.path.extend({dependency_paths!r})'), encoding="utf-8")
    env = {k:v for k,v in os.environ.items() if k.upper() in {
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
    env.update(HOME=str(home), USERPROFILE=str(home), PYTHONIOENCODING="utf-8",
               OKTO_NEXUS_NO_BANNER="1")
    log_path = tmp_path / "server.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-I", str(launcher),
            str(Path(okto_nexus.__file__).resolve().parent.parent), str(tmp_path),
            "--home", str(home), "--host", "127.0.0.1", "--port", str(port),
            "--feature-harness-integrations", "true", "--embedding-mode", "off"],
            cwd=tmp_path, env=env, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
            text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        def wait_for(predicate):
            until = time.monotonic() + 15
            while not predicate():
                assert process.poll() is None, log_path.read_text(encoding="utf-8")
                assert time.monotonic() < until, log_path.read_text(encoding="utf-8")
                time.sleep(.02)
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False,
                              headers={"Authorization": "Bearer " + key}, timeout=2) as client:
                def healthy():
                    try:
                        return client.get("/healthz").status_code == 200
                    except httpx.HTTPError:
                        return False
                wait_for(healthy)
                initial = None
                if first_request == "http":
                    response = client.post("/v1/runtime/shutdown", json={"timeout_seconds": .1})
                    assert response.status_code == 202, response.text
                    initial = response.json()
                process.stdin.write(signal_name + "\n")
                process.stdin.flush()
                wait_for(lambda: client.get("/v1/runtime/shutdown").json()["state"] == "DRAINING_PENDING")
                report = client.get("/v1/runtime/shutdown").json()
                if initial is not None:
                    assert report["deadline_monotonic"] == initial["deadline_monotonic"]
                # A second signal must not invoke Uvicorn's force-exit path.
                process.stdin.write(signal_name + "\n")
                process.stdin.flush()
                marker = tmp_path / "signals.json"
                def observed_twice():
                    try:
                        return marker.read_text() == "2"
                    except OSError:
                        return False
                wait_for(observed_twice)
                assert healthy() and process.poll() is None
                repeated = client.get("/v1/runtime/shutdown").json()
                assert repeated["state"] == "DRAINING_PENDING"
                assert repeated["deadline_monotonic"] == report["deadline_monotonic"]
                (tmp_path / "restore").touch()
                assert process.wait(timeout=15) == 0, log_path.read_text(encoding="utf-8")
        finally:
            (tmp_path / "restore").touch()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            process.stdin.close()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute("SELECT control_state FROM execution_executors WHERE kind='embedded'").fetchall()
        assert len(rows) == 1 and rows[0][0] == "DISCONNECTED"


@pytest.mark.parametrize("startup_fails", [False, True])
def test_signal_during_startup_waits_for_owner_without_hanging_failed_startup(monkeypatch, startup_fails):
    async def scenario():
        app = SimpleNamespace(state=SimpleNamespace())
        server = RuntimeServer(uvicorn.Config(app))
        calls = []
        class Owner:
            async def request(self):
                calls.append("request")
                return {"state": "DRAINING_PENDING"}
            async def wait(self):
                calls.append("wait")
                server.should_exit = True
        async def startup(self, sockets=None):
            self.handle_exit(2, None)
            self.handle_exit(2, None)
            await asyncio.sleep(.03)
            assert not self.should_exit and not self.force_exit
            if startup_fails:
                raise RuntimeError("Technical startup failure")
            app.state.runtime_shutdown = Owner()
            while not self.should_exit:
                await asyncio.sleep(.01)
        monkeypatch.setattr(uvicorn.Server, "serve", startup)
        if startup_fails:
            with pytest.raises(RuntimeError, match="Technical startup failure"):
                await asyncio.wait_for(server.serve(), 2)
            assert calls == []
        else:
            await asyncio.wait_for(server.serve(), 2)
            assert calls == ["request", "wait"]
        assert server._signal_shutdown_task.done()
        assert not server.force_exit
    asyncio.run(scenario())
