"""Transaction-bound coordination identity, approval correlation and recovery."""
from __future__ import annotations

from ..domain.base import new_id
from ..domain.coordination_requests import conflict
from ..errors import ErrorCode, OktoNexusError


def require_internal(metadata, *, approved, client_request_id, decision_revision=None):
    if metadata is not None and (not approved or client_request_id is None or type(metadata) is not dict):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Coordination approval context is internal.", {})
    if approved and client_request_id is not None and metadata is None:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "The original coordination approval is required.", {})
    if ((metadata is not None and (type(decision_revision) is not int or decision_revision < 1))
            or (metadata is None and decision_revision is not None)):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "The coordination decision revision is internal.", {})


def receipt_response(repo, uow, receipt, *, now, reused):
    reference = repo.reference(uow, receipt, now=now)
    data = dict(status=reference['state'], workspace_id=receipt.key.workspace_id,
                request_receipt=reference, reused=reused)
    if receipt.resource_id is not None:
        data['message_id' if receipt.key.operation == 'message_create' else 'handoff_id'] = receipt.resource_id
    if receipt.approval_id is not None:
        data['approval_id'] = receipt.approval_id
    return data


class CoordinationCreation:
    """A single call, owned by the canonical message/handoff write UoW.

    Authentication, current permissions and verified session provenance precede
    this helper. It never opens a transaction or performs productive work.
    """

    def __init__(self, *, repo, approvals, uow, actor_id, workspace_id, operation,
                 client_request_id, request_hash, authority_binding, explicit_trace_id,
                 now, metadata=None, decision_revision=None):
        if repo is None:
            raise OktoNexusError(ErrorCode.CONFLICT, "Coordination receipts are not available on this Server.", {})
        if not authority_binding:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                "A coordination request requires an authenticated actor.", {})
        from .connection_policy import require_method
        require_method(uow, actor_id, 'mcp')
        self.repo, self.approvals, self.uow = repo, approvals, uow
        self.key = repo.key(uow, actor_agent_id=actor_id, workspace_id=workspace_id,
                            operation=operation, client_request_id=client_request_id)
        self.digest, self.now, self.metadata = request_hash, now, metadata
        self.decision_revision = decision_revision
        self.authority, self.trace = authority_binding, explicit_trace_id
        self.existing = repo.lookup(uow, self.key, request_hash=request_hash, now=now)
        self.approval_id = None
        if metadata is not None:
            expected = dict(revision=1, server_id=self.key.server_id, actor_agent_id=actor_id,
                workspace_id=workspace_id, operation=operation, client_request_id=client_request_id,
                request_hash=request_hash, authority_binding=authority_binding,
                explicit_trace_id=explicit_trace_id, approval_id=metadata.get('approval_id'))
            if metadata != expected or not self.existing or self.existing.approval_id != expected['approval_id']:
                raise conflict('CLIENT_REQUEST_APPROVAL_REFERENCE_MISSING')
            if approvals is None:
                raise conflict('CLIENT_REQUEST_APPROVAL_REFERENCE_MISSING')
            approvals.require_coordination_execution(uow, metadata=metadata, decision_revision=decision_revision)
            self.approval_id = self.existing.approval_id

    def replay(self):
        if self.existing is None or (self.metadata is not None and self.existing.state == 'pending_approval'):
            return None
        return receipt_response(self.repo, self.uow, self.existing, now=self.now, reused=True)

    def approval_context(self):
        self.approval_id = new_id('apr')
        return dict(revision=1, server_id=self.key.server_id, actor_agent_id=self.key.actor_agent_id,
            workspace_id=self.key.workspace_id, operation=self.key.operation,
            client_request_id=self.key.client_request_id, request_hash=self.digest,
            authority_binding=self.authority, explicit_trace_id=self.trace, approval_id=self.approval_id)

    def pending(self):
        receipt = self.repo.record(self.uow, self.key, request_hash=self.digest,
                                  now=self.now, approval_id=self.approval_id)
        return receipt_response(self.repo, self.uow, receipt, now=self.now, reused=False)

    def created(self, resource_id):
        if self.metadata is not None:
            receipt = self.repo.resolve_approval(self.uow, self.key, request_hash=self.digest,
                approval_id=self.approval_id, resource_id=resource_id, now=self.now)
        else:
            receipt = self.repo.record(self.uow, self.key, request_hash=self.digest,
                                       now=self.now, resource_id=resource_id)
        response = receipt_response(self.repo, self.uow, receipt, now=self.now, reused=False)
        if self.metadata is not None:
            self.approvals.complete_coordination(self.uow, metadata=self.metadata,
                decision_revision=self.decision_revision, result=response)
        return response


class CoordinationRequestService:
    """Read only the authenticated actor's own metadata references."""

    def __init__(self, *, factory, repo, agents, workspaces, clock, context_provider):
        self.factory, self.repo, self.agents, self.workspaces = factory, repo, agents, workspaces
        self.clock, self.context_provider = clock, context_provider

    def get(self, *, workspace_id, operation, client_request_id):
        from ..domain.execution_principal import current_execution_principal
        from .execution_tools import ExecutionToolConnectionFactory, execution_actions, denied
        from .runtime_actor_authority import authenticated_message_context
        with self.factory.unit_of_work(write=False) as uow:
            principal = current_execution_principal.get()
            if principal is not None:
                if (not isinstance(self.factory, ExecutionToolConnectionFactory)
                        or workspace_id != principal.scope['workspace_id']):
                    raise denied()
                self.factory.capabilities.authorize_principal(uow, principal=principal,
                    actions=execution_actions(principal))
                actor_id = principal.scope['agent_id']
            else:
                context = authenticated_message_context(uow, self.context_provider(), self.agents)
                if context is None:
                    raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "An authenticated actor is required.", {})
                actor_id = context.actor_agent_id
            from .connection_policy import require_method
            require_method(uow, actor_id, 'mcp')
            key = self.repo.key(uow, actor_agent_id=actor_id, workspace_id=workspace_id,
                                operation=operation, client_request_id=client_request_id)
            if self.workspaces.get(uow, workspace_id) is None:
                raise OktoNexusError(ErrorCode.NOT_FOUND, "The logical workspace was not found.", {})
            receipt = self.repo.get(uow, key)
            if receipt is None:
                raise OktoNexusError(ErrorCode.NOT_FOUND,
                    "No retained receipt was found. Absence does not prove that an old request never committed.",
                    {'reason': 'CLIENT_REQUEST_RECEIPT_NOT_FOUND'})
            return receipt_response(self.repo, uow, receipt, now=self.clock.now_iso(), reused=True)
