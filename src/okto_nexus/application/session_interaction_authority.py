"""Check existing human and runtime authority without admitting an operation."""

import json
from dataclasses import asdict

from ..adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from ..adapters.outbound.sqlite.execution_leases import SqliteExecutionLeaseRepository
from ..adapters.outbound.sqlite.session_interaction import accept_input
from ..adapters.outbound.sqlite.session_interaction_cancellation import cancel_input
from ..domain.runtime_context import RuntimeRequestContext
from ..errors import ErrorCode, OktoNexusError
from .execution_agent_recovery import require_agent_ready
from .execution_connection_keys import require_connection_key
from .execution_identity_owner import require_identity_host
from .execution_leases import (
    ExecutionChannel,
    require_applied_dispatch_lease,
    require_execution_lane,
)
from .execution_native_facts import require_capability_scope_facts, stamp
from .execution_operator_authority import (
    require_operator_request,
    require_subject_dispatch_grant,
)
from .runtime_policy import effective


def enqueue_human_input(*, factory, access, authority_fence, current_capability_revision,
                        scope, author, client_intent_id, capability_revision, text):
    """Commit one input for an already identified human and exact session."""
    with authority_fence() as resolve_human, factory.unit_of_work() as uow:
        if not resolve_human(author.authority_ref):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The session input author is no longer signed in.', {})

        def verify_new_authority():
            grant = require_session_input_authority(uow, factory=factory, access=access, scope=scope,
                                                   author=author, resolve_human=resolve_human)
            if not capability_revision or current_capability_revision(uow, scope) != capability_revision:
                raise OktoNexusError(ErrorCode.CONFLICT, 'The session input capability changed.', {})
            return grant

        return accept_input(uow, scope=scope, author=author, client_intent_id=client_intent_id,
            capability_revision=capability_revision, text=text, now=stamp(access.clock.now_iso()),
            verify_new_authority=verify_new_authority)


def cancel_human_input(*, factory, access, authority_fence, current_cancel_revision,
                       scope, author, input_id, capability_revision, expected_queue_revision,
                       expected_input_revision):
    """Cancel an owned input under the current human's cancellation authority."""
    with authority_fence() as resolve_human, factory.unit_of_work() as uow:
        def verify():
            if not resolve_human(author.authority_ref):
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The session input author is no longer signed in.', {})
            context = RuntimeRequestContext('operator', 'operator_session', trusted_local_operator=True)
            if not access.authenticate(context, uow=uow, require_feature=False):
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Input cancellation requires operator authority.', {})
            return current_cancel_revision(uow, scope)

        return cancel_input(uow, scope=scope, author=author, input_id=input_id, capability_revision=capability_revision,
                            expected_queue_revision=expected_queue_revision, expected_input_revision=expected_input_revision,
                            verify_authority=verify)


def require_session_input_authority(uow, *, factory, access, scope, author, resolve_human):
    """Verify both the originating login and the exact session's existing grant.

    The caller holds the human authority fence before taking this writer and
    through commit. The returned grant identifies the authority checked here.
    A pending approval or busy worker is permitted at intake. A sending
    transaction must independently check capability and turn eligibility.
    """
    if not resolve_human(author.authority_ref):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The session input author is no longer signed in.', {})
    context = RuntimeRequestContext('operator', 'operator_session', trusted_local_operator=True)
    access.authenticate(context, uow=uow)
    require_operator_request(uow, actor='operator', subject=scope.agent_id, access=access,
                             context=context, binding_id=scope.binding_id, action='turn.submit')
    exact = {
        **asdict(scope.session), 'binding_id': scope.binding_id, 'agent_id': scope.agent_id,
        'workspace_id': scope.workspace_id, 'workspace_binding_id': scope.workspace_binding_id,
        'session_owner_generation': scope.generation.value,
    }
    server_id, revisions, _ = current_agent_revisions(factory, agent_id=scope.agent_id, uow=uow, persist=False)
    expected_revisions = {
        'authorization_revision': revisions.authorization, 'configuration_revision': revisions.configuration,
        'credential_epoch': revisions.credential_epoch,
    }
    repo = SqliteExecutionLeaseRepository()
    owner = repo.authority(uow, exact)
    if owner is None or server_id != scope.session.server_id or owner['control_state'] != 'CONTROL_READY':
        raise OktoNexusError(ErrorCode.CONFLICT, 'The exact session is currently unavailable.', {})
    applied_scope = {**exact, **expected_revisions, 'binding_revision': owner['binding_revision']}
    require_capability_scope_facts(scope=applied_scope, revisions=expected_revisions, authority=owner)
    if owner['lifecycle_state'] != 'READY' or owner['lease_state'] != 'ACTIVE':
        raise OktoNexusError(ErrorCode.CONFLICT, 'The exact session has no active lease.', {})
    if effective(uow.connection, scope.agent_id)['session_policy'] == 'one_shot':
        raise OktoNexusError(ErrorCode.CONFLICT, 'This session is allocated to one-shot work.', {})
    require_identity_host(uow.connection, server_id=server_id, agent_id=scope.agent_id,
                          executor_id=scope.session.executor_id)
    require_agent_ready(uow.connection, server_id, scope.session.executor_id, scope.agent_id)
    containment = getattr(access, 'session_containment', None)
    if containment is not None:
        containment.require_not_pending(uow, applied_scope)
    if owner['connection_key_id'] is not None:
        require_connection_key(uow, access=access, agent_id=scope.agent_id,
                               endpoint_id=owner['endpoint_id'], key_id=owner['connection_key_id'])
    opening = json.loads(owner['semantic_payload'])
    mode = opening.get('payload', {}).get('mode')
    if opening.get('action') != 'runtime.open' or mode not in ('managed', 'attach'):
        raise OktoNexusError(ErrorCode.CONFLICT, 'The session has no canonical execution mode.', {})
    now = stamp(access.clock.now_iso())
    lease = repo.effective(uow, applied_scope)
    require_applied_dispatch_lease(lease, scope=applied_scope, owner=owner, action='turn.submit', now=now)
    if owner['kind'] == 'remote':
        require_execution_lane(uow, scope=applied_scope, now=now,
            channel=ExecutionChannel(server_id, scope.session.executor_id,
                                     lease['connection_id'], lease['connection_generation']))
    subject = access.agents.get(uow, scope.agent_id)
    if subject is None or not subject.is_active:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The session subject is unavailable.', {})
    grant = require_subject_dispatch_grant(uow, access=access, subject=subject, grant_id=lease['grant_id'],
        action='send', endpoint_id=owner['endpoint_id'], workspace_id=scope.workspace_id, mode=mode,
        consume=False, audit=False)
    if grant['revision'] != lease['source_grant_revision']:
        raise OktoNexusError(ErrorCode.CONFLICT, 'The session grant changed after its lease was applied.', {})
    return grant['grant_id'], grant['revision']
