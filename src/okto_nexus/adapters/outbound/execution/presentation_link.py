"""A bounded passive exchange on the authenticated Connector socket."""

import asyncio
import secrets

from nexus_connector_core import CoreError
from nexus_connector_core.presentation_link import (
    PRESENTATION_LINK_REVISION,
    PRESENTATION_READ,
    PRESENTATION_RESULT,
    encode_presentation_frame,
    presentation_request_hash,
)


class PresentationLink:
    def __init__(self, channel, send, *, timeout=5):
        self.channel, self._send, self._timeout = channel, send, timeout
        self.instance = secrets.token_hex(16)
        self._pending = {}
        self.closed = False

    async def read_codex(self, *, scope, target, thread_id):
        if self.closed or len(self._pending) >= 4:
            raise CoreError('SESSION_UNKNOWN', 'presentation_link')
        request_id = 'viewer_read_' + secrets.token_hex(16)
        frame = dict(contract_revision=PRESENTATION_LINK_REVISION, type=PRESENTATION_READ, **self.channel.identity(),
                     request_id=request_id, scope=scope, target=target, thread_id=thread_id)
        raw = encode_presentation_frame(frame)
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = (future, presentation_request_hash(frame))
        try:
            async with asyncio.timeout(self._timeout):
                await self._send(raw.decode('utf-8'))
                context = await future
            if self.closed or context is None or context['thread_id'] != thread_id:
                raise CoreError('SESSION_UNKNOWN', 'presentation_link')
            return context
        except (TimeoutError, OSError, RuntimeError) as error:
            raise CoreError('SESSION_UNKNOWN', 'presentation_link') from error
        finally:
            self._pending.pop(request_id, None)
            future.cancel()

    def accept_result(self, frame):
        if (frame['type'] != PRESENTATION_RESULT
                or any(frame[key] != value for key, value in self.channel.identity().items())):
            raise CoreError('SCOPE_MISMATCH', 'presentation_reply')
        retained = self._pending.get(frame['request_id'])
        if retained is None or self.closed:
            return
        future, expected_hash = retained
        if frame['request_hash'] != expected_hash:
            raise CoreError('SCOPE_MISMATCH', 'presentation_reply')
        if not future.done():
            future.set_result(frame['context'])

    def disconnect(self):
        self.closed = True
        for future, _ in self._pending.values():
            if not future.done():
                future.set_result(None)
