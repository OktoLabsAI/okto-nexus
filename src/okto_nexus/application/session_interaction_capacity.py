"""Recover the exact capacity claim over the existing Core capacity port."""

from functools import partial

import anyio
from nexus_connector_core import (
    CapacityAssessment,
    CapacityReservation,
    capacity_reservation_id,
)

from ..adapters.outbound.sqlite.session_interaction import (
    confirm_dispatch_capacity,
    has_unsent_capacity_proof,
    mark_dispatch_capacity_uncertain,
    read_dispatch_capacity,
    record_unsent_capacity_release,
    retire_unconsumed_dispatch,
)
from ..adapters.outbound.sqlite.session_interaction_capacity_attempts import (
    fence_prepared_capacity_release,
    read_capacity_attempt,
    retire_prepared_capacity_attempt,
)
from ..errors import ErrorCode, OktoNexusError
from .execution_native_facts import stamp
from .session_interaction_dispatch import admit_held_input, prepare_input_capacity


async def consume_input_capacity(*, factory, scope, operation_id, capacity,
                                 permit_consumption=True) -> CapacityReservation:
    """Observe or consume a single already-staged claim. Release the R4 hold on proof."""
    key = {'scope': scope, 'operation_id': operation_id}

    def read():
        with factory.unit_of_work(write=False) as uow:
            claim = read_dispatch_capacity(uow, **key)
            return claim, claim.state == 'CONSUMED' and has_unsent_capacity_proof(uow, scope=scope, claim=claim)

    def apply(function, **options):
        with factory.unit_of_work() as uow:
            return function(uow, **key, **options)

    claim, release_pending = await anyio.to_thread.run_sync(read)
    if release_pending:
        # The refusal fenced the exact R4 attempt. A current authenticated host
        # can release that historical slot without authorizing another send.
        observed = await capacity.release_capacity(claim.reservation.request, claim.reservation.reservation_id, 'REVOKED')
        await anyio.to_thread.run_sync(partial(apply, record_unsent_capacity_release, observed=observed))
        return observed
    if claim.state in ('CONSUMED', 'CANCELLED_NO_EFFECT'):
        return claim.reservation
    if claim.state not in ('WAITING_CONSUMPTION', 'NEEDS_RECONCILIATION'):
        raise OktoNexusError(ErrorCode.CONFLICT, 'The capacity claim is no longer awaiting consumption.', {})
    try:
        expected = claim.reservation
        observed = await capacity.get_capacity_reservation(expected.request)
        if (type(observed) is not CapacityReservation or observed.request != expected.request
                or observed.reservation_id != expected.reservation_id):
            raise OktoNexusError(ErrorCode.CONFLICT, 'The original host capacity claim could not be confirmed.', {})
        if not permit_consumption and observed.state not in ('RELEASED', 'EXPIRED_UNCONSUMED'):
            return observed
        if observed.state == 'HELD':
            observed = await capacity.consume_capacity(expected.request, expected.reservation_id, claim.consumption)
        reconcile = (retire_unconsumed_dispatch if type(observed) is CapacityReservation and observed.state in (
            'RELEASED', 'EXPIRED_UNCONSUMED') else confirm_dispatch_capacity)
        await anyio.to_thread.run_sync(partial(apply, reconcile, observed=observed))
    except Exception:
        await anyio.to_thread.run_sync(partial(apply, mark_dispatch_capacity_uncertain))
        raise
    return observed


def _current_host(host, request):
    scope, channel = request.scope, host.channel
    if (scope.server_id, scope.executor_id) != (channel.server_id, channel.executor_id):
        raise OktoNexusError(ErrorCode.CONFLICT, 'The input attempt belongs to a different capacity host.', {})
    return (scope.connection_generation, scope.boot_id) == (channel.connection_generation, host.boot_id)


