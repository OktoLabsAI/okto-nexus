"""Open the approved remote Pi renderer under a current operator attachment."""

import asyncio
from contextlib import aclosing, asynccontextmanager
from dataclasses import asdict

from nexus_connector_core import CoreError

from ..domain.attention import digest
from ..domain.presentation_protocol import REMOTE_PI_AUDIENCE
from ..errors import OktoNexusError
from .execution_native_session_mapping import reviewed_pi_presentation_context
from .remote_presentation_owner import RemotePresentationOwner


class RemotePiPresentation(RemotePresentationOwner):
    @staticmethod
    def _supports(mapping, link):
        return link.pi_enabled and reviewed_pi_presentation_context(mapping)

    def capability_revision(self, uow, scope, author, access, audience, *, next_turn_revision):
        if author.surface != 'native_terminal' or access not in ('read', 'write') or audience != REMOTE_PI_AUDIENCE:
            return None
        try:
            mapping, lease_scope, link = self._select(uow, scope)
        except (CoreError, OktoNexusError):
            return None
        context = {'mapping': asdict(mapping), 'lease_scope': lease_scope, 'link': link.instance,
                   'access': access, 'audience': audience}
        if access == 'write':
            if next_turn_revision is None or (revision := next_turn_revision(uow, scope)) is None:
                return None
            context['next_turn_revision'] = revision
        return 'sha256:' + digest(context)

    async def _require(self, selected, scope, author):
        if await asyncio.to_thread(self._authorize, scope, author) != selected:
            raise CoreError('STALE_GENERATION', 'remote_pi_presentation')

    async def prove(self, scope, *, author):
        selected = await asyncio.to_thread(self._authorize, scope, author)
        mapping, lease_scope, link = selected
        await link.probe_pi(scope=lease_scope, target=self._target(mapping))
        await self._require(selected, scope, author)
        return mapping, (lease_scope, link.instance)

    @asynccontextmanager
    async def _open(self, scope, *, author, columns, rows, editor):
        selected = await asyncio.to_thread(self._authorize, scope, author)
        mapping, lease_scope, link = selected
        async with link.open_pi(scope=lease_scope, target=self._target(mapping), columns=columns, rows=rows,
                                editor=editor) as (read, edit):
            await self._require(selected, scope, author)

            async def guarded_read():
                value = await read()
                await self._require(selected, scope, author)
                return value

            async def guarded_edit(key, *, text):
                await self._require(selected, scope, author)
                await edit(key, text=text)

            yield guarded_read, guarded_edit

    @asynccontextmanager
    async def open_renderer(self, scope, *, author, columns, rows):
        async with self._open(scope, author=author, columns=columns, rows=rows, editor=False) as (read, _):
            async def frames():
                while (value := await read()) is not None:
                    yield value

            async with aclosing(frames()) as output:
                yield output

    @asynccontextmanager
    async def open_editor(self, scope, *, author, columns, rows):
        async with self._open(scope, author=author, columns=columns, rows=rows, editor=True) as (read, edit):
            yield edit, read
