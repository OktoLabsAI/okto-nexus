"""Real remote setup/daemon transports; only installation/native peers are fake.

All state, IPC credentials and operator accounts belong to pytest's Temp tree.
No provider, OS service installation or personal credential store is consulted.
"""
import asyncio
from copy import deepcopy
from dataclasses import asdict, replace
from functools import partial
import io
import json
import time

from nexus_connector_core import InstallationCandidate, RuntimeEvent, calculate_inventory_revision
from nexus_connector_core.discovery import fingerprint
from nexus_connector_core.installation import effective_installation_ref

from okto_nexus.adapters.inbound.http.operator_auth import OperatorAuth
from okto_nexus.adapters.outbound.operator_client import OperatorProfile
from okto_nexus.adapters.outbound.service_manager.context import atomic_json, read_json
from okto_nexus.application.project_preset import configuration
from okto_nexus.application.remote_terminal_setup import RemoteProjectSetup
from okto_nexus.application.terminal_connection import ConnectionError, PREFIX
from okto_nexus.application.terminal_work import TerminalWork
from okto_nexus_connector.cli.commands import connect, configure_local, identity
from okto_nexus_connector.cli.main import build_parser
from okto_nexus_connector.cli.output import Output
from okto_nexus_connector.daemon import r4_control, r4_execution
from okto_nexus_connector.daemon.app import DaemonApp
from okto_nexus_connector.errors import ConnectorError
from okto_nexus_connector.identity.vault import RestrictedFileVault
from okto_nexus_connector.platform.paths import state_file
from okto_nexus_connector.services import remote_setup
from okto_nexus_connector.storage.state_store import StateStore
from okto_nexus_connector.transport.https_client import NexusHTTPClient
from test_remote_operator_terminal import ACCOUNT, MemoryVault
from test_vertical_inventory import _Native


class NativeFactory:
    """Synthetic native process, with real Core journals/receipts around it."""

    def __init__(self):
        self.opened = {}

    async def open(self, prepared, session_id, context, *, stream_epoch):
        assert context.r4_authority is not None
        native = _Native()
        native.native_id = 'synthetic-' + session_id
        self.opened[session_id] = (native, stream_epoch, prepared.cwd)
        return native


