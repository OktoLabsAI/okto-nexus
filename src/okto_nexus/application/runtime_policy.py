"""Global runtime defaults with explicit, independently inheritable agent overrides."""
from ..errors import ErrorCode, OktoNexusError


def defaults(conn):
    row = dict(conn.execute('SELECT runtime_enabled,session_policy,revision,automatic_recovery,inherit_global_mcps FROM runtime_policy_defaults WHERE singleton=1').fetchone())
    row['runtime_enabled'] = bool(row['runtime_enabled'])
    row['automatic_recovery'] = bool(row['automatic_recovery'])
    row['inherit_global_mcps'] = bool(row['inherit_global_mcps'])
    return row


def effective(conn, agent_id):
    global_policy = defaults(conn)
    row = conn.execute('SELECT runtime_enabled,session_policy,inherit_global_mcps FROM agent_runtime_overrides WHERE agent_id=?', (agent_id,)).fetchone()
    return {key: (bool(row[key]) if key in ('runtime_enabled', 'inherit_global_mcps') else row[key])
            if row is not None and row[key] is not None else global_policy[key]
            for key in ('runtime_enabled', 'session_policy', 'inherit_global_mcps')}


def guard(conn, agent_id):
    epoch = conn.execute('SELECT epoch FROM agent_runtime_policy_epochs WHERE agent_id=?', (agent_id,)).fetchone()
    # MCP inheritance is captured in each opening intent; changing the default
    # must not revoke or mutate already-running sessions.
    policy = effective(conn, agent_id)
    return {k: policy[k] for k in ('runtime_enabled', 'session_policy')} | {'epoch': epoch[0] if epoch else 0}


def view(conn, agent_id=None):
    global_policy = defaults(conn)
    if agent_id is None:
        return global_policy
    row = conn.execute('SELECT * FROM agent_runtime_overrides WHERE agent_id=?', (agent_id,)).fetchone()
    result = dict(row) if row else dict(agent_id=agent_id, runtime_enabled=None, session_policy=None, inherit_global_mcps=None, revision=0)
    if result['runtime_enabled'] is not None:
        result['runtime_enabled'] = bool(result['runtime_enabled'])
    if result['inherit_global_mcps'] is not None:
        result['inherit_global_mcps'] = bool(result['inherit_global_mcps'])
    return result | dict(defaults=global_policy, effective=effective(conn, agent_id))


def require_closed(conn, agent_ids):
    for agent_id in agent_ids:
        if conn.execute("SELECT 1 FROM one_shot_calls WHERE agent_id=? AND state IN ('QUEUED','ADMITTED','RUNNING') LIMIT 1",
                        (agent_id,)).fetchone():
            raise OktoNexusError(ErrorCode.CONFLICT,
                'Wait for pending one-shot calls before changing session isolation.', {'agent_id': agent_id})
        bindings = conn.execute('SELECT DISTINCT s.binding_id FROM execution_sessions s JOIN execution_bindings b '
                'USING(server_id,executor_id,binding_id) JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id '
                "WHERE e.agent_id=? AND s.lifecycle_state<>'CLOSED' "
                "AND NOT (s.lifecycle_state='FAILED' AND s.lease_state='CLOSED')", (agent_id,)).fetchall()
        if bindings:
            raise OktoNexusError(ErrorCode.CONFLICT,
                'Close existing sessions for affected agents before changing session isolation.',
                {'reason': 'ACTIVE_SESSIONS', 'agent_id': agent_id,
                 'binding_ids': [row[0] for row in bindings]})


def invalidate(uow, access, agent_ids, now):
    for agent_id in agent_ids:
        uow.connection.execute('INSERT INTO agent_runtime_policy_epochs VALUES(?,1) '
            'ON CONFLICT(agent_id) DO UPDATE SET epoch=epoch+1', (agent_id,))
        endpoint_ids = [row[0] for row in uow.connection.execute('SELECT endpoint_id FROM agent_endpoints WHERE agent_id=?', (agent_id,))]
        access.endpoints.invalidate_configuration(uow, endpoint_ids=endpoint_ids, now=now)


def read_policy(deps, context, agent_id=None):
    from ..bootstrap.execution_authority import build_execution_access
    access = build_execution_access(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        operator = access.authenticate(context, uow=uow, require_feature=False)
        if not operator and (agent_id is None or context.actor_agent_id != agent_id):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Runtime policy is outside this identity.', {})
        if agent_id is not None and access.agents.get(uow, agent_id) is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'Agent does not exist.', {})
        return view(uow.connection, agent_id)


