"""Serve bounded history reads on one authenticated Codex presentation."""

import asyncio
from contextlib import asynccontextmanager

from ..domain.runtime_context import RuntimeRequestContext
from ..errors import ErrorCode, OktoNexusError
from .codex_presenter_history import read_codex_history_snapshot
from .codex_presenter_requests import codex_history_page
from .codex_viewer_protocol import CodexViewerContext


class CodexPresenterHistoryChannel:
    """Keep one capture for the channel's cursor lifetime."""

    def __init__(self, *, broker, prove_owner, access, scope, author, attachment, audience, channel_id):
        self._broker = broker
        self._prove_owner = prove_owner
        self._access = access
        self._subject = {'scope': scope, 'author': author, 'attachment': attachment,
                         'audience': audience, 'channel_id': channel_id}
        self._snapshot_lock = asyncio.Lock()
        self._owner = None
        self._snapshot = None

    async def _authorize(self):
        await asyncio.to_thread(self._broker.require_active, **self._subject)

    @asynccontextmanager
    async def _bound_owner(self):
        async with self._snapshot_lock:
            await self._authorize()
            current = await self._prove_owner(self._subject['scope'])
            if current[0].codex_thread_id is None:
                raise OktoNexusError(ErrorCode.CONFLICT, 'The exact Codex thread is unavailable.', {})
            if self._owner is not None and current != self._owner:
                raise OktoNexusError(ErrorCode.CONFLICT, 'The presentation owner changed.', {})
            yield current[0]
            if current != await self._prove_owner(self._subject['scope']):
                raise OktoNexusError(ErrorCode.CONFLICT, 'The presentation owner changed.', {})
            await self._authorize()
            self._owner = current

    async def page(self, *, method, params):
        async with self._bound_owner() as mapping:
            request = codex_history_page(method=method, params=params, native_thread_id=mapping.codex_thread_id)
            snapshot = self._snapshot if self._snapshot is not None else await self._capture(mapping)
            result = snapshot.page(request)
        self._snapshot = snapshot
        return result

    async def viewer_context(self, read_context):
        async with self._bound_owner() as mapping:
            context = await read_context(self._subject['scope'])
            if not isinstance(context, CodexViewerContext) or context.thread_id != mapping.codex_thread_id:
                raise OktoNexusError(ErrorCode.CONFLICT, 'The exact Codex viewer context is unavailable.', {})
            return context

    async def _capture(self, mapping):
        context = RuntimeRequestContext('operator', 'operator_session', trusted_local_operator=True)
        return await asyncio.to_thread(read_codex_history_snapshot, self._broker.factory,
                                       mapping=mapping, access=self._access, context=context)