class RemoteProject:
    def __init__(self, runtime, tmp_path, monkeypatch, *, actions=1):
        self.deps, self.client = runtime[:2]
        self.origin = str(self.client.base_url).rstrip('/')
        self.root = tmp_path / 'remote-host'
        self.root.mkdir()
        self.project = self.root / 'project'
        self.project.mkdir()
        self.operator_home = tmp_path / 'human-client'
        OperatorAuth(self.deps.config.home_dir).configure(**ACCOUNT, local=True)
        self.operator_vault = MemoryVault()
        self.profile = OperatorProfile(self.operator_home, 'remote', backend=self.operator_vault)
        self.profile.login(self.origin, **ACCOUNT)
        self.http = self.profile.client()
        self.calls = []
        self.lose_next = None
        self.material, self.handoffs = [], []
        self.checkpoint = self.operator_home / 'terminal/profiles/project.json'
        self.work_checkpoint = self.operator_home / 'terminal/work/project.json'
        self.flow = RemoteProjectSetup(self.call, self.save_connection, origin=self.origin,
            material_sink=self.material.append, handoff_sink=lambda value: self.handoffs.append(deepcopy(value)))

        binary = self.root / 'synthetic-codex.exe'
        binary.write_bytes(b'Synthetic qualification peer; never executed')
        self.candidate = InstallationCandidate('codex_app_server', str(binary), fingerprint(binary), 'explicit', 'selected')
        self.observed = replace(self.candidate, version='fixture-v1')
        self.store = StateStore(state_file(self.root))
        config = configuration(adapter_id=self.candidate.adapter_id, project=str(self.project), label='Remote renewal')
        config['execution_location'] = 'remote'
        config['authorization'] = dict(minutes=60, actions=actions)
        local = remote_setup.prepare(self.store, setup_run_id='renewal-root', server=self.origin,
            configuration=config, candidate=self.candidate, candidate_ref=effective_installation_ref(self.candidate),
            inventory_revision=calculate_inventory_revision([self.candidate]))
        selection = dict(agent='renewal-subject', create_agent=True, display_name='Renewal subject',
            client=None, project='operator-shortcut', label='Remote renewal', workspace_id=None,
            binding_id=None, candidate_ref=None, provider_home=None, operator_profile='remote', remote_draft=local['draft'])
        self.document = self.flow.review(selection)
        result = self.flow.apply(self.document, approval=self.document['review_revision'], timeout=0)
        assert result['state'] == 'awaiting_host' and len(self.material) == 1
        self.receipt = self.root / 'handoff.json'
        self.receipt.write_bytes(remote_setup.document_bytes(self.handoffs[-1]))
        self.bootstrap = deepcopy(self.handoffs[-1]['bootstrap'])
        self.key = self.material[0]
        self.agent_id, self.server_id = self.bootstrap['agent_id'], self.bootstrap['server_id']
        self.store.update(lambda state: state.preferences.update({'vault.fallback_file.approved': True}))
        (self.root / 'vault').mkdir(exist_ok=True)
        self.vault = RestrictedFileVault(self.root / 'vault', approved=True)
        monkeypatch.setenv('OKTO_NEXUS_CONNECTOR_VAULT', 'file')
        monkeypatch.setattr(identity, '_vault', lambda *args: self.vault)
        monkeypatch.setattr(configure_local, '_vault', lambda *args: self.vault)
        monkeypatch.setattr(connect, '_read_key', lambda *args: self.key)
        monkeypatch.setattr(connect, 'vault_backend_names', lambda: ('synthetic',))
        monkeypatch.setattr(configure_local.manager, 'start', lambda *args: None)
        self.probes = []

        async def observe(*args, **kwargs):
            self.probes.append(kwargs)
            self.store.update(lambda state: state.execution_executors[0].installation_observations.append(
                dict(source=asdict(self.candidate), version=self.observed.version)))

        async def candidates(*args, **kwargs):
            return [self.observed]

        async def discover(*, adapter_ids=None, cancel_requested=None):
            return [self.observed] if adapter_ids is None or self.observed.adapter_id in adapter_ids else []

        monkeypatch.setattr(configure_local, 'observe_installation', observe)
        monkeypatch.setattr(configure_local, 'configured_candidates', candidates)
        monkeypatch.setattr(r4_control, 'R4DaemonControl', partial(r4_control.R4DaemonControl, discover=discover))
        self.native = NativeFactory()
        monkeypatch.setattr(r4_execution, 'R4DaemonExecution', partial(r4_execution.R4DaemonExecution, native_factory=self.native))
        self.daemon = DaemonApp(self.root, ipc_transport='auto')
        self.daemon_task = None
        self.output = Output(json_mode=False, stream=io.StringIO())
        self.receipt_frames = []
        publish = NexusHTTPClient.publish_operation_receipt

        async def capture(http, ticket, *, frame):
            result = await publish(http, ticket, frame=frame)
            self.receipt_frames.append(deepcopy(frame))
            return result

        monkeypatch.setattr(NexusHTTPClient, 'publish_operation_receipt', capture)

    def call(self, method, path, body=None):
        self.calls.append((method, path))
        response = self.http(method, path, body)
        if self.lose_next == path:
            self.lose_next = None
            raise ConnectionError('OUTCOME_UNKNOWN', 'Injected response loss after real HTTP commit.', possible_effect=True)
        return response

    def save_connection(self, document):
        self.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(self.checkpoint, document)

    def work(self):
        def save(document):
            self.work_checkpoint.parent.mkdir(parents=True, exist_ok=True)
            atomic_json(self.work_checkpoint, document)
        return TerminalWork(self.call, save, read_json(self.checkpoint),
            read_json(self.work_checkpoint) if self.work_checkpoint.exists() else None)

    async def eventually(self, predicate, *, timeout=20):
        deadline = time.monotonic() + timeout
        while not predicate():
            assert self.daemon_task is None or not self.daemon_task.done(), 'Daemon stopped unexpectedly'
            assert time.monotonic() < deadline, self.control.status() if self.control else 'Control not composed'
            await asyncio.sleep(.03)

    @property
    def control(self):
        return self.daemon.r4_controls.get(self.server_id)

    async def start(self):
        self.daemon_task = asyncio.create_task(self.daemon.run_forever())
        await self.eventually(lambda: self.daemon.lock.live_owner() is not None)
        args = build_parser().parse_args(['connect', '--setup-receipt', str(self.receipt), '--alias', 'project'])
        # state.reload and executor.realize use the actual authenticated IPC.
        pending = await connect.run_connect(args, self.output, self.root)
        assert pending['status'] == 'awaiting_operator_approval', pending
        result = await asyncio.to_thread(self.flow.apply, read_json(self.checkpoint), timeout=0)
        assert result['state'] == 'awaiting_finish'
        try:
            configured = await connect.run_connect(args, self.output, self.root)
        except ConnectorError as error:
            # The actual background owner may win the same approved Finish.
            # Its durable result, not the exception alone, permits this retry.
            assert error.code == 'STALE_GENERATION'
            current = self.store.load()
            saved = current.preferences[f'configure.{self.server_id}.{self.agent_id}.renewal-root']
            assert saved['stage'] == 'done' and saved['result']['saved'] is True
            intent, = current.binding_intents
            assert intent.status == 'APPLIED' and intent.applied_binding == saved['binding']
            configured = await connect.run_connect(args, self.output, self.root)
        assert configured['saved'], configured
        result = await asyncio.to_thread(self.flow.apply, read_json(self.checkpoint), timeout=0)
        assert result['state'] == 'configured'
        self.binding = read_json(self.checkpoint)['result']['binding']
        await self.eventually(lambda: self.control and self.control.status()['execution_ready'])
        await self.inventory_ready()
        assert not self.native.opened and len(self.probes) == 1
        return self

    async def inventory_ready(self):
        deadline = time.monotonic() + 20
        while True:
            owner = self.control.inventory_owner
            try:
                if owner is not None:
                    await owner.require_batch(self.candidate.adapter_id)
                    return
            except ConnectorError as error:
                assert error.code in ('INVENTORY_NOT_FRESH', 'STALE_GENERATION')
            assert time.monotonic() < deadline, self.control.status()
            await asyncio.sleep(.03)

    async def close(self):
        if self.daemon_task is not None:
            self.daemon.request_stop()
            result = await asyncio.wait_for(asyncio.shield(self.daemon_task), 45)
            assert result == 0, 'Daemon reported unresolved ownership on cleanup'

    def rows(self, table):
        # Table names are test constants, never user input.
        with self.deps.connection_factory.unit_of_work(write=False) as uow:
            return [dict(row) for row in uow.connection.execute('SELECT * FROM ' + table)]

    async def operation(self, operation_id, *, stage='SUCCEEDED'):
        deadline = time.monotonic() + 20
        while True:
            value = await asyncio.to_thread(self.call, 'GET', PREFIX + '/runtime/operations/' + operation_id)
            assert value.get('error') is None, value
            if value['executor_stage'] == stage:
                return value
            assert time.monotonic() < deadline, value
            await asyncio.sleep(.03)

    async def send_and_complete(self, *, request_id):
        flow = self.work()
        operation = await asyncio.to_thread(flow.submit, 'Explicit synthetic work', new_session=True,
            client_intent_id=request_id)
        assert operation.get('state') != 'blocked', operation
        await self.operation(operation['operation_id'], stage='SUBMITTED')
        child = operation['submission_turn_operation_id']
        await self.operation(child, stage='SUBMITTED')
        session_id = operation['scope']['session_id']
        native, epoch, cwd = self.native.opened[session_id]
        assert cwd == str(self.project)
        await native.queue.put(RuntimeEvent(self.server_id, self.binding['executor_id'], session_id,
            epoch, 0, 'turn_state', 'fixture.result', dict(delivery_phase='terminal',
                delivery_outcome='success', output_text='Synthetic remote result'), operation_id=child))
        await self.operation(child)
        return operation

    async def rotate(self, monkeypatch):
        """Existing explicit one-shot endpoint; no retry claim for key rotation."""
        result = await asyncio.to_thread(self.call, 'POST', '/api/v1/agents/' + self.agent_id + '/regenerate-key')
        new_key = result['data']['api_key']
        async with NexusHTTPClient(self.origin) as http:
            me = await http.me(new_key)
        assert me.credential_epoch > self.bootstrap['credential_epoch']
        monkeypatch.setattr(identity, '_read_key', lambda *args, **kwargs: new_key)
        args = build_parser().parse_args(['identity', 'replace-credential', 'project'])
        replaced = await identity.run_identity(args, self.output, self.root)
        assert replaced['credential_epoch'] == me.credential_epoch
        self.key = new_key
        return me

    async def close_session(self, session_id):
        result = await asyncio.to_thread(self.work().submit, action='close', session_id=session_id,
            client_intent_id='explicit-close-' + session_id)
        await self.operation(result['operation_id'])
        await self.eventually(lambda: self.native.opened[session_id][0].stopped)

    def assert_redacted(self):
        text = self.checkpoint.read_text() + self.output.stream.getvalue() + self.store.path.read_text()
        if self.work_checkpoint.exists():
            text += self.work_checkpoint.read_text()
        assert self.key not in text and self.material[0] not in text
        assert all(token not in text for token in self.operator_vault.values.values())
        json.loads(self.checkpoint.read_text())
