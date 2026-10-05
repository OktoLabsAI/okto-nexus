"""Current canonical binding facts, without provider discovery or execution."""

from contextlib import nullcontext

from ..adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from ..errors import ErrorCode, OktoNexusError
from .execution_inventory_revalidation import accepts_binding


def read_execution_binding(factory, *, server_id, binding_id, context, access, uow=None):
    if not isinstance(binding_id, str) or not 1 <= len(binding_id) <= 160:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid binding ID.", {})
    # Revision materialization shares the authorization snapshot. As with /me,
    # it may advance revision counters, but never creates authority or work.
    with nullcontext(uow) if uow is not None else factory.unit_of_work() as uow:
        operator = access.authenticate(context, uow=uow, require_feature=False)
        conn = uow.connection
        row = conn.execute(
            "SELECT b.*,ep.agent_id,ep.workspace_id,ep.adapter_id,ep.enabled,"
            "ep.activation_state,ep.protocol,ep.health,a.is_active,"
            "e.revoked_at,p.enabled AS profile_enabled,"
            "r.revision AS actual_realization_revision,r.status AS realization_status,"
            "r.subject_agent_id,r.workspace_binding_id AS realization_workspace_binding,"
            "r.candidate_ref AS realization_candidate,r.inventory_revision AS realization_inventory,"
            "w.status AS workspace_status,w.workspace_id AS bound_workspace_id,"
            "i.inventory_revision AS current_inventory_revision,"
            "m.enabled AS method_enabled "
            "FROM execution_bindings b JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id "
            "JOIN agents a ON a.agent_id=ep.agent_id "
            "JOIN execution_executors e ON e.server_id=b.server_id AND e.executor_id=b.executor_id "
            "LEFT JOIN runtime_profiles p ON p.profile_id=ep.profile_id "
            "LEFT JOIN execution_realizations r ON r.server_id=b.server_id AND r.executor_id=b.executor_id "
            "AND r.realization_ref=b.realization_ref "
            "LEFT JOIN execution_workspace_bindings w ON w.server_id=b.server_id "
            "AND w.executor_id=b.executor_id AND w.workspace_binding_id=b.workspace_binding_id "
            "LEFT JOIN execution_inventory_current i ON i.server_id=b.server_id AND i.executor_id=b.executor_id "
            "LEFT JOIN agent_connection_methods m ON m.agent_id=ep.agent_id AND m.method=ep.adapter_id "
            "WHERE b.server_id=? AND b.binding_id=? AND (ep.agent_id=? OR ?)",
            (server_id, binding_id, context.actor_agent_id, operator)).fetchone()
        if row is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, "The binding was not found in this scope.", {})
        _, revisions, _ = current_agent_revisions(factory, agent_id=row['agent_id'],
                                                  uow=uow, require_active=False)
        if (row['revoked_at'] is not None or row['activation_state'] == 'revoked'
                or row['realization_status'] == 'REVOKED' or row['workspace_status'] == 'REVOKED'):
            state = 'REVOKED'
        elif (not row['is_active'] or not row['enabled'] or row['profile_enabled'] == 0
              or row['method_enabled'] == 0):
            state = 'DISABLED'
        elif (row['activation_state'] != 'approved' or
              row['realization_status'] == 'PENDING_APPROVAL' or row['workspace_status'] == 'PENDING_APPROVAL'):
            state = 'PENDING_REVIEW'
        elif (row['protocol'] != 'nxl-r4' or row['profile_enabled'] is None
              or row['health'] == 'quarantined' or row['realization_status'] != 'READY'
              or row['workspace_status'] != 'READY'
              or row['actual_realization_revision'] != row['realization_revision']
              or row['subject_agent_id'] != row['agent_id']
              or row['realization_workspace_binding'] != row['workspace_binding_id']
              or row['bound_workspace_id'] != row['workspace_id']
              or row['realization_candidate'] != row['candidate_ref']
              or row['realization_inventory'] != row['inventory_revision']
              or not accepts_binding(conn, row, row['current_inventory_revision'], server_id, row['executor_id'])):
            state = 'STALE'
        else:
            # Consent persists across executor disconnection. APPROVED is not a
            # promise of technical freshness, a grant, or permission to start.
            state = 'APPROVED'
        result = {name: row[name] for name in (
            'binding_id', 'server_id', 'executor_id', 'agent_id', 'endpoint_id',
            'workspace_id', 'workspace_binding_id', 'adapter_id', 'candidate_ref',
            'inventory_revision', 'realization_ref', 'realization_revision', 'binding_revision')}
        return {**result, 'authorization_revision': revisions.authorization,
                'configuration_revision': revisions.configuration, 'state': state}
