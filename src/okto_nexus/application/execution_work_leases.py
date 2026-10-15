"""Keep running handoff authority separate from a session's technical lease."""
from dataclasses import dataclass
from typing import Protocol

from ..errors import ErrorCode, OktoNexusError


@dataclass(frozen=True)
class RunningHandoff:
    operation: dict
    claim_epoch: int
    current_epoch: int | None
    status: str | None
    claimant: str | None


class RunningHandoffRepository(Protocol):
    def startup_deadline(self, uow, scope) -> float | None:
        """Bound an unstarted reserved one-shot in this exact session scope."""
        ...

    def running(self, uow, scope) -> tuple[RunningHandoff, ...]:
        """Return only unsettled native work owned by this exact session scope."""
        ...


class ExecutionWorkLeaseAuthority:
    def __init__(self, *, repository: RunningHandoffRepository, validate):
        self.repository, self.validate = repository, validate

    def require(self, uow, scope, *, now):
        deadline = self.repository.startup_deadline(uow, scope)
        if deadline is not None and deadline <= now:
            # Reject both initial authority and renewal. The existing scoped
            # denial/containment owner retains resources until release proof;
            # neither this deadline nor the pool expiry is physical termination.
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                'The reserved handoff startup deadline was exceeded.', {})
        for work in self.repository.running(uow, scope):
            if (work.current_epoch != work.claim_epoch or work.claimant != scope['agent_id']
                    or work.status not in {'CLAIMED', 'COMPLETED', 'VERIFYING'}):
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                    'The running handoff no longer owns its claim.', {})
            # An authenticated business completion is not physical termination.
            # Let the same native turn finish publishing its response; neither
            # renewals nor a tool result may manufacture a resource release.
            if work.status in {'COMPLETED', 'VERIFYING'}:
                continue
            # Canonical work authorization includes the original grant and,
            # for automatic claims, the retained opt-in/identity proof. This
            # does not consume budget again or create an operator credential.
            self.validate(uow, work.operation)
