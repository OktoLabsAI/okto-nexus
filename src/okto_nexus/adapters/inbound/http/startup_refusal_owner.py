"""Bounded in-band startup refusal commits outside the WebSocket reader."""
import asyncio

import anyio
from nexus_connector_core import CoreError
from nexus_connector_core.startup_refusal_link import (
    decode_startup_refusal, encode_startup_refusal,
    startup_refusal_accepted, startup_refusal_deferred,
)


class StartupRefusalOwner:
    def __init__(self, *, validate, send, max_pending=4):
        self.validate, self.send, self.max_pending = validate, send, max_pending
        self.pending = {}
        self.stopping = False
        self.last_error = None

    async def submit(self, frame):
        encoded = encode_startup_refusal(frame)
        frame = decode_startup_refusal(encoded)
        identity = frame['request_id']
        prior = self.pending.get(identity)
        if prior is not None:
            if prior[1] != encoded:
                raise CoreError('SCOPE_MISMATCH', 'startup_refusal_owner')
            return
        if self.stopping or len(self.pending) >= self.max_pending:
            await self.send(startup_refusal_deferred(frame))
            return
        task = asyncio.create_task(self._produce(frame), name='startup-refusal-commit')
        self.pending[identity] = task, encoded
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
            response = startup_refusal_deferred(frame)
        if not self.stopping:
            try:
                await self.send(response)
            except Exception as error:
                self.last_error = error

    async def stop(self):
        self.stopping = True
        await asyncio.shield(asyncio.gather(*(item[0] for item in tuple(self.pending.values())),
            return_exceptions=True))
