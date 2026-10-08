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
import okto_nexus

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
        print(json.dumps({"type":"response","command":msg["type"],"success":True,"data":{"sessionId":"shutdown-fixture"}}),flush=True)
# Deliberately ignore EOF: incidental pipe closure cannot satisfy the reap proof.
while True: time.sleep(300)
'''

LAUNCHER = '''import sys,threading,uvicorn,asyncio
from pathlib import Path
from types import SimpleNamespace
from okto_nexus.adapters.inbound.cli.serve import run_serve
from okto_nexus.bootstrap import embedded_inventory,embedded_dispatch
from nexus_connector_core import InstallationCandidate
from nexus_connector_core.discovery import fingerprint
from nexus_connector_core.native.adapters.pi import PiRpcConnector
from nexus_connector_core.native.runtime_bridge import CopiedAdapterSession
peer,marker=sys.argv[1:3]
candidate=InstallationCandidate("pi_rpc",peer,fingerprint(Path(peer)),"explicit","selected")
embedded_inventory.discover_local_candidates=lambda **_:SimpleNamespace(candidates=(candidate,))
original_init=embedded_dispatch.EmbeddedDispatchOwner.__init__
class Vault:
    def __init__(self): self.values={}
    def store(self,key,value): self.values[key]=value
    def remove(self,key): self.values.pop(key,None)
def initialize(self,*args,**kwargs):
    original_init(self,*args,**kwargs)
    owner=self
    class Factory:
        async def open(self,prepared,session_id,context,*,stream_epoch):
            environment=await owner.sessions[session_id]["executor"].environment(prepared)
            connector=PiRpcConnector(command=[sys._base_executable,"-u",peer,marker],cwd=prepared.cwd,env=environment)
            native=await asyncio.to_thread(connector.start,owning_agent_id=context.agent_id)
            return CopiedAdapterSession(connector,native,session_id=session_id,stream_epoch=stream_epoch,context=context)
    self.fixture_native_factory=Factory()
    self.tools.vault=Vault()
embedded_dispatch.EmbeddedDispatchOwner.__init__=initialize
original_start=embedded_dispatch.EmbeddedDispatchOwner.start
async def start(self):
    self.native_factory=self.fixture_native_factory
    return await original_start(self)
embedded_dispatch.EmbeddedDispatchOwner.start=start
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
        self.deps = deps
        auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
        _, self.operator = ensure_operator_key(deps, auth)
        with deps.connection_factory.unit_of_work() as uow:
            deps.repos.agents.upsert(uow, agent_id="shutdown-fixture")
            self.subject = auth.issue_key(uow, agent_id="shutdown-fixture")
        self.peer = root / "peer.py"
        self.peer.write_text(PEER, encoding="utf-8")
        self.marker = root / "process-identities.json"
        launcher = root / "serve.py"
        launcher.write_text(LAUNCHER, encoding="utf-8")
        # The generated launcher lives outside tests. Expose its injected
        # connector fixture while retaining the exact Server package under test.
        test_root = Path(__file__).resolve().parent
        package_root = Path(okto_nexus.__file__).resolve().parent.parent
        env = {k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
        env.update(HOME=str(self.home), USERPROFILE=str(self.home), PYTHONPATH=os.pathsep.join(map(str, (package_root, test_root))),
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
                                      headers={"Authorization": "Bearer " + self.operator}, timeout=15)
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

    def wait_operation(self, operation_id, stages=('SUBMITTED', 'SUCCEEDED')):
        deadline = time.monotonic() + 15
        while True:
            response = self.client.get('/v1/runtime/operations/' + operation_id,
                                       headers={'Authorization': "Bearer " + self.subject})
            assert response.status_code == 200, response.text
            view = response.json()
            if view.get('executor_stage') in stages:
                return view
            assert time.monotonic() < deadline, (view, self.log_path.read_text(encoding='utf-8')[-3000:])
            time.sleep(.02)

    def open(self, *, actions=('open', 'close')):
        from okto_nexus.domain.base import iso_plus
        with self.deps.connection_factory.unit_of_work(write=False) as uow:
            executor = uow.connection.execute("SELECT executor_id FROM execution_executors WHERE kind='embedded'").fetchone()[0]
        inventory = self.client.get('/v1/runtime/executors/' + executor + '/inventory')
        assert inventory.status_code == 200, inventory.text
        snapshot = inventory.json()['snapshot']
        candidate = snapshot['evidence'][0]['candidate_ref']
        response = self.client.post('/v1/runtime/executors/' + executor + '/realizations', json=dict(
            client_intent_id='shutdown-realization', agent_id='shutdown-fixture', workspace_root=str(self.project),
            workspace_id=None, workspace_label='Shutdown fixture', adapter_id='pi_rpc', candidate_ref=candidate,
            inventory_revision=snapshot['inventory_revision'], local_consent_id='shutdown-consent', approved=True,
            provider_home=None, secret_bindings={}))
        assert response.status_code == 201, response.text
        realization = response.json()
        response = self.client.post('/v1/connections/bindings:prepare', json=dict(
            client_intent_id='shutdown-binding', agent_id_hint='shutdown-fixture', executor_id=executor,
            adapter_id='pi_rpc', candidate_ref=candidate, inventory_revision=snapshot['inventory_revision'],
            realization_ref=realization['realization_ref'], workspace_id=realization['workspace_id'], alias='shutdown'))
        assert response.status_code == 200, response.text
        proposal = response.json()
        response = self.client.post('/v1/connections/bindings:apply', json=dict(client_intent_id='shutdown-apply',
            proposal_id=proposal['proposal_id'], proposal_revision=proposal['proposal_revision'],
            approved_diff_hash=proposal['diff']['approved_diff_hash']))
        assert response.status_code == 200, response.text
        self.binding = response.json()
        response = self.client.post('/api/v1/harness/grants', json=dict(actor_agent_id='shutdown-fixture',
            endpoint_id=self.binding['endpoint_id'], actions=list(actions), max_executions=3,
            expires_at=iso_plus(self.deps.clock.now_iso(), 600)))
        assert response.status_code == 200, response.text
        response = self.client.post('/api/v1/harness/sessions', headers={'Authorization': "Bearer " + self.subject}, json=dict(
            agent_id='shutdown-fixture', kind='pi', endpoint_id=self.binding['endpoint_id'],
            project_root=str(self.project), idempotency_key='shutdown-open'))
        assert response.status_code == 200, response.text
        opened = response.json()['data']
        self.wait_operation(opened['operation_id'])
        identities = json.loads(self.marker.read_text(encoding='utf-8'))
        for name in ('peer', 'child'):
            self.witnesses.append(PeerWitness(identities[name]))
        if sys.platform == 'linux':
            assert identities['parent'] != self.process.pid
            self.witnesses.append(PeerWitness(identities['parent']))
        self.session_id = opened['scope']['session_id']
        return self.session_id

    def close_session(self):
        response = self.client.post('/api/v1/harness/sessions/' + self.session_id + '/close',
            headers={'Authorization': "Bearer " + self.subject}, json={'idempotency_key': 'shutdown-close'})
        assert response.status_code == 200, response.text
        return self.wait_operation(response.json()['data']['operation_id'], stages=('SUCCEEDED',))

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
