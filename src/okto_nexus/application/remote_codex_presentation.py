"""Read an exact managed Codex context with current human and host authority."""

import asyncio
from dataclasses import asdict

from nexus_connector_core import CoreError
from pydantic import ValidationError

from ..domain.attention import digest
from ..domain.presentation_protocol import (
    CODEX_VIEWER_WINDOWS_SHA256,
    REMOTE_CODEX_AUDIENCE,
)
from ..errors import OktoNexusError
from .codex_viewer_protocol import CodexViewerContext
from .execution_native_session_mapping import reviewed_codex_context
from .remote_presentation_owner import RemotePresentationOwner


class RemoteCodexPresentation(RemotePresentationOwner):
    @staticmethod
    def _supports(mapping, link):
        return link.codex_enabled and reviewed_codex_context(mapping)

    def capability_revision(self, uow, scope, author, access, audience, *, next_turn_revision):
        if author.surface != 'native_terminal' or access not in ('read', 'write') or audience != REMOTE_CODEX_AUDIENCE:
            return None
        try:
            mapping, lease_scope, link = self._select(uow, scope)
        except (CoreError, OktoNexusError):
            return None
        context = {'mapping': asdict(mapping), 'lease_scope': lease_scope, 'link': link.instance,
                   'viewer': CODEX_VIEWER_WINDOWS_SHA256, 'audience': audience}
        if access == 'write':
            if next_turn_revision is None or (revision := next_turn_revision(uow, scope)) is None:
                return None
            context.update(access=access, next_turn_revision=revision)
        return 'sha256:' + digest(context)

    async def prove(self, scope, *, author):
        mapping, lease_scope, link = await asyncio.to_thread(self._authorize, scope, author)
        return mapping, (lease_scope, link.instance)

    async def read(self, scope, author):
        selected = await asyncio.to_thread(self._authorize, scope, author)
        mapping, lease_scope, link = selected
        value = await link.read_codex(scope=lease_scope, target=self._target(mapping), thread_id=mapping.codex_thread_id)
        if await asyncio.to_thread(self._authorize, scope, author) != selected or link.closed:
            raise CoreError('STALE_GENERATION', 'remote_presentation')
        try:
            context = CodexViewerContext.model_validate(value)
        except ValidationError:
            raise CoreError('SESSION_CONFLICT', 'remote_presentation') from None
        if context.thread_id != mapping.codex_thread_id or context.status not in ('idle', 'active'):
            raise CoreError('SESSION_CONFLICT', 'remote_presentation')
        return mapping, context
