"""Disposable Nexus owner with real owned Windows processes, never user homes."""
import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys

import pytest
from nexus_connector_core.native.process import spawn_owned_process, snapshot_owned_process_birth
from okto_nexus.adapters.inbound.http.lock import ServeLock
from test_embedded_dispatch import local_setup, connect_local, admit, wait_receipt
from test_agent_recovery_isolation import create_agent, remote_roundtrip
from test_vertical_inventory import _Native


class ProcessNative(_Native):
    def __init__(self, root):
        super().__init__()
        self.process = spawn_owned_process([sys.executable, '-c', 'import time; time.sleep(300)'],
            cwd=str(root), env=dict(os.environ), text=True)

    def owned_process_birth(self):
        return snapshot_owned_process_birth(self.process)

    async def close(self):
        self.process.kill()
        await asyncio.to_thread(self.process.wait, timeout=5)
        return await super().close()


class ProcessFactory:
    def __init__(self):
        self.natives = []

    async def open(self, prepared, session_id, context, *, stream_epoch):
        native = ProcessNative(Path(prepared.cwd))
        self.natives.append(native)
        return native


def run(root, phase):
    with pytest.MonkeyPatch.context() as patch:
        with contextmanager(local_setup.__wrapped__)(root, patch, None) as setup:
            deps, app, client, headers, *_ = setup
            lock = ServeLock(root / 'home')
            lock.acquire()
            try:
                setup, binding, _ = connect_local(setup)
                second = create_agent(setup, 'second-local')
                second, other_binding, _ = connect_local(second, agent_id='second-local')
                factory = ProcessFactory()
                owner = app.state.embedded_dispatch_owner
                owner.native_factory = factory
                if phase == 'before-bind':
                    original_execute = owner._execute
                    held = asyncio.Event()
                    async def before_bind(frame):
                        if frame['agent_id'] == 'subject':
                            await held.wait()
                        return await original_execute(frame)
                    owner._execute = before_bind
                sessions = []
                for subject_setup, subject_binding in [(setup, binding), (second, other_binding)]:
                    opened = admit(subject_setup, subject_binding, 'crash-open', 'runtime.start', new_session=True)
                    sessions.append(opened['session_id'])
                    if phase != 'before-bind' or subject_binding['agent_id'] != 'subject':
                        wait_receipt(subject_setup, opened)
                remote_roundtrip(create_agent(setup, 'remote-before-crash'), 'remote-before-crash')
                # Simulate captured bytes waiting for Nexus projection at crash.
                from nexus_connector_core import RuntimeEvent
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    streams = [dict(r) for r in uow.connection.execute('SELECT * FROM execution_local_streams')]
                async def retain():
                    for stream in streams:
                        _, journal = await owner.host._runtime_tasks[(stream['executor_id'], stream['session_id'])]
                        await journal.append_event(RuntimeEvent(stream['server_id'], stream['executor_id'],
                            stream['session_id'], stream['stream_epoch'], 1, 'text_delta', 'technical.output', {'text': 'captured-before-crash'}))
                # Core owns sequences; process termination may race publication.
                # Both pre-ACK and post-ACK outcomes must restore without duplicates.
                client.portal.call(retain)
                state = dict(headers=headers, binding=binding, body=setup[4],
                    processes=[n.process.pid for n in factory.natives],
                    sessions=sessions, expected_events=len(streams))
                ready = root / 'ready.json'
                pending = ready.with_suffix('.tmp')
                pending.write_text(json.dumps(state), encoding='utf-8')
                pending.replace(ready)
                sys.stdin.readline()  # parent chooses orderly exit or exact process kill
            finally:
                lock.release()


if __name__ == '__main__':
    run(Path(sys.argv[1]).resolve(), sys.argv[2])
