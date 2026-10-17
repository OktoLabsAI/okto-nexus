"""Disposable Connector daemon for the cross-process capacity campaign.

Only native discovery/provider effects are synthetic. Control, capabilities,
leases, capacity ledger, reconciliation and receipts use production owners.
The parent sends test credentials through stdin; responses exclude secrets.
"""
import asyncio
from functools import partial
import json
import os
from pathlib import Path
import sys
import threading


class Native:
    native_id = 'capacity-process-native'
    active_turn_id = 'capacity-process-turn'

    def __init__(self, faults):
        self.queue, self.sent, self.stopped = asyncio.Queue(), [], False
        self.faults = faults
        self.closing = False

    async def send(self, verb, payload, operation_id, **options):
        self.sent.append((verb, operation_id))
        if verb == 'send_turn' and self.faults['lose_next_send']:
            self.faults['lose_next_send'] = False
            raise OSError('Synthetic provider accepted work, response lost')

    async def events(self):
        while (event := await self.queue.get()) is not None:
            yield event

    async def observe(self):
        return ('STOPPED' if self.stopped else 'RUNNING', 'IDLE')

    async def close(self):
        self.closing = True
        await self.faults['stop_allowed'].wait()
        self.stopped = True
        await self.queue.put(None)
        return 'graceful'


