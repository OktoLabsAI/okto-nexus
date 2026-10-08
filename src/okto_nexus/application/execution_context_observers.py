"""Read observed host ownership; a declaration never qualifies an observer."""


def live_observers(uow, endpoint, profile):
    if not profile or not profile['enabled'] or 'context_without_execution' in profile['config'].get('disabled_capabilities', ()):
        return []
    return [dict(row) for row in uow.connection.execute(
        'SELECT s.session_id,o.owner_epoch,o.server_id AS canonical_server_id,'
        'o.executor_id AS canonical_executor_id FROM execution_context_observers o '
        'JOIN execution_sessions s USING(server_id,executor_id,session_id) '
        'JOIN execution_bindings b USING(server_id,executor_id,binding_id) '
        'JOIN execution_executors x USING(server_id,executor_id) '
        "WHERE b.endpoint_id=? AND o.qualified=1 AND s.lifecycle_state='READY' AND s.lease_state='ACTIVE' "
        "AND x.kind='embedded' AND x.control_state='CONTROL_READY' AND x.revoked_at IS NULL "
        'AND x.owner_instance_id=o.owner_instance_id AND x.generation=o.executor_generation '
        'AND o.profile_revision=?', (endpoint['endpoint_id'], profile['revision']))]
