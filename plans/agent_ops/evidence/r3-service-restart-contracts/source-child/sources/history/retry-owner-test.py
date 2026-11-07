"""SVC-T22: restart stays pending while a real Connector-owned child is alive.

The Server is a separate real process. The Python peer belongs to the Core in
the still-running Connector, with the normal launch container, birth journal,
claim and slot. This is not a child surviving the death of its owner, a provider
campaign, or a native-service installation. Only discovery/provider behavior is
synthetic; no containment policy or durable ownership fact is rewritten.
"""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from nexus_connector_core import OperationKey, RuntimeEvent, SessionKey
from nexus_connector_core.native.process import (
    observe_owned_process,
    snapshot_owned_process_birth,
    spawn_owned_process,
)

import remote_renewal_helpers
from test_service_restart_contracts import RestartServer
from test_vertical_inventory import _Native


CHILD = """
import os, sys, threading
watchdog = threading.Timer(120, lambda: os._exit(88))
watchdog.daemon = True
watchdog.start()
print('READY', flush=True)
for line in sys.stdin.buffer:
    if line == b'WORK\\n':
        with open(sys.argv[1], 'ab', buffering=0) as marker:
            marker.write(b'work\\n')
            os.fsync(marker.fileno())
        print('ACK', flush=True)
    elif line == b'STOP\\n':
        break
"""


class OwnedNative(_Native):
    """Small LF peer with physical liveness; normal Core owns its handle."""

    def __init__(self, child):
        super().__init__()
        self.child = child
        self.close_entered = asyncio.Event()
        self.release_close = asyncio.Event()

    async def send(self, verb, payload, operation_id, *, expected_turn_id=None):
        assert verb == 'send_turn'

        def write_once():
            self.child.stdin.write(b'WORK\n')
            self.child.stdin.flush()
            assert self.child.stdout.readline() == b'ACK\n'

        await asyncio.wait_for(asyncio.to_thread(write_once), 10)
        await super().send(verb, payload, operation_id, expected_turn_id=expected_turn_id)

    async def close(self):
        self.close_entered.set()
        await self.release_close.wait()
        if self.child.poll() is None:
            self.child.stdin.write(b'STOP\n')
            self.child.stdin.flush()
            await asyncio.to_thread(self.child.wait, 10)
        assert observe_owned_process(self.child)['stop_observed'] is True
        self.stopped = True
        await self.queue.put(None)
        return 'graceful'

    async def observe(self):
        return ('STOPPED' if observe_owned_process(self.child)['stop_observed'] else 'RUNNING', 'IDLE')

    def dispose_owned_child(self):
        # Cleanup only the exact handle created by this test, never a PID read
        # from historical metadata. Do not leak a child if an assertion fails.
        if self.child.poll() is None:
            self.child.kill()
            self.child.wait(timeout=10)
        for pipe in (self.child.stdin, self.child.stdout, self.child.stderr):
            if pipe is not None:
                pipe.close()


