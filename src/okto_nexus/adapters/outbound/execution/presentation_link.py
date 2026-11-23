"""A bounded passive exchange on the authenticated Connector socket."""

import asyncio
import secrets
from contextlib import asynccontextmanager, suppress

import anyio
from nexus_connector_core import CoreError
from nexus_connector_core.presentation_link import (
    CLAUDE_PRESENTATION_CLOSE,
    CLAUDE_PRESENTATION_LINK_REVISION,
    CLAUDE_PRESENTATION_NEXT,
    CLAUDE_PRESENTATION_OPEN,
    CLAUDE_PRESENTATION_PROBE,
    CLAUDE_PRESENTATION_RESULT,
    PI_PRESENTATION_CLOSE,
    PI_PRESENTATION_EDIT,
    PI_PRESENTATION_LINK_REVISION,
    PI_PRESENTATION_NEXT,
    PI_PRESENTATION_OPEN,
    PI_PRESENTATION_PROBE,
    PI_PRESENTATION_RESULT,
    PRESENTATION_LINK_REVISION,
    PRESENTATION_READ,
    PRESENTATION_RESULT,
    decode_claude_presentation_output,
    decode_pi_presentation_output,
    encode_claude_presentation_frame,
    encode_pi_presentation_frame,
    encode_presentation_frame,
    presentation_request_hash,
)
from nexus_connector_core.saved_context_link import SAVED_CONTEXT_CODECS

SAVED_CONTEXT_RESULTS = frozenset(codec.observed_type for codec in SAVED_CONTEXT_CODECS)


