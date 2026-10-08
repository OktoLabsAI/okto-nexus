"""Operator initiation is separate from the subject's runtime execution grant."""
import json
from ..domain.runtime_context import RuntimeRequestContext
from ..errors import ErrorCode, OktoNexusError
from .execution_binding_proposals import _agent_guard
from .runtime_actor_authority import LOCAL_OPERATOR_PREFIX, local_operator_binding


def require_operator_request(uow, *, actor, subject, access, context, require_feature=True,
                             binding_id=None, action=None):
    if actor == subject:
        return None
    if (access is not None and context is not None and context.actor_agent_id == actor
            and context.authentication_source == 'agent_key' and binding_id and action == 'turn.submit'
            and not access.authenticate(context, uow=uow, require_feature=require_feature)):
        endpoint = uow.connection.execute('SELECT b.endpoint_id FROM execution_bindings b '
            'JOIN execution_installation i USING(server_id) JOIN agent_endpoints e USING(endpoint_id) '
            'WHERE b.binding_id=? AND e.agent_id=?', (binding_id, subject)).fetchall()
        if len(endpoint) != 1:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Delegated binding is unavailable.', {})
        grant = access.authorize(context, action='send', endpoint_id=endpoint[0][0],
            represented_agent_id=subject, uow=uow, audit=False, check_budget=False)
        if grant is None:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'An explicit execution grant is required.', {})
        return 'delegated:' + json.dumps(dict(actor_guard=_agent_guard(uow.connection, actor),
            grant_id=grant['grant_id'], grant_revision=grant['revision'], binding_id=binding_id,
            endpoint_id=endpoint[0][0], action=action), sort_keys=True, separators=(',', ':'))
    if (access is None or context is None or context.actor_agent_id != actor
            or context.authentication_source not in ('agent_key', 'http_loopback', 'operator_session')
            or not access.authenticate(context, uow=uow, require_feature=require_feature)):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                            'Representing another agent requires an authenticated operator.', {})
    if context.authentication_source in ('http_loopback', 'operator_session'):
        if actor != 'operator' or not context.trusted_local_operator:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The local operator is unavailable.', {})
        return local_operator_binding(uow)
    return _agent_guard(uow.connection, actor)


def require_recorded_operator(uow, *, actor, subject, guard, access):
    if actor == subject:
        return
    current = access.agents.get(uow, actor) if access is not None else None
    if current is None or not guard:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                            'The initiating operator authority is unavailable.', {})
    if guard.startswith('delegated:'):
        proof = json.loads(guard.removeprefix('delegated:'))
        context = RuntimeRequestContext(actor, 'agent_key', credential_binding=current.api_key_hash,
            execution_grant_id=proof['grant_id'])
        actual = require_operator_request(uow, actor=actor, subject=subject, access=access, context=context,
            binding_id=proof['binding_id'], action=proof['action'])
        if actual != guard:
            raise OktoNexusError(ErrorCode.CONFLICT, 'The delegated execution authority changed.', {})
        # Delegation never acquires operator containment privileges.
        return None
    local = guard.startswith(LOCAL_OPERATOR_PREFIX)
    context = RuntimeRequestContext(actor, 'http_loopback' if local else 'agent_key',
                                    trusted_local_operator=local,
                                    credential_binding=None if local else current.api_key_hash)
    actual = require_operator_request(uow, actor=actor, subject=subject, access=access, context=context)
    if actual != guard:
        raise OktoNexusError(ErrorCode.CONFLICT, 'The initiating operator authority changed.', {})
    return context


def consume_recorded_delegation(uow, *, actor, subject, guard, access):
    if actor == subject or not guard or not guard.startswith('delegated:'):
        return
    require_recorded_operator(uow, actor=actor, subject=subject, guard=guard, access=access)
    proof = json.loads(guard.removeprefix('delegated:'))
    current = access.agents.get(uow, actor)
    context = RuntimeRequestContext(actor, 'agent_key', credential_binding=current.api_key_hash,
        execution_grant_id=proof['grant_id'])
    access.authorize(context, action='send', endpoint_id=proof['endpoint_id'],
        represented_agent_id=subject, consume=True, uow=uow)


def require_delegated_result_read(uow, *, operation_id, context, access):
    if context is None:
        return
    rows = uow.connection.execute('SELECT p.subject_agent_id,b.endpoint_id FROM execution_operations p '
        'JOIN execution_installation i USING(server_id) JOIN execution_bindings b '
        'USING(server_id,executor_id,binding_id) WHERE p.operation_id=? AND p.actor_agent_id=?',
        (operation_id, context.actor_agent_id)).fetchall()
    if len(rows) == 1 and rows[0]['subject_agent_id'] != context.actor_agent_id:
        access.authorize(context, action='read', endpoint_id=rows[0]['endpoint_id'],
            represented_agent_id=rows[0]['subject_agent_id'], uow=uow, audit=False)
