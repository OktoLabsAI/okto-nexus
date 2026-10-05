"""Operator initiation is separate from the subject's runtime execution grant."""
from ..domain.runtime_context import RuntimeRequestContext
from ..errors import ErrorCode, OktoNexusError
from .execution_binding_proposals import _agent_guard
from .runtime_actor_authority import LOCAL_OPERATOR_PREFIX, local_operator_binding


def require_operator_request(uow, *, actor, subject, access, context, require_feature=True):
    if actor == subject:
        return None
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
    local = guard.startswith(LOCAL_OPERATOR_PREFIX)
    context = RuntimeRequestContext(actor, 'http_loopback' if local else 'agent_key',
                                    trusted_local_operator=local,
                                    credential_binding=None if local else current.api_key_hash)
    actual = require_operator_request(uow, actor=actor, subject=subject, access=access, context=context)
    if actual != guard:
        raise OktoNexusError(ErrorCode.CONFLICT, 'The initiating operator authority changed.', {})
