"""Bounded logical discovery, using canonical eligibility and work authority.

No host calls, inbox consumption, claim or productive work in discovery.
Facts and journal writes share a short UoW before any reservation is sent.
"""
import json
from typing import Protocol

from ..domain.base import new_id
from ..domain.resource_pool import PoolUnavailable
from ..errors import ErrorCode, OktoNexusError
from .handoff_automation import create_context, context_for
from .handoff_runtime_processor import HandoffCandidatePage
from .handoff_runtime_scheduler import SCHEDULE_REASONS
from .runtime_endpoint_selection import select_runtime_endpoint


class HandoffCandidateRepository(Protocol):
    def agents_page(self, uow, lease, *, allow_new, limit): ...
    def active(self, uow, lease, agent_id): ...
    def target(self, uow, handoff, endpoint_id): ...
    def request(self, uow, *, handoff, agent_id, target, attempt_id): ...


def refusal(error):
    if isinstance(error, PoolUnavailable):
        return error.reason
    if error.code == ErrorCode.PERMISSION_DENIED:
        return 'NOT_AUTHORIZED'
    reason = error.details.get('reason') if error.details else None
    return reason if reason in SCHEDULE_REASONS else 'RECOVERING'


class HandoffCandidateDiscovery:
    def __init__(self, *, factory, repository: HandoffCandidateRepository, attempts, handoffs):
        self.factory, self.repository = factory, repository
        self.attempts, self.handoffs = attempts, handoffs

    def _eligible(self, uow, handoff, agent_id):
        agent = self.handoffs._routing_agent(uow, agent_id, handoff.workspace_id)
        return bool(self.handoffs.filter_available_handoffs(uow, workspace_id=handoff.workspace_id,
            agent=agent, rows=[handoff], now=self.handoffs._clock.now_iso()))

    def prepare_page(self, lease, *, limit):
        if type(limit) is not int or not 1 <= limit <= 32:
            raise ValueError('Invalid candidate page size.')
        with self.factory.unit_of_work() as uow:
            handoff = self.handoffs._handoffs.get(uow, workspace_id=lease.workspace_id,
                                                  handoff_id=lease.handoff_id)
            allow_new = bool(handoff and handoff.status == 'OPEN'
                and handoff.claim_epoch == lease.claim_generation
                and json.loads(handoff.target).get('strategy') == 'broadcast')
            agents, cursor, more = self.repository.agents_page(uow, lease, allow_new=allow_new, limit=limit)
            identities, reason = [], 'NO_CANDIDATES'
            for agent_id in agents:
                attempt = self.repository.active(uow, lease, agent_id)
                try:
                    if attempt:
                        if not attempt.operation_id:
                            valid = (allow_new and attempt.claim_generation == lease.claim_generation
                                     and self._eligible(uow, handoff, agent_id))
                            if valid:
                                p = attempt.principal
                                self.handoffs.runtime_work.access.authorize(context_for(p), action='execute_work',
                                    endpoint_id=p.endpoint_id, represented_agent_id=agent_id,
                                    workspace_id=lease.workspace_id, uow=uow, audit=False)
                            else:
                                self.attempts.release_pending(uow, attempt.request.attempt_id)
                        identities.append(attempt.request.attempt_id)
                    elif allow_new and self._eligible(uow, handoff, agent_id):
                        identities.append(self._prepare(uow, handoff, agent_id).request.attempt_id)
                except (OktoNexusError, PoolUnavailable) as error:
                    # Storage/internal failures must abort the page, not become
                    # a purported safe capacity refusal for one candidate.
                    if isinstance(error, OktoNexusError) and error.code not in (
                            ErrorCode.PERMISSION_DENIED, ErrorCode.CONFLICT, ErrorCode.QUOTA_EXCEEDED,
                            ErrorCode.NOT_FOUND, ErrorCode.CONFIG_ERROR, ErrorCode.VALIDATION_ERROR):
                        raise
                    reason = refusal(error)
                    if attempt:
                        self.attempts.release_pending(uow, attempt.request.attempt_id)
                        identities.append(attempt.request.attempt_id)
            return HandoffCandidatePage(tuple(identities), cursor, more,
                settled=not allow_new and not agents and not more, reason=reason)

    def _prepare(self, uow, handoff, agent_id):
        work, candidates = self.handoffs.runtime_work, []
        attempt_id = new_id('hat')
        for endpoint in work.access.endpoints.list(uow, agent_id=agent_id, workspace_id=handoff.workspace_id):
            if endpoint['protocol'] != 'nxl-r4':
                continue
            for grant in work.access.grants.candidates(uow, actor_id=agent_id, endpoint_id=endpoint['endpoint_id']):
                try:
                    context = create_context(uow, access=work.access, agent_id=agent_id,
                        workspace_id=handoff.workspace_id, endpoint_id=endpoint['endpoint_id'],
                        handoff_id=handoff.handoff_id, grant_id=grant['grant_id'], attempt_id=attempt_id)
                    work.authorize(uow, context=context, endpoint_id=endpoint['endpoint_id'],
                        grant_id=grant['grant_id'], agent_id=agent_id, workspace_id=handoff.workspace_id, audit=False)
                except OktoNexusError as error:
                    if error.code not in (ErrorCode.PERMISSION_DENIED, ErrorCode.QUOTA_EXCEEDED,
                                          ErrorCode.CONFIG_ERROR, ErrorCode.VALIDATION_ERROR):
                        raise
                    continue
                target = self.repository.target(uow, handoff, endpoint['endpoint_id'])
                candidates.append((endpoint, (context, target), target[2]))
                break  # Multiple grants/bindings do not multiply logical agents.
        selected = select_runtime_endpoint(candidates)
        if selected is None:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'No authorized managed work binding.', {})
        _, (context, target), _ = selected
        request = self.repository.request(uow, handoff=handoff, agent_id=agent_id,
                                           target=target, attempt_id=attempt_id)
        return self.attempts.create(uow, principal=context.handoff_automation, request=request,
                                    claim_generation=handoff.claim_epoch)