class OwnedFactory:
    def __init__(self):
        self.opened = {}

    async def open(self, prepared, session_id, context, *, stream_epoch,
                   process_birth_recorder, process_launch):
        assert context.r4_authority is not None
        assert process_launch.identity.key.session_id == session_id
        environment = {key: value for key, value in os.environ.items()
                       if key.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP'}}
        environment.update(USERPROFILE=prepared.cwd, APPDATA=prepared.cwd,
                           LOCALAPPDATA=prepared.cwd, PYTHONIOENCODING='utf-8')

        def start():
            child = spawn_owned_process(
                [getattr(sys, '_base_executable', sys.executable), '-I', '-u', '-c', CHILD,
                 str(Path(prepared.cwd)/'native-work.txt')],
                container_id=process_launch.identity.container_id,
                cwd=prepared.cwd, env=environment)
            return OwnedNative(child)

        native = await process_launch.produce(validate_authority=lambda: None, start=start)
        self.opened[session_id] = (native, stream_epoch, prepared.cwd)
        # Use the callback supplied by Core, scoped to the admitted opening;
        # this is not a test INSERT or a foreign process mapped to a session.
        await process_birth_recorder(snapshot_owned_process_birth(native.child))
        ready = await asyncio.wait_for(asyncio.to_thread(native.child.stdout.readline), 10)
        assert ready == b'READY\n'
        return native


def service_command(server, action, *, timeout):
    completed = subprocess.run([
        sys.executable, '-I', str(server.launcher), 'service', action,
        '--home', str(server.home), '--host', '127.0.0.1', '--port', str(server.port),
        '--json', '--timeout', str(timeout)], cwd=server.root, env=server.env,
        capture_output=True, text=True, timeout=timeout+20)
    # Only canonical metadata is used in assertions; do not echo private logs.
    assert completed.returncode in (0, 3), 'Disposable lifecycle CLI failed'
    return completed.returncode, json.loads(completed.stdout)


@pytest.mark.skipif(os.name != 'nt', reason='Current Windows owned-Job qualification')
def test_restart_pending_keeps_real_connector_child_claim_and_slot(tmp_path, monkeypatch):
    monkeypatch.setattr(remote_renewal_helpers, 'NativeFactory', OwnedFactory)
    server = RestartServer(tmp_path)
    project = None

    async def scenario():
        nonlocal project
        old_pid = await asyncio.to_thread(server.start)
        project = remote_renewal_helpers.RemoteProject(
            (server.deps, server.client), tmp_path, monkeypatch, actions=2)
        await project.start()
        initial_code, initial = await asyncio.to_thread(service_command, server, 'status', timeout=2)
        assert initial_code == 0 and initial['state'] == 'ready'
        assert initial['pid'] == old_pid
        flow = project.work()
        opened = await asyncio.to_thread(flow.submit, 'One owned local peer effect',
                                        new_session=True, client_intent_id='live-child-restart')
        await project.operation(opened['operation_id'], stage='SUBMITTED')
        turn_id = opened['submission_turn_operation_id']
        await project.operation(turn_id, stage='SUBMITTED')
        session_id = opened['scope']['session_id']
        native, epoch, _ = project.native.opened[session_id]
        child = native.child
        assert child.poll() is None and child.pid not in (os.getpid(), old_pid)
        marker = project.project/'native-work.txt'
        assert marker.read_bytes() == b'work\n'
        key = SessionKey(project.server_id, project.binding['executor_id'], session_id)
        journal = await project.daemon.host.ensure_journal()
        ledger = await project.daemon.host.ensure_ledger()
        birth = await journal.get_process_birth(key)
        launch = await journal.get_process_launch(key)
        claim = await journal.get_session_claim(key)
        slot = await ledger.owned_slot_state(key)
        assert birth is not None and birth.key == key and birth.evidence.pid == child.pid
        assert birth.opening_operation_id == claim.opening_operation_id == slot.opening_operation_id == opened['operation_id']
        assert launch.identity.container_id == birth.evidence.container_id
        assert launch.identity.key == key and launch.spawn_claimed and launch.stop_proof is None
        assert birth.evidence == snapshot_owned_process_birth(child)
        assert not slot.released
        original_ids = {row['operation_id'] for row in project.rows('execution_operations')}

        code, pending = await asyncio.to_thread(service_command, server, 'restart', timeout=.2)
        assert code == 3 and pending['state'] == 'stopping'
        assert pending['wait_timed_out'] and pending['shutdown']['state'] == 'DRAINING_PENDING'
        assert pending['pid'] == old_pid and pending['generation'] == initial['generation']
        assert server.children[-1].poll() is None and child.poll() is None
        assert await journal.get_session_claim(key) == claim
        assert await ledger.owned_slot_state(key) == slot
        assert await journal.get_process_birth(key) == birth
        assert (await journal.get_process_launch(key)).stop_proof is None
        assert {row['operation_id'] for row in project.rows('execution_operations')} == original_ids
        assert len(project.native.opened) == len(native.sent) == 1
        assert marker.read_bytes() == b'work\n'

        # Admit close while the turn is still active. Its physical release is
        # held until the terminal publication below is acknowledged, so Server
        # drain cannot race ahead of the explicit close request.
        closed = await asyncio.to_thread(project.work().submit, action='close',
            session_id=session_id, client_intent_id='close-owned-child')
        await asyncio.wait_for(native.close_entered.wait(), 15)
        await native.queue.put(RuntimeEvent(project.server_id, project.binding['executor_id'],
            session_id, epoch, 0, 'turn_state', 'fixture.result',
            dict(delivery_phase='terminal', delivery_outcome='success', output_text='One local peer result'),
            operation_id=turn_id))
        await project.operation(turn_id)
        assert child.poll() is None and not (await ledger.owned_slot_state(key)).released
        native.release_close.set()
        await project.eventually(lambda: native.stopped)
        assert child.poll() is not None and observe_owned_process(child)['stop_observed'] is True
        deadline = asyncio.get_running_loop().time()+20
        while not (await ledger.owned_slot_state(key)).released:
            assert asyncio.get_running_loop().time() < deadline
            await asyncio.sleep(.03)
        while True:
            receipt = await journal.get_receipt(OperationKey(project.server_id, key.executor_id, closed['operation_id']))
            if receipt is not None and receipt.stage == 'SUCCEEDED':
                break
            assert asyncio.get_running_loop().time() < deadline
            await asyncio.sleep(.03)
        assert await asyncio.to_thread(server.children[-1].wait, 30) == 0
        # The already-returned restart request never schedules an automatic
        # replacement; only a later explicit command may start a generation.
        final_code, final = await asyncio.to_thread(service_command, server, 'status', timeout=2)
        assert final_code == 0 and final['state'] == 'stopped'
        shutdown = json.loads((server.home/'service-shutdown.json').read_text(encoding='utf-8'))
        assert shutdown['state'] == 'DRAINED' and shutdown['generation'] == initial['generation']
        assert len(project.native.opened) == len(native.sent) == 1
        assert marker.read_bytes() == b'work\n'
        project.assert_redacted()

    async def run():
        try:
            await scenario()
        finally:
            try:
                if project is not None:
                    for native, _, _ in project.native.opened.values():
                        native.release_close.set()
                    await project.close()
            finally:
                if project is not None:
                    for native, _, _ in project.native.opened.values():
                        native.dispose_owned_child()
                server.cleanup()

    asyncio.run(run())
