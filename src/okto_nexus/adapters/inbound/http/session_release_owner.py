"""Bounded owned release validations; the WebSocket reader never awaits history."""
import asyncio

import anyio
from nexus_connector_core import CoreError
from nexus_connector_core.session_release import encode_session_release, decode_session_release, session_release_deferred


class SessionReleaseOwner:
    def __init__(self, *, validate, send, max_pending=4):
        self.validate, self.send, self.max_pending = validate, send, max_pending
        self.pending = {}
        self.stopping = False
        self.last_error = None

    async def submit(self, frame):
        encoded = encode_session_release(frame)
        frame = decode_session_release(encoded)
        identity = frame['release_id']
        prior = self.pending.get(identity)
        if prior is not None:
            if prior[1] != encoded:
                raise CoreError('SCOPE_MISMATCH', 'session_release_owner')
            return
        if self.stopping or len(self.pending) >= self.max_pending:
            await self.send(session_release_deferred(frame))
            return
        task = asyncio.create_task(self._produce(frame), name='session-release-validation')
        self.pending[identity] = (task, encoded)
        def done(completed):
            self.pending.pop(identity, None)
            if not completed.cancelled():
                completed.exception()
        task.add_done_callback(done)

    async def _produce(self, frame):
        try:
            response = await anyio.to_thread.run_sync(lambda: self.validate(frame))
        except Exception as error:
            self.last_error = error
            response = session_release_deferred(frame)
        if not self.stopping:
            try:
                await self.send(response)
            except Exception as error:
                # A lost socket ACK does not discard a committed release. Its
                # original identity is recovered by the next report/reconcile.
                self.last_error = error

    async def stop(self):
        self.stopping = True
        await asyncio.shield(asyncio.gather(*(item[0] for item in tuple(self.pending.values())), return_exceptions=True))
