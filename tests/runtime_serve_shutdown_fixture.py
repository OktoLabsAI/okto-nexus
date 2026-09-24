"""Real serve CLI and owned Pi protocol fixture; no models or ambient credentials."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

import httpx

from okto_nexus.adapters.inbound.http.app import ensure_operator_key
from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.application.auth import AgentKeyAuthService
from test_runtime_relay_process_restart import PeerWitness


PEER = '''import json,os,subprocess,sys,time
from pathlib import Path
child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(300)"])
Path(sys.argv[1]).write_text(json.dumps({"peer":os.getpid(),"child":child.pid,"parent":os.getppid()}),encoding="utf-8")
for line in sys.stdin:
    msg=json.loads(line)
    if msg.get("type"):
        print(json.dumps({"type":"response","command":msg["type"],"success":True,"data":{}}),flush=True)
# Deliberately ignore EOF: incidental pipe closure cannot satisfy the reap proof.
while True: time.sleep(300)
'''

LAUNCHER = '''import sys,threading,uvicorn
from okto_nexus.adapters.inbound.cli.serve import run_serve
from okto_nexus.adapters.inbound.mcp import server as mcp_server
from okto_nexus.adapters.outbound.harness.pi import PiRpcConnector
peer,marker=sys.argv[1:3]
original_bootstrap=mcp_server.bootstrap
def bootstrap(*args,**kwargs):
    deps=original_bootstrap(*args,**kwargs)
    deps.harness_connector_factories={"pi": lambda **options: PiRpcConnector(command=[sys._base_executable,"-u",peer,marker],env=options["backend"]["env"])}
    return deps
mcp_server.bootstrap=bootstrap
Original=uvicorn.Server
class ControlledServer(Original):
    def run(self,*args,**kwargs):
        def control():
            for line in sys.stdin:
                if line.strip()=="stop":
                    self.should_exit=True
                    return
        threading.Thread(target=control,daemon=True).start()
        return super().run(*args,**kwargs)
uvicorn.Server=ControlledServer
raise SystemExit(run_serve(sys.argv[3:]))
'''


class ServeFixture:
    def __init__(self, root):
        self.root = root
        self.home = root / "home"
        self.home.mkdir()
        self.project = root / "project"
        self.project.mkdir()
        self.process = self.client = self.log = None
        self.witnesses = []
        deps = bootstrap({}, ["--home", str(self.home)])
        auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
        _, self.operator = ensure_operator_key(deps, auth)
        with deps.connection_factory.unit_of_work() as uow:
            deps.repos.agents.upsert(uow, agent_id="shutdown-fixture")
        self.peer = root / "peer.py"
        self.peer.write_text(PEER, encoding="utf-8")
        self.marker = root / "process-identities.json"
        launcher = root / "serve.py"
        launcher.write_text(LAUNCHER, encoding="utf-8")
        repo = Path(__file__).resolve().parents[1]
        env = {k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
        env.update(HOME=str(self.home), USERPROFILE=str(self.home), PYTHONPATH=str(repo / "src"),
                   PYTHONIOENCODING="utf-8", OKTO_NEXUS_NO_BANNER="1")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.log_path = root / "serve.log"
        self.log = self.log_path.open("w", encoding="utf-8")
        try:
            self.process = subprocess.Popen([sys.executable, str(launcher), str(self.peer), str(self.marker), "--home", str(self.home),
                "--host", "127.0.0.1", "--port", str(port), "--feature-harness-integrations", "true"],
                cwd=self.project, env=env, stdin=subprocess.PIPE, stdout=self.log,
                stderr=subprocess.STDOUT, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            self.client = httpx.Client(base_url=f"http://127.0.0.1:{port}",
                                      headers={"x-api-key": self.operator}, timeout=15)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                assert self.process.poll() is None, self.log_path.read_text(encoding="utf-8")
                try:
                    if self.client.get("/api/v1/info").status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(.05)
            raise AssertionError("Disposable serve did not become ready")
        except BaseException:
            self.close()
            raise

    def open(self):
        response = self.client.post("/api/v1/harness/profiles", json={"profile_id": "shutdown",
            "adapter_id": "pi", "enabled": True, "inherit_ambient": False,
            "config": {}})
        assert response.status_code == 200, response.text
        response = self.client.post("/api/v1/harness/endpoints", json={"endpoint_id": "shutdown",
            "agent_id": "shutdown-fixture", "adapter_id": "pi", "profile_id": "shutdown",
            "project_root": str(self.project), "enabled": True})
        assert response.status_code == 200, response.text
        response = self.client.post("/api/v1/harness/sessions", json={"agent_id": "shutdown-fixture",
            "kind": "pi", "endpoint_id": "shutdown", "project_root": str(self.project)})
        assert response.status_code == 200, response.text
        identities = json.loads(self.marker.read_text(encoding="utf-8"))
        # Hold exact live process instances before triggering any shutdown.
        for name in ("peer", "child"):
            self.witnesses.append(PeerWitness(identities[name]))
        if sys.platform == "linux":
            assert identities["parent"] != self.process.pid  # owned guardian
            self.witnesses.append(PeerWitness(identities["parent"]))
        self.session_id = response.json()["data"]["session_id"]
        return self.session_id

    def stop(self, mode):
        if mode == "kill":
            self.process.kill()  # only this owned Popen; never a process-group scan
        elif mode == "clean":
            self.process.stdin.write("stop\n")
            self.process.stdin.flush()
        else:
            assert os.name == "posix"
            self.process.send_signal(signal.SIGTERM if mode == "term" else signal.SIGINT)
        self.process.wait(timeout=20)
        for witness in self.witnesses:
            witness.assert_stopped()

    def close(self):
        if self.client:
            self.client.close()
        if self.process:
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=10)
            self.process.stdin.close()
        for witness in self.witnesses:
            witness.close()
        if self.log:
            self.log.close()
