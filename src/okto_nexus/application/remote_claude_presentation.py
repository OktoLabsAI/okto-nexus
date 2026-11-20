"""Read the exact managed Claude terminal through the Connector's outbound link."""

import asyncio
from contextlib import aclosing, asynccontextmanager
from dataclasses import asdict

from nexus_connector_core import CoreError

from ..domain.attention import digest
from ..domain.presentation_protocol import REMOTE_CLAUDE_AUDIENCE
from ..errors import OktoNexusError
from .execution_native_session_mapping import reviewed_claude_terminal_context
from .remote_presentation_owner import RemotePresentationOwner


class RemoteClaudePresentation(RemotePresentationOwner):
    @staticmethod
    def _supports(mapping, link):
        return link.claude_enabled and reviewed_claude_terminal_context(mapping)

    def capability_revision(self, uow, scope, author, access, audience):
        if author.surface != 'native_terminal' or access != 'read' or audience != REMOTE_CLAUDE_AUDIENCE:
            return None
        try:
            mapping, lease_scope, link = self._select(uow, scope)
        except (CoreError, OktoNexusError):
            return None
        return 'sha256:' + digest({'mapping': asdict(mapping), 'lease_scope': lease_scope,
                                  'link': link.instance, 'audience': audience})

    async def _require(self, selected, scope, author):
        if await asyncio.to_thread(self._authorize, scope, author) != selected:
            raise CoreError('STALE_GENERATION', 'remote_claude_presentation')

    async def prove(self, scope, *, author):
        selected = await asyncio.to_thread(self._authorize, scope, author)
        mapping, lease_scope, link = selected
        await link.probe_claude(scope=lease_scope, target=self._target(mapping))
        await self._require(selected, scope, author)
        return mapping, (lease_scope, link.instance)

    @asynccontextmanager
    async def open_reader(self, scope, *, author):
        selected = await asyncio.to_thread(self._authorize, scope, author)
        mapping, lease_scope, link = selected
        async with link.open_claude(scope=lease_scope, target=self._target(mapping)) as read:
            await self._require(selected, scope, author)

            async def frames():
                while True:
                    value = await read()
                    await self._require(selected, scope, author)
                    if value is None:
                        return
                    if value:
                        yield value

            async with aclosing(frames()) as output:
                yield output