async def advance_input_capacity(*, factory, access, host, scope, authority_fence,
                                 current_capability_revision, fresh_publications, remote_ready):
    """Advance one exact session's next input over the authenticated capacity port."""
    if not remote_ready:
        return None

    def pending_work():
        with factory.unit_of_work(write=False) as uow:
            operations = uow.connection.execute("""
                SELECT i.operation_id FROM session_interaction_inputs i
                WHERE i.server_id=? AND i.executor_id=? AND i.session_id=? AND i.owner_generation=?
                  AND (i.capacity_state IN ('WAITING_CONSUMPTION','NEEDS_RECONCILIATION')
                    OR (i.capacity_state='CONSUMED' AND i.status='REFUSED_BEFORE_SEND'
                      AND EXISTS (SELECT 1 FROM execution_unsent_dispatch_proofs p
                          WHERE p.server_id=i.server_id AND p.executor_id=i.executor_id
                            AND p.operation_id=i.operation_id))) LIMIT 2
            """, (scope.session.server_id, scope.session.executor_id, scope.session.session_id,
                  scope.generation.value)).fetchall()
            if len(operations) > 1:
                raise OktoNexusError(ErrorCode.CONFLICT, 'The session has more than one staged capacity claim.', {})
            if operations:
                return read_dispatch_capacity(uow, scope=scope, operation_id=operations[0]['operation_id']), None
            return None, read_capacity_attempt(uow, session=scope.session)

    claim, previous = await anyio.to_thread.run_sync(pending_work)
    if claim is not None:
        current = _current_host(host, claim.reservation.request)
        return await consume_input_capacity(factory=factory, scope=scope, operation_id=claim.operation_id,
                                            capacity=host.port, permit_consumption=current)

    common = {'factory': factory, 'access': access, 'scope': scope,
              'current_capability_revision': current_capability_revision}

    def prepare():
        with authority_fence() as resolve, factory.unit_of_work() as uow:
            return prepare_input_capacity(uow, host=host, resolve_human=resolve, **common)

    def retire(observation):
        with factory.unit_of_work() as uow:
            return retire_prepared_capacity_attempt(uow, scope=scope, observed=observation, now=stamp(access.clock.now_iso()))

    async def release_if_fenced(*, authority_denied=False):
        if previous is None or (observed is not None and observed.state != 'HELD'):
            return None

        def fence():
            with factory.unit_of_work() as uow:
                return fence_prepared_capacity_release(uow, scope=scope, request=previous.request,
                                                       authority_denied=authority_denied)

        if not await anyio.to_thread.run_sync(fence):
            return None
        request = previous.request
        released = await host.port.release_capacity(request, capacity_reservation_id(request),
                                                    'REVOKED' if authority_denied else 'CANCELLED')
        await anyio.to_thread.run_sync(retire, released)
        return released

    observed = None
    if previous is not None:
        request = previous.request
        current = _current_host(host, request)
        observed = await host.port.get_capacity_reservation(request)
        if observed is not None and not _matches_attempt(request, observed):
            raise OktoNexusError(ErrorCode.CONFLICT, 'The host returned a different capacity attempt.', {})
        if observed is not None and observed.state in ('EXPIRED_UNCONSUMED', 'RELEASED'):
            await anyio.to_thread.run_sync(retire, observed)
            return observed
        if not current:
            return await release_if_fenced()

    try:
        attempt = await anyio.to_thread.run_sync(prepare)
    except OktoNexusError as error:
        if error.code != ErrorCode.PERMISSION_DENIED:
            raise
        released = await release_if_fenced(authority_denied=True)
        if released is None:
            raise
        return released
    if attempt is None or attempt.resolved_at is not None:
        return await release_if_fenced()
    request = attempt.request
    if not _current_host(host, request) or (previous is not None and request != previous.request):
        raise OktoNexusError(ErrorCode.CONFLICT, 'The capacity host or pending input changed.', {})
    observed = await host.port.get_capacity_reservation(request)
    if observed is None:
        # A retry uses the same immutable request and cannot buy a second slot.
        observed = await host.port.try_reserve_capacity(request)
    if type(observed) is CapacityAssessment and observed.request_hash == request.request_hash:
        return observed
    if not _matches_attempt(request, observed):
        raise OktoNexusError(ErrorCode.CONFLICT, 'The host returned a different capacity attempt.', {})

    def stage_or_recover():
        with authority_fence() as resolve, factory.unit_of_work() as uow:
            prior = read_capacity_attempt(uow, session=scope.session, attempt_id=request.attempt_id)
            if prior is not None and prior.state == 'STAGED':
                return prior.operation_id
            if observed.state in ('EXPIRED_UNCONSUMED', 'RELEASED'):
                retire_prepared_capacity_attempt(uow, scope=scope, observed=observed, now=stamp(access.clock.now_iso()))
                return None
            consumption = admit_held_input(uow, reservation=observed, resolve_human=resolve,
                fresh_publications=fresh_publications, remote_ready=remote_ready, **common)
            return consumption.turn_operation_id

    operation_id = await anyio.to_thread.run_sync(stage_or_recover)
    if operation_id is None:
        return observed
    return await consume_input_capacity(factory=factory, scope=scope, operation_id=operation_id, capacity=host.port)


def _matches_attempt(request, observed):
    return (type(observed) is CapacityReservation and observed.request == request
            and observed.reservation_id == capacity_reservation_id(request))