async def run(config):
    from nexus_connector_core import InstallationCandidate, LocalRuntimeCore
    from nexus_connector_core.discovery import fingerprint
    from nexus_connector_core.native.adapter_types import NativeAdapterError, ErrorCode
    from okto_nexus_connector.daemon.app import DaemonApp
    from okto_nexus_connector.daemon import r4_control, r4_execution
    from okto_nexus_connector.storage.state_store import (
        IdentityRecord, ServerProfileRecord, ExecutionExecutorRecord)
    from okto_nexus_connector.storage.r4_publications import R4PublicationStore
    from okto_nexus_connector.transport.r4_connection import R4Connection

    daemon = DaemonApp(Path(config['root']))
    daemon.host.max_owned_slots = 1
    previous = next((item for item in daemon.store.load().identities
                     if item.server_id == config['server_id'] and item.agent_id == 'subject'), None)
    if previous is None:
        identity = daemon.vault.store('subject', config['agent_key'])
        daemon.vault.store('provider-demo', 'synthetic-provider-secret')
    else:
        identity = previous.secret_handle
    def configure(state):
        state.connector_id = config.get('connector_id', 'connector')
        state.servers[config['server_id']] = ServerProfileRecord(
            config['server_id'], config['base_url'], config['base_url'], 'now')
        state.identities = [IdentityRecord('subject', config['server_id'], 'subject',
            identity, config['credential_epoch'], 'now')]
        if not state.execution_executors:
            state.execution_executors.append(ExecutionExecutorRecord(config['server_id'],
                state.connector_id, 'subject', config.get('register_intent', 'register'), 'Remote host',
                executor_id=config['executor_id'], state='REGISTERED', inventory_publication_sequence=1))
    daemon.store.update(configure)
    binary = Path(config['binary'])
    candidate = InstallationCandidate('codex_app_server', str(binary), fingerprint(binary), 'explicit', 'selected')
    async def discover(*, adapter_ids, cancel_requested):
        # Match the production per-harness discovery port. Do not report the
        # synthetic Codex installation as evidence for sibling adapters.
        return [candidate] if candidate.adapter_id in adapter_ids else []
    peers, opening = {}, set()
    stop_allowed = asyncio.Event()
    stop_allowed.set()
    faults = {'lose_next_send': False, 'stop_allowed': stop_allowed,
              'publication_cut': None, 'publication_cuts': 0,
              'fail_next_prepare': False, 'preparation_failures': 0,
              'fail_next_candidate': False, 'candidate_failures': 0,
              'lose_next_open': False, 'open_ack_losses': 0,
              'lose_next_startup_ack': False, 'startup_ack_losses': 0,
              'hold_bind_commit': False, 'bind_commit_entered': False,
              'bind_commit_gate': threading.Event()}
    original_startup_publish = R4Connection.publish_startup_refusal
    async def publish_startup_with_lost_ack(self, request, **options):
        reply = await original_startup_publish(self, request, **options)
        if faults['lose_next_startup_ack']:
            faults['lose_next_startup_ack'] = False
            faults['startup_ack_losses'] += 1
            raise OSError('Synthetic startup ACK observation lost')
        return reply
    R4Connection.publish_startup_refusal = publish_startup_with_lost_ack
    original_candidates = r4_execution.R4DaemonExecution._candidates
    async def candidates_with_cut(self, frame):
        if faults['fail_next_candidate']:
            faults['fail_next_candidate'] = False
            faults['candidate_failures'] += 1
            from okto_nexus_connector.errors import ConnectorError
            raise ConnectorError('VALIDATION_ERROR', 'r4_launch',
                'Synthetic candidate discovery failure.')
        return await original_candidates(self, frame)
    r4_execution.R4DaemonExecution._candidates = candidates_with_cut
    original_prepare = LocalRuntimeCore.prepare
    async def prepare_with_cut(runtime, *args, **kwargs):
        if faults['fail_next_prepare']:
            faults['fail_next_prepare'] = False
            faults['preparation_failures'] += 1
            raise NativeAdapterError(ErrorCode.CONFIG_ERROR, 'Synthetic version probe deadline',
                                     {'reason': 'version_probe_timeout'})
        return await original_prepare(runtime, *args, **kwargs)
    LocalRuntimeCore.prepare = prepare_with_cut
    # Cut after a real durable commit, before the execution owner receives its
    # result. Never replace the store or manufacture a Core operation fact.
    for method_name in ('reserve', 'bind', 'record_startup'):
        original = getattr(R4PublicationStore, method_name)
        def cut_publication(self, *args, _original=original, _name=method_name, **kwargs):
            result = _original(self, *args, **kwargs)
            if _name == 'bind' and faults['hold_bind_commit']:
                faults['hold_bind_commit'] = False
                faults['bind_commit_entered'] = True
                if not faults['bind_commit_gate'].wait(60):
                    raise OSError('Synthetic binding commit observer timed out')
            if faults['publication_cut'] == _name:
                faults['publication_cut'] = None
                faults['publication_cuts'] += 1
                raise OSError('Synthetic publication commit reply lost: ' + _name)
            return result
        setattr(R4PublicationStore, method_name, cut_publication)
    allow_open = asyncio.Event()
    allow_open.set()
    class Factory:
        async def open(self, prepared, session_id, context, *, stream_epoch):
            assert prepared.cwd == config['workspace_root']
            assert context.r4_authority is not None
            opening.add(session_id)
            try:
                await allow_open.wait()
                peer = Native(faults)
                peers[session_id] = peer
                if faults['lose_next_open']:
                    faults['lose_next_open'] = False
                    faults['open_ack_losses'] += 1
                    raise OSError('Synthetic native open may have succeeded; reply lost')
                return peer
            finally:
                opening.discard(session_id)
    r4_control.R4DaemonControl = partial(r4_control.R4DaemonControl, discover=discover)
    r4_execution.R4DaemonExecution = partial(r4_execution.R4DaemonExecution, native_factory=Factory())
    daemon._start_transports()
    control = daemon.r4_controls[config['server_id']]
    stopped = False
    try:
        while line := await asyncio.to_thread(sys.stdin.readline):
            command = json.loads(line)['command']
            if command == 'disconnect':
                await control.connection.close()
            elif command == 'hold_open':
                allow_open.clear()
            elif command == 'release_open':
                allow_open.set()
            elif command == 'lose_next_send':
                faults['lose_next_send'] = True
            elif command == 'lose_next_open':
                faults['lose_next_open'] = True
            elif command == 'fail_next_prepare':
                faults['fail_next_prepare'] = True
            elif command == 'fail_next_candidate':
                faults['fail_next_candidate'] = True
            elif command == 'lose_next_startup_ack':
                faults['lose_next_startup_ack'] = True
            elif command == 'hold_bind_commit':
                faults['hold_bind_commit'] = True
            elif command == 'release_bind_commit':
                faults['bind_commit_gate'].set()
            elif command in ('cut_publication_reserve', 'cut_publication_bind',
                    'cut_publication_record_startup'):
                faults['publication_cut'] = command.removeprefix('cut_publication_')
            elif command == 'hold_stop':
                stop_allowed.clear()
            elif command == 'release_stop':
                stop_allowed.set()
            elif command == 'stop':
                result = await daemon._shutdown()
                stopped = True
                print(json.dumps({'pending': result}), flush=True)
                return
            elif command != 'status':
                raise ValueError('Unknown campaign command')
            state = control.status()
            print(json.dumps(dict(pid=os.getpid(), ready=state['execution_ready'],
                error=state['error_code'], generation=state['connection_generation'],
                candidate_failures=faults['candidate_failures'],
                startup_ack_losses=faults['startup_ack_losses'],
                open_ack_losses=faults['open_ack_losses'],
                bind_commit_entered=faults['bind_commit_entered'],
                publication_cuts=faults['publication_cuts'],
                preparation_failures=faults['preparation_failures'],
                opens=len(peers), opening=len(opening), sends=sum(len(peer.sent) for peer in peers.values()),
                stopping=sum(peer.closing and not peer.stopped for peer in peers.values()),
                stopped=sum(peer.stopped for peer in peers.values()))), flush=True)
    finally:
        if not stopped:
            await daemon._shutdown()


if __name__ == '__main__':
    config = json.loads(sys.stdin.readline())
    sys.path[:0] = config.pop('source_roots')
    os.environ['OKTO_NEXUS_CONNECTOR_VAULT'] = 'file'
    asyncio.run(run(config))
