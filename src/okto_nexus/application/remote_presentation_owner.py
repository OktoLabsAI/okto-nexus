"""Bind a presentation to the current remote owner and exact managed session."""

import json
from dataclasses import asdict

from nexus_connector_core import CoreError, NativeSessionTarget

from ..adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from ..adapters.outbound.sqlite.execution_leases import SqliteExecutionLeaseRepository
from ..adapters.outbound.sqlite.session_interaction import (
    _current_session,
    _scope_params,
)
from .execution_leases import require_execution_lane
from .execution_native_facts import stamp
from .execution_native_session_mapping import read_managed_native_session


class RemotePresentationOwner:
    def __init__(self, factory, *, authority_fence, clock, links=None):
        self.factory, self._authority_fence, self._clock = factory, authority_fence, clock
        self.links = {} if links is None else links

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
        if (mapping is None or not mapping.stream_epoch or not self._supports(mapping, link)
                or (mapping.receipt_connection_id, mapping.receipt_connection_generation) != connection):
            raise CoreError('CAPABILITY_UNSUPPORTED', 'remote_presentation')
        return mapping, lease_scope, link

    @staticmethod
    def _target(mapping):
        return asdict(NativeSessionTarget(mapping.opening_operation_id, mapping.adapter_id, mapping.native_session_id,
                                          mapping.stream_epoch))
