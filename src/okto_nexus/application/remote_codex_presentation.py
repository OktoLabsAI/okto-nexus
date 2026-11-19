"""Read an exact managed Codex context with current human and host authority."""

import asyncio
import json
from dataclasses import asdict

from nexus_connector_core import CoreError, NativeSessionTarget
from pydantic import ValidationError

from ..adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from ..adapters.outbound.sqlite.execution_leases import SqliteExecutionLeaseRepository
from ..adapters.outbound.sqlite.session_interaction import (
    _current_session,
    _scope_params,
)
from ..domain.attention import digest
from ..domain.presentation_protocol import (
    CODEX_VIEWER_WINDOWS_SHA256,
    REMOTE_CODEX_AUDIENCE,
)
from ..errors import OktoNexusError
from .codex_viewer_protocol import CodexViewerContext
from .execution_leases import require_execution_lane
from .execution_native_facts import stamp
from .execution_native_session_mapping import (
    read_managed_native_session,
    reviewed_codex_context,
)


class RemoteCodexPresentation:
    def __init__(self, factory, *, authority_fence, clock):
        self.factory, self._authority_fence, self._clock = factory, authority_fence, clock
        self.links = {}

    def _authorize(self, scope, author):
        with self._authority_fence() as human, self.factory.unit_of_work(write=False) as uow:
            if author.surface != 'native_terminal' or not human(author.authority_ref):
                raise CoreError('NOT_AUTHORIZED', 'remote_presentation')
            return self._select(uow, scope)

    def _select(self, uow, scope):
        key = scope.session.server_id, scope.session.executor_id
        link = self.links.get(key)
        if link is None or link.closed:
            raise CoreError('SESSION_UNKNOWN', 'remote_presentation')
        channel = link.channel
        params = _scope_params(scope)
        repo = SqliteExecutionLeaseRepository()
        if not _current_session(uow.connection, params, require_active_lease=True):
            raise CoreError('SESSION_UNKNOWN', 'remote_presentation')
        owner, lease = repo.authority(uow, params), repo.effective(uow, params)
        connection = (channel.connection_id, channel.connection_generation)
        now = stamp(self._clock.now_iso())
        if (owner is None or owner['kind'] != 'remote' or owner['control_state'] != 'CONTROL_READY'
                or owner['revoked_at'] is not None or (owner['owner_instance_id'], owner['generation']) != connection
                or not owner['enabled'] or owner['activation_state'] != 'approved' or owner['health'] == 'quarantined'
                or owner['workspace_status'] != 'READY' or owner['realization_status'] != 'READY'
                or owner['realization_revision'] != owner['current_realization_revision']
                or lease is None or lease['status'] != 'ACTIVE' or lease['applied_at'] is None
                or not lease['scope_json'] or stamp(lease['valid_until_server']) <= now
                or (lease['connection_id'], lease['connection_generation']) != connection):
            raise CoreError('SESSION_UNKNOWN', 'remote_presentation')
        lease_scope = json.loads(lease['scope_json'])
        params['session_owner_generation'] = params.pop('owner_generation')
        server, revisions, _ = current_agent_revisions(self.factory, agent_id=scope.agent_id, uow=uow, persist=False)
        params |= {'binding_revision': owner['binding_revision'], 'authorization_revision': revisions.authorization,
                   'configuration_revision': revisions.configuration, 'credential_epoch': revisions.credential_epoch}
        if server != scope.session.server_id or lease_scope != params:
            raise CoreError('STALE_GENERATION', 'remote_presentation')
        require_execution_lane(uow, scope=lease_scope, channel=channel, now=now)
        mapping = read_managed_native_session(uow, scope)
        if (mapping is None or not reviewed_codex_context(mapping) or not mapping.stream_epoch
                or (mapping.receipt_connection_id, mapping.receipt_connection_generation) != connection):
            raise CoreError('CAPABILITY_UNSUPPORTED', 'remote_presentation')
        return mapping, lease_scope, link

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
        target = NativeSessionTarget(mapping.opening_operation_id, mapping.adapter_id, mapping.native_session_id,
                                     mapping.stream_epoch)
        value = await link.read_codex(scope=lease_scope, target=asdict(target), thread_id=mapping.codex_thread_id)
        if await asyncio.to_thread(self._authorize, scope, author) != selected or link.closed:
            raise CoreError('STALE_GENERATION', 'remote_presentation')
        try:
            context = CodexViewerContext.model_validate(value)
        except ValidationError:
            raise CoreError('SESSION_CONFLICT', 'remote_presentation') from None
        if context.thread_id != mapping.codex_thread_id or context.status not in ('idle', 'active'):
            raise CoreError('SESSION_CONFLICT', 'remote_presentation')
        return mapping, context
