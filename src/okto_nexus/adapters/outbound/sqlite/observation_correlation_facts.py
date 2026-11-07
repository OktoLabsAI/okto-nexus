"""Exact, passive canonical joins; never compose Core or read its journal."""


SESSION_SQL = """SELECT s.server_id,s.executor_id,s.session_id,s.open_operation_id,
    s.binding_id,s.workspace_binding_id,s.workspace_id,s.owner_generation,s.stream_epoch,
    s.lifecycle_state,s.lease_state,ex.kind,ex.control_state,ex.revoked_at,
    ex.owner_instance_id,ex.generation AS executor_generation,
    o.subject_agent_id,o.workspace_id AS opening_workspace_id,o.action AS opening_action,
    o.binding_id AS opening_binding_id,o.workspace_binding_id AS opening_workspace_binding_id,
    o.session_id AS opening_session_id,o.expected_revisions_json,
    b.binding_revision,b.workspace_binding_id AS binding_workspace_binding_id,
    b.realization_revision,r.revision AS current_realization_revision,r.status AS realization_status,
    r.subject_agent_id AS realization_agent_id,r.workspace_binding_id AS realization_workspace_binding_id,
    ep.agent_id AS endpoint_agent_id,ep.workspace_id AS endpoint_workspace_id,
    ep.protocol,ep.enabled AS endpoint_enabled,ep.activation_state,ep.health,
    wb.workspace_id AS bound_workspace_id,wb.status AS workspace_status
    FROM execution_sessions s
    JOIN execution_installation install ON install.singleton=1 AND install.server_id=s.server_id
    JOIN execution_executors ex USING(server_id,executor_id)
    JOIN execution_operations o ON o.server_id=s.server_id AND o.executor_id=s.executor_id
        AND o.operation_id=s.open_operation_id
    JOIN execution_bindings b ON b.server_id=s.server_id AND b.executor_id=s.executor_id
        AND b.binding_id=s.binding_id
    JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id
    JOIN execution_workspace_bindings wb ON wb.server_id=s.server_id AND wb.executor_id=s.executor_id
        AND wb.workspace_binding_id=s.workspace_binding_id
    JOIN execution_realizations r ON r.server_id=b.server_id AND r.executor_id=b.executor_id
        AND r.realization_ref=b.realization_ref
"""


class SqliteObservationCorrelationFacts:
    def session(self, uow, *, server_id, executor_id, session_id):
        row = uow.connection.execute(SESSION_SQL +
            ' WHERE s.server_id=? AND s.executor_id=? AND s.session_id=?',
            (server_id, executor_id, session_id)).fetchone()
        return dict(row) if row is not None else None
