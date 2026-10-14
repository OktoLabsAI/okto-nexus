"""Bind managed work to the existing canonical handoff and claim epoch."""

from typing import Protocol

from ..domain.execution_principal import current_execution_principal
from .execution_tools import denied


class ExecutionClaimRepository(Protocol):
    def bind(self, uow, *, handoff_id, claim_epoch, scope): ...
    def matches(self, uow, *, handoff_id, claim_epoch, scope) -> bool: ...
    def bind_delivery(self, uow, *, operation_id, scope): ...


def remember_claim(uow, handoff, repository):
    principal = current_execution_principal.get()
    if principal is None:
        return
    if repository is None:
        raise denied('Managed claim ownership is unavailable.')
    repository.bind(uow, handoff_id=handoff.handoff_id, claim_epoch=handoff.claim_epoch,
                    scope=dict(principal.scope))


def require_claim(uow, *, handoff_id, claim_epoch, repository):
    principal = current_execution_principal.get()
    if principal is None:
        return
    if repository is None or not repository.matches(uow, handoff_id=handoff_id,
            claim_epoch=claim_epoch, scope=dict(principal.scope)):
        raise denied('This claim belongs to a different session or execution generation.')
