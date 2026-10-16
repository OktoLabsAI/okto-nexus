"""Disposable embedded owner terminated at an exact managed launch frontier."""
import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys

import pytest
from nexus_connector_core.journal import SQLiteJournal
from nexus_connector_core.native.process import spawn_owned_process, snapshot_owned_process_birth
from okto_nexus.adapters.inbound.http.lock import ServeLock
from test_embedded_dispatch import connect_local, admit
from test_local_realization import local_setup


def run(root, boundary):
    with pytest.MonkeyPatch.context() as patch:
        with contextmanager(local_setup.__wrapped__)(root, patch, None) as setup:
            _, app, client, headers, body, *_ = setup
            with ServeLock(root/'home'):
                setup, binding, _ = connect_local(setup)
                owner = app.state.embedded_dispatch_owner
                execute = owner._execute
                async def capture(frame, **kwargs):
                    if frame['action'] == 'runtime.open':
                        (root/'opening.json').write_text(json.dumps(dict(
                            headers=headers, body=body, binding=binding, session_id=frame['session_id'],
                            operation_id=frame['operation_id'])), encoding='utf-8')
                    return await execute(frame, **kwargs)
                owner._execute = capture
                if boundary == 'intent':
                    async def before_marker(*_):
                        os._exit(17)
                    patch.setattr(SQLiteJournal, 'mark_possible_effect', before_marker)
                class Factory:
                    async def open(self, prepared, session_id, context, *, stream_epoch,
                                   process_launch, process_birth_recorder):
                        if boundary == 'effect':
                            os._exit(17)
                        loop = asyncio.get_running_loop()
                        def start():
                            if boundary == 'claim':
                                os._exit(17)
                            if boundary == 'container':
                                from nexus_connector_core.native.process.windows_process import OwnedWindowsPopen
                                patch.setattr(OwnedWindowsPopen, '_execute_child', lambda *_a, **_k: os._exit(17))
                            process = spawn_owned_process([sys.executable, '-c', 'import time; time.sleep(60)'],
                                cwd=str(root), env=dict(os.environ), text=True,
                                container_id=process_launch.identity.container_id)
                            if boundary == 'birth':
                                asyncio.run_coroutine_threadsafe(
                                    process_birth_recorder(snapshot_owned_process_birth(process)), loop).result()
                            os._exit(17)
                        await process_launch.produce(validate_authority=lambda: None, start=start)
                owner.native_factory = Factory()
                admit(setup, binding, 'crash-during-launch', 'runtime.start', new_session=True)
                # Crash is initiated by the retained dispatch worker, not this waiter.
                client.portal.call(asyncio.sleep, 30)
                raise AssertionError('The disposable owner did not reach its crash frontier')


if __name__ == '__main__':
    run(Path(sys.argv[1]).resolve(), sys.argv[2])