def save_policy(deps, context, *, agent_id=None, changes):
    from ..bootstrap.execution_authority import build_execution_access
    access = build_execution_access(deps)
    if (not isinstance(changes, dict) or set(changes) - {'expected_revision', 'runtime_enabled', 'session_policy', 'automatic_recovery', 'inherit_global_mcps'}
            or not {'expected_revision','runtime_enabled','session_policy'} <= set(changes)
            or 'automatic_recovery' in changes and (agent_id is not None or type(changes['automatic_recovery']) is not bool)
            or 'inherit_global_mcps' in changes and not (type(changes['inherit_global_mcps']) is bool or agent_id is not None and changes['inherit_global_mcps'] is None)
            or type(changes['expected_revision']) is not int or changes['expected_revision'] < (0 if agent_id else 1)
            or not (type(changes['runtime_enabled']) is bool or agent_id is not None and changes['runtime_enabled'] is None)
            or changes['session_policy'] not in (('shared', 'per_sender', 'per_sender_session', 'one_shot', None) if agent_id else ('shared', 'per_sender', 'per_sender_session', 'one_shot'))):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid runtime policy; null means inherit only for agents.', {})
    with deps.connection_factory.unit_of_work() as uow:
        access.authorize_maintenance(context, uow=uow)
        conn = uow.connection
        if agent_id is not None and access.agents.get(uow, agent_id) is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'Agent does not exist.', {})
        current = view(conn, agent_id)
        changes = dict(changes)
        changes.setdefault('inherit_global_mcps', current['inherit_global_mcps'])
        if current['revision'] != changes['expected_revision']:
            raise OktoNexusError(ErrorCode.CONFLICT, 'Runtime policy changed; reload before saving.', {})
        if all(current[key] == changes[key] for key in ('runtime_enabled', 'session_policy', 'inherit_global_mcps')) and (
                agent_id is not None or current['automatic_recovery']==changes.get('automatic_recovery',current['automatic_recovery'])):
            return current
        affected = [agent_id] if agent_id else [row[0] for row in conn.execute('SELECT agent_id FROM agents')]
        before = {aid: effective(conn, aid) for aid in affected}
        if agent_id:
            conn.execute('INSERT INTO agent_runtime_overrides(agent_id,runtime_enabled,session_policy,inherit_global_mcps,revision) VALUES(?,?,?,?,?) ON CONFLICT(agent_id) DO UPDATE SET '
                'runtime_enabled=excluded.runtime_enabled,session_policy=excluded.session_policy,inherit_global_mcps=excluded.inherit_global_mcps,revision=excluded.revision',
                (agent_id, changes['runtime_enabled'], changes['session_policy'], changes['inherit_global_mcps'], current['revision'] + 1))
        else:
            conn.execute('UPDATE runtime_policy_defaults SET runtime_enabled=?,session_policy=?,automatic_recovery=?,inherit_global_mcps=?,revision=revision+1 WHERE singleton=1',
                         (changes['runtime_enabled'], changes['session_policy'],changes.get('automatic_recovery',current['automatic_recovery']),changes['inherit_global_mcps']))
        changed = [aid for aid in affected if before[aid] != effective(conn, aid)]
        require_closed(conn, [aid for aid in changed if before[aid]['session_policy'] != effective(conn, aid)['session_policy']])
        now = deps.clock.now_iso()
        invalidate(uow, access, [aid for aid in changed if any(before[aid][k] != effective(conn, aid)[k]
            for k in ('runtime_enabled', 'session_policy'))], now)
        access.endpoints.audit_configuration(uow, context=context, kind='runtime_policy', resource_id=agent_id or 'global',
            old_revision=current['revision'], new_revision=current['revision'] + 1,
            fields=[key for key in ('runtime_enabled', 'session_policy', 'automatic_recovery', 'inherit_global_mcps')
                    if key in changes and current.get(key) != changes[key]], now=now)
        return view(conn, agent_id)


def harness_mcp_settings(conn, agent_id, adapter_id, settings):
    """Resolve overrides once, into the signed opening payload on either host."""
    result = dict(settings)
    if adapter_id in ('codex_app_server', 'claude_stream') and effective(conn, agent_id)['inherit_global_mcps']:
        result.setdefault('inherit_global_mcps', 'enabled')
    return result


def set_legacy_session_override(uow, *, agent_id, mode, access, now):
    """Compatibility for the old connection policy editor; now agent scoped."""
    conn = uow.connection
    current = view(conn, agent_id)
    if current['effective']['session_policy'] != mode:
        require_closed(conn, [agent_id])
        invalidate(uow, access, [agent_id], now)
    conn.execute('INSERT INTO agent_runtime_overrides(agent_id,runtime_enabled,session_policy,revision) VALUES(?,?,?,?) ON CONFLICT(agent_id) DO UPDATE SET '
                 'session_policy=excluded.session_policy,revision=excluded.revision',
                 (agent_id, current['runtime_enabled'], mode, current['revision'] + 1))