class PresentationLink:
    def __init__(self, channel, send, *, timeout=5, codex_enabled=True, pi_enabled=False, claude_enabled=False):
        self.channel, self._send, self._timeout = channel, send, timeout
        self.instance = secrets.token_hex(16)
        self.codex_enabled, self.pi_enabled = codex_enabled, pi_enabled
        self.claude_enabled = claude_enabled
        self._pending = {kind: {} for kind in (
            PRESENTATION_RESULT, PI_PRESENTATION_RESULT, CLAUDE_PRESENTATION_RESULT, *SAVED_CONTEXT_RESULTS)}
        self.closed = False

    async def read_codex(self, *, scope, target, thread_id):
        if not self.codex_enabled:
            raise CoreError('SESSION_UNKNOWN', 'presentation_link')
        request_id = 'viewer_read_' + secrets.token_hex(16)
        frame = dict(contract_revision=PRESENTATION_LINK_REVISION, type=PRESENTATION_READ, **self.channel.identity(),
                     request_id=request_id, scope=scope, target=target, thread_id=thread_id)
        context = await self._exchange(frame, encode_presentation_frame(frame), PRESENTATION_RESULT, self._timeout)
        if context is None or context['thread_id'] != thread_id:
            raise CoreError('SESSION_UNKNOWN', 'presentation_link')
        return context

    def supports_saved_context(self, codec):
        return {codec.link_revision, codec.open_revision}.issubset(self.channel.control_capabilities)

    async def probe_saved_context(self, codec, *, scope, source):
        if not self.supports_saved_context(codec):
            raise CoreError('CAPABILITY_UNSUPPORTED', 'saved_context_link')
        frame = dict(contract_revision=codec.link_revision, type=codec.probe_type, **self.channel.identity(),
                     request_id=f'saved_{codec.name}_' + secrets.token_hex(16), scope=scope, source=source)
        available = await self._exchange(frame, codec.encode_probe(frame), codec.observed_type, self._timeout)
        return available is True

    async def _pi_request(self, action, stream, *, timeout=None, **payload):
        if not self.pi_enabled:
            raise CoreError('CAPABILITY_UNSUPPORTED', 'pi_presentation_link')
        frame = dict(contract_revision=PI_PRESENTATION_LINK_REVISION, type=action, **self.channel.identity(),
                     request_id='viewer_pi_' + secrets.token_hex(16), stream_id=stream, **payload)
        result = await self._exchange(frame, encode_pi_presentation_frame(frame), PI_PRESENTATION_RESULT,
                                      self._timeout if timeout is None else timeout)
        if result is None or result['state'] == 'refused':
            raise CoreError('SESSION_UNKNOWN', 'pi_presentation_link')
        return result

    async def probe_pi(self, *, scope, target):
        response = await self._pi_request(PI_PRESENTATION_PROBE, 'piv_' + secrets.token_hex(16), scope=scope, target=target)
        if response['state'] != 'available':
            raise CoreError('SESSION_UNKNOWN', 'pi_presentation_link')

    async def _claude_request(self, action, stream, *, timeout=None, **payload):
        if not self.claude_enabled:
            raise CoreError('CAPABILITY_UNSUPPORTED', 'claude_presentation_link')
        frame = dict(contract_revision=CLAUDE_PRESENTATION_LINK_REVISION, type=action, **self.channel.identity(),
                     request_id='viewer_claude_' + secrets.token_hex(16), stream_id=stream, **payload)
        response = await self._exchange(frame, encode_claude_presentation_frame(frame), CLAUDE_PRESENTATION_RESULT,
                                        self._timeout if timeout is None else timeout)
        if response is None or response['state'] == 'refused':
            raise CoreError('SESSION_UNKNOWN', 'claude_presentation_link')
        return response

    async def probe_claude(self, *, scope, target):
        response = await self._claude_request(CLAUDE_PRESENTATION_PROBE, 'clv_' + secrets.token_hex(16),
                                              scope=scope, target=target)
        if response['state'] != 'available':
            raise CoreError('SESSION_UNKNOWN', 'claude_presentation_link')

    @asynccontextmanager
    async def open_claude(self, *, scope, target):
        stream = 'clv_' + secrets.token_hex(16)

        async def read():
            response = await self._claude_request(CLAUDE_PRESENTATION_NEXT, stream)
            state = response['state']
            if state in ('idle', 'closed'):
                return b'' if state == 'idle' else None
            if state == 'output':
                return decode_claude_presentation_output(response)
            raise CoreError('SCOPE_MISMATCH', 'claude_presentation_link')

        try:
            response = await self._claude_request(CLAUDE_PRESENTATION_OPEN, stream, scope=scope, target=target)
            if response['state'] != 'opened':
                raise CoreError('SESSION_UNKNOWN', 'claude_presentation_link')
            yield read
        finally:
            if not self.closed:
                with anyio.CancelScope(shield=True), suppress(CoreError):
                    await self._claude_request(CLAUDE_PRESENTATION_CLOSE, stream, timeout=min(self._timeout, 1.5))

    @asynccontextmanager
    async def open_pi(self, *, scope, target, columns, rows, editor):
        stream = 'piv_' + secrets.token_hex(16)
        sequence = read_sequence = 0

        async def read():
            nonlocal read_sequence
            while True:
                response = await self._pi_request(PI_PRESENTATION_NEXT, stream)
                state = response['state']
                if state == 'idle':
                    continue
                if state == 'closed':
                    return None
                if state == 'output':
                    return decode_pi_presentation_output(response)
                if (state == 'draft' and editor and response['sequence'] == read_sequence + 1
                        and response['sequence'] <= sequence):
                    read_sequence += 1
                    return decode_pi_presentation_output(response)
                raise CoreError('SCOPE_MISMATCH', 'pi_presentation_link')

        async def edit(key, *, text):
            nonlocal sequence
            sequence += 1
            response = await self._pi_request(PI_PRESENTATION_EDIT, stream, key=key, text=text, sequence=sequence)
            if response['state'] != 'edited':
                raise CoreError('SCOPE_MISMATCH', 'pi_presentation_link')

        try:
            response = await self._pi_request(PI_PRESENTATION_OPEN, stream, scope=scope, target=target,
                                               columns=columns, rows=rows, editor=editor)
            if response['state'] != 'opened':
                raise CoreError('SESSION_UNKNOWN', 'pi_presentation_link')
            yield read, edit if editor else None
        finally:
            if not self.closed:
                with anyio.CancelScope(shield=True), suppress(CoreError):
                    await self._pi_request(PI_PRESENTATION_CLOSE, stream, timeout=min(self._timeout, 1.5))

    async def _exchange(self, frame, raw, result_type, timeout):
        pending = self._pending[result_type]
        if self.closed or len(pending) >= (4 if result_type == PRESENTATION_RESULT or result_type in SAVED_CONTEXT_RESULTS else 8):
            raise CoreError('SESSION_UNKNOWN', 'presentation_link')
        request_id = frame['request_id']
        future = asyncio.get_running_loop().create_future()
        pending[request_id] = (future, presentation_request_hash(frame), frame.get('stream_id'))
        try:
            async with asyncio.timeout(timeout):
                await self._send(raw.decode('utf-8'))
                context = await future
            if self.closed:
                raise CoreError('SESSION_UNKNOWN', 'presentation_link')
            return context
        except (TimeoutError, OSError, RuntimeError) as error:
            raise CoreError('SESSION_UNKNOWN', 'presentation_link') from error
        finally:
            pending.pop(request_id, None)
            future.cancel()

    def accept_result(self, frame):
        pending = self._pending.get(frame['type'])
        if (pending is None
                or any(frame[key] != value for key, value in self.channel.identity().items())):
            raise CoreError('SCOPE_MISMATCH', 'presentation_reply')
        retained = pending.get(frame['request_id'])
        if retained is None or self.closed:
            return
        future, expected_hash, stream = retained
        if frame['request_hash'] != expected_hash or frame.get('stream_id') != stream:
            raise CoreError('SCOPE_MISMATCH', 'presentation_reply')
        if not future.done():
            field = ('available' if frame['type'] in SAVED_CONTEXT_RESULTS
                     else 'context' if frame['type'] == PRESENTATION_RESULT else 'result')
            future.set_result(frame[field])

    def disconnect(self):
        self.closed = True
        for pending in self._pending.values():
            for future, _, _ in pending.values():
                if not future.done():
                    future.set_result(None)
