"""Current technical authority for the Core capacity port, without a fake actor.

Business eligibility and an automatic claimant's policy/grant remain Server
use cases. This adapter checks the existing connection, approved binding,
inventory and session facts before a technical reservation can be observed or
consumed. It never creates an intent, execution grant, session or provider.
"""
import asyncio
from datetime import datetime, timezone
import json
import time

from nexus_connector_core import CapacityRequest

from .execution_agent_revisions import current_agent_revisions
from .execution_leases import SqliteExecutionLeaseRepository
from ....application.execution_agent_recovery import agent_recovering
from ....application.execution_leases import require_execution_lane
from ....application.execution_inventory_revalidation import accepts_binding
from ....application.executor_inventory import load_current_executor_inventory
from ....errors import OktoNexusError


class SqliteExecutionCapacityAuthority:
    def __init__(self, *, factory, channel, fresh_publications, verify_owner=None,
                 now=lambda: datetime.now(timezone.utc), monotonic=time.monotonic):
        self.factory, self.channel, self.fresh = factory, channel, fresh_publications
        self.verify_owner, self.now, self.monotonic = verify_owner, now, monotonic
        self.leases = SqliteExecutionLeaseRepository()

    async def check_capacity_scope(self, request, *, action):
        if type(request) is not CapacityRequest or action not in ('assess', 'reserve', 'get', 'consume', 'release', 'bind'):
            return 'NOT_AUTHORIZED'
        return await asyncio.to_thread(self._check, request, action)

    def _check(self, request, action):
        scope, channel = request.scope, self.channel
        if (scope.server_id, scope.executor_id) != (channel.server_id, channel.executor_id):
            return 'NOT_AUTHORIZED'
        try:
            with self.factory.unit_of_work() as uow:
                if self.verify_owner is not None:
                    self.verify_owner(uow=uow)
                conn = uow.connection
                executor = conn.execute('SELECT kind,control_state FROM execution_executors '
                    'WHERE server_id=? AND executor_id=? AND owner_instance_id=? AND generation=? AND revoked_at IS NULL',
                    (channel.server_id, channel.executor_id, channel.connection_id, channel.connection_generation)).fetchone()
                if executor is None:
                    return 'NOT_AUTHORIZED'
                # The authenticated owner can reconcile its exact historical
                # attempts after a subject/selection revocation. No new effect.
                if action in ('get', 'release'):
                    return 'AVAILABLE' if executor['control_state'] in ('CONTROL_READY', 'RECOVERING') else 'RECOVERING'
                if scope.connection_generation != channel.connection_generation:
                    return 'STALE_OBSERVATION'
                if executor['control_state'] != 'CONTROL_READY' or agent_recovering(
                        conn, channel.server_id, channel.executor_id, scope.agent_id):
                    return 'RECOVERING'
                server_id, revisions, _ = current_agent_revisions(self.factory, agent_id=scope.agent_id, uow=uow)
                if server_id != channel.server_id or (revisions.authorization, revisions.configuration, revisions.credential_epoch) != (
                        scope.authorization_revision, scope.configuration_revision, scope.credential_epoch):
                    return 'STALE_OBSERVATION'
                binding = conn.execute(
                    'SELECT b.*,ep.agent_id,ep.adapter_id,ep.protocol,ep.enabled,ep.activation_state,ep.health,ep.profile_id,'
                    'w.workspace_id,w.status AS workspace_status,r.subject_agent_id,r.status AS realization_status,'
                    'r.workspace_binding_id AS realized_workspace_binding,r.revision AS current_realization_revision,'
                    'p.enabled AS profile_enabled FROM execution_bindings b '
                    'JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id '
                    'JOIN runtime_profiles p ON p.profile_id=ep.profile_id '
                    'JOIN execution_workspace_bindings w ON w.server_id=b.server_id AND w.executor_id=b.executor_id '
                    'AND w.workspace_binding_id=b.workspace_binding_id '
                    'JOIN execution_realizations r ON r.server_id=b.server_id AND r.executor_id=b.executor_id '
                    'AND r.realization_ref=b.realization_ref WHERE b.server_id=? AND b.executor_id=? AND b.binding_id=?',
                    (scope.server_id, scope.executor_id, scope.binding_id)).fetchone()
                if (binding is None or binding['agent_id'] != scope.agent_id or binding['subject_agent_id'] != scope.agent_id
                        or binding['workspace_id'] != scope.workspace_id or binding['workspace_binding_id'] != scope.workspace_binding_id
                        or binding['realized_workspace_binding'] != scope.workspace_binding_id
                        or binding['protocol'] != 'nxl-r4' or not binding['enabled'] or not binding['profile_enabled']
                        or binding['activation_state'] != 'approved' or binding['health'] == 'quarantined'):
                    return 'NOT_AUTHORIZED'
                if (binding['binding_revision'] != scope.binding_revision or binding['workspace_status'] != 'READY'
                        or binding['realization_status'] != 'READY'
                        or binding['realization_revision'] != binding['current_realization_revision']):
                    return 'STALE_OBSERVATION'
                if executor['kind'] == 'remote':
                    require_execution_lane(uow, scope=scope.to_dict(), channel=channel, now=self.now())
                inventory = self.leases.inventory(uow, scope.to_dict())
                fresh = self.fresh.get((scope.server_id, scope.executor_id))
                if (inventory is None or fresh is None or fresh[0] != inventory['publication_sequence']
                        or not accepts_binding(conn, binding, inventory['inventory_revision'], scope.server_id, scope.executor_id)
                        or inventory['observation_age_ms'] + max(0, int((self.monotonic() - fresh[1]) * 1000)) >= 120000):
                    return 'STALE_OBSERVATION'
                snapshot = load_current_executor_inventory(inventory['canonical_projection'])
                if not any(item['adapter_id'] == binding['adapter_id'] and item['candidate_ref'] == binding['candidate_ref']
                           for item in snapshot['evidence']):
                    return 'STALE_OBSERVATION'
                session = conn.execute('SELECT * FROM execution_sessions WHERE server_id=? AND executor_id=? AND session_id=?',
                    (scope.server_id, scope.executor_id, scope.session_id)).fetchone()
                if session is not None and (session['binding_id'] != scope.binding_id
                        or session['workspace_id'] != scope.workspace_id or session['workspace_binding_id'] != scope.workspace_binding_id
                        or session['owner_generation'] != scope.session_owner_generation):
                    return 'STALE_OBSERVATION'
                if request.unit == 'new_session':
                    from ....application.execution_identity_owner import require_identity_host
                    require_identity_host(conn, server_id=scope.server_id, agent_id=scope.agent_id, executor_id=scope.executor_id)
                    if session is None:
                        return 'AVAILABLE' if scope.session_owner_generation == 1 else 'STALE_OBSERVATION'
                    return 'AVAILABLE' if session['lifecycle_state'] in ('OPEN_PENDING', 'READY') else 'RECOVERING'
                if session is None or session['lifecycle_state'] != 'READY' or session['lease_state'] != 'ACTIVE':
                    return 'RECOVERING'
                lease = self.leases.effective(uow, scope.to_dict())
                if (lease is None or lease['status'] != 'ACTIVE' or lease['connection_id'] != channel.connection_id
                        or lease['connection_generation'] != channel.connection_generation
                        or 'turn.submit' not in json.loads(lease['allowed_actions_json'])
                        or datetime.fromisoformat(lease['valid_until_server'].replace('Z', '+00:00')) <= self.now()):
                    return 'NOT_AUTHORIZED'
                lease_scope = json.loads(lease['scope_json'])
                if any(lease_scope.get(name) != getattr(scope, name) for name in (
                        'server_id', 'executor_id', 'binding_id', 'agent_id', 'workspace_id', 'workspace_binding_id',
                        'session_id', 'session_owner_generation', 'authorization_revision', 'configuration_revision',
                        'binding_revision', 'credential_epoch')):
                    return 'STALE_OBSERVATION'
                grant = self.leases.source_grant(uow, lease['grant_id'])
                if grant is None or grant['revoked_at'] is not None or (not grant['no_expiry'] and
                        datetime.fromisoformat(grant['expires_at'].replace('Z', '+00:00')) <= self.now()):
                    return 'NOT_AUTHORIZED'
                return 'AVAILABLE'
        except OktoNexusError:
            return 'NOT_AUTHORIZED'
