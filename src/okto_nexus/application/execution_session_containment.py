"""Durable obligations to contain one original runtime session.

A denied renewal is not a release proof. An initial denial can settle only
with its exact terminal no-effect opening fact. Keep those distinctions across
restarts, without changing the availability of sibling sessions.
"""
from dataclasses import dataclass
from typing import Protocol

from nexus_connector_core import decode_r4_frame, encode_r4_frame

from ..errors import ErrorCode, OktoNexusError


@dataclass(frozen=True)
class ContainmentTarget:
    opening_operation_id: str
    opening_intent_hash: str


class SessionContainmentRepository(Protocol):
    def renewal_target(self, uow, request, channel) -> ContainmentTarget | None: ...
    def initial_target(self, uow, request, channel) -> ContainmentTarget | None: ...
    def record(self, uow, request, target: ContainmentTarget, now: str) -> None: ...
    def pending(self, uow, scope) -> bool: ...
    def complete_verified(self, uow, channel, session_id, owner_generation, proof, now) -> None: ...
    def initial_refusal_records(self, uow, channel, *, agent_id=None, session_id=None,
                                pending_only=True) -> list[dict]: ...
    def bind_initial_refusal(self, uow, channel, *, operation_id, session_id, binding) -> bool: ...


class ExecutionSessionContainment:
    def __init__(self, *, factory, repository: SessionContainmentRepository, clock):
        self.factory, self.repository, self.clock = factory, repository, clock

    def denied(self, request, *, channel):
        """Called only after authenticated lease revalidation has refused work.

        Bind to recorded historical authority, not the now-revoked policy. An
        arbitrary stale/foreign request must not create a containment target.
        """
        request = decode_r4_frame(encode_r4_frame(request))
        if (request['type'] != 'lease.renew' or request['purpose'] not in ('renew', 'initial')
                or request['scope']['server_id'] != channel.server_id
                or request['scope']['executor_id'] != channel.executor_id
                or request['connection_id'] != channel.connection_id
                or request['connection_generation'] != channel.connection_generation):
            return False
        with self.factory.unit_of_work() as uow:
            target = (self.repository.initial_target(uow, request, channel) if request['purpose'] == 'initial'
                      else self.repository.renewal_target(uow, request, channel))
            if target is None:
                return False
            self.repository.record(uow, request, target, self.clock.now_iso())
        return True  # The obligation commits before the denial is published.

    def require_not_pending(self, uow, scope):
        if self.repository.pending(uow, scope):
            raise OktoNexusError(ErrorCode.CONFLICT,
                'This session requires confirmed resource release after lease denial.', {})

    def record_verified_release(self, uow, *, channel, session_id, owner_generation, proof):
        """Internal commit hook after canonical reconciliation validates all facts.

        This is not a transport endpoint or a standalone proof validator. Use
        the caller's transaction so projection and obligation settle together.
        """
        self.repository.complete_verified(uow, channel, session_id, owner_generation,
                                          proof, self.clock.now_iso())


def matches_initial_refusal(frame, scope, request, target: ContainmentTarget):
    """A terminal no-effect opening fact may resolve its recorded initial denial.

    Receipt authentication and immutable dispatch matching remain mandatory at
    ingress. This rule never treats a renewal denial as evidence of no effect.
    """
    return (frame['stage'] == 'FAILED' and frame.get('error_code') == 'LEASE_REVALIDATION_REQUIRED'
        and frame['possible_effect'] is False and frame['retry_safe'] is True
        and frame.get('native_id') is None and request['purpose'] == 'initial'
        and request['expected_lease_serial'] == 0 and request['scope'] == scope
        and frame['operation_id'] == target.opening_operation_id and frame['intent_hash'] == target.opening_intent_hash
        and all(frame[k] == request[k] for k in ('connection_id','connection_generation')))
