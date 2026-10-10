"""Authorized configuration boundary for one-shot limits and MCP presets."""
from ..errors import ErrorCode, OktoNexusError
from . import one_shot_settings, runtime_mcp_presets


def configure(deps, context, *, kind, resource_id=None, changes=None):
    from ..bootstrap.execution_authority import build_execution_access
    access = build_execution_access(deps)
    with deps.connection_factory.unit_of_work(write=changes is not None) as uow:
        # Presets contain host commands and secret references: operator only,
        # including reads. Managed agent capabilities cannot grant maintenance.
        access.authorize_maintenance(context, uow=uow)
        conn = uow.connection
        if kind == 'one_shot':
            read = lambda: one_shot_settings.read(conn, resource_id)
            allowed = {'expected_revision', 'settings'}
        elif kind == 'mcp_preset':
            read = lambda: runtime_mcp_presets.snapshot(conn, resource_id)
            allowed = {'expected_revision', 'servers'}
        else:
            raise ValueError('Unknown runtime settings kind')
        current = read()
        if changes is None:
            return current
        if type(changes) is not dict or set(changes) != allowed:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid runtime settings fields.', {})
        if kind == 'one_shot':
            result = one_shot_settings.save(conn, agent_id=resource_id, **changes)
        else:
            result = runtime_mcp_presets.save(conn, endpoint_id=resource_id, **changes)
        if result['revision'] != current['revision']:
            access.endpoints.audit_configuration(uow, context=context, kind=kind, resource_id=resource_id or 'global',
                old_revision=current['revision'], new_revision=result['revision'],
                fields=sorted(allowed - {'expected_revision'}), now=deps.clock.now_iso())
        return result


def one_shot_state(deps, context, *, agent_id, cancel_call_id=None):
    import json
    import time
    from ..bootstrap.execution_authority import build_execution_access
    from . import one_shot_capacity as capacity
    access = build_execution_access(deps)
    with deps.connection_factory.unit_of_work(write=cancel_call_id is not None) as uow:
        access.authorize_maintenance(context, uow=uow)
        conn = uow.connection
        if access.agents.get(uow, agent_id) is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'Agent does not exist.', {})
        if cancel_call_id is not None:
            call = capacity._row(conn, cancel_call_id)
            if call['agent_id'] != agent_id:
                raise OktoNexusError(ErrorCode.NOT_FOUND, 'One-shot call not found for this agent.', {})
            if call['outcome_json'] is None:
                capacity.fail(conn, call_id=cancel_call_id, code='ONE_SHOT_CANCELLED', stage='cancellation',
                    message='The operator cancelled this one-shot call.', now=time.time(), cancelled=True, retry_safe=True)
                access.endpoints.audit_configuration(uow, context=context, kind='one_shot_cancel',
                    resource_id=cancel_call_id, old_revision=None, new_revision=1, fields=['state'], now=deps.clock.now_iso())
        slots = dict(conn.execute('SELECT state,count(*) FROM one_shot_slots WHERE agent_id=? GROUP BY state', (agent_id,)))
        queued = conn.execute("SELECT count(*) FROM one_shot_calls WHERE agent_id=? AND state='QUEUED'", (agent_id,)).fetchone()[0]
        calls = []
        for row in conn.execute('SELECT call_id,caller_id,state,enqueued_at,outcome_json FROM one_shot_calls '
                                'WHERE agent_id=? ORDER BY enqueued_at DESC,call_id DESC LIMIT 50', (agent_id,)):
            item = dict(row)
            outcome = json.loads(item.pop('outcome_json') or '{}')
            item['error'] = outcome.get('error')
            calls.append(item)
        policy = capacity.policy(conn, agent_id)
        return dict(slots=slots, occupied=sum(slots.values()), queued=queued, calls=calls,
                    available=slots.get('WARM', 0), max_pool_instances=policy.max_parallel,
                    max_parallel=policy.max_parallel, warm_target=policy.warm_instances)
