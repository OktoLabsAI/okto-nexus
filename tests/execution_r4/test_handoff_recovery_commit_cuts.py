"""T24: lost/rolled-back observations never substitute a new work identity."""
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest

from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from okto_nexus.bootstrap.handoff_runtime_attempts import build_handoff_runtime_attempts
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, assert_unclaimed
from test_canonical_result_publication import current_turn
from test_handoff_runtime_attempts import prepared, ObservedPort
from test_capacity_compensation import committed, expire
from test_one_shot_runtime import query


def cut_transition(service, state, target, boundary):
    factory, fired = service.factory, []

    @contextmanager
    def unit_of_work(**kwargs):
        changed = False
        with factory.unit_of_work(**kwargs) as uow:
            before = state(uow)
            yield uow
            changed = not fired and kwargs.get('write') is not False and before != target and state(uow) == target
            if changed:
                fired.append(target)
                if boundary == 'rollback':
                    raise OSError('Rollback ' + str(target))
        if changed and boundary == 'lost_reply':
            raise OSError('Lost commit result ' + str(target))

    service.factory = SimpleNamespace(unit_of_work=unit_of_work)
    return fired


@pytest.mark.parametrize('boundary', ['rollback', 'lost_reply'])
@pytest.mark.parametrize('point', ['before_reserve', 'after_reserve', 'unknown_reserve'])
def test_refusal_or_uncertainty_commit_cut_keeps_original_attempt(runtime, boundary, point):
    service, port, attempt, hid, gid = prepared(runtime)
    setup = runtime[0]
    deps, _, client, *_ = setup
    aid = attempt.request.attempt_id
    competitor_request = replace(attempt.request, attempt_id='competitor',
        scope=replace(attempt.request.scope, session_id='competitor-session'))

    class FaultPort(ObservedPort):
        competitor = None
        lost = False

        async def assess_capacity(self, req):
            if point == 'before_reserve' and self.competitor is None:
                self.competitor = await self.port.try_reserve_capacity(competitor_request)
            return await self.port.assess_capacity(req)

        async def try_reserve_capacity(self, req):
            if point == 'after_reserve' and self.competitor is None:
                self.competitor = await self.port.try_reserve_capacity(competitor_request)
            result = await super().try_reserve_capacity(req)
            if point == 'unknown_reserve' and not self.lost:
                self.lost = True
                assert result.state == 'HELD'
                raise TimeoutError('Core committed the reservation; its response was lost')
            return result

    observed = FaultPort(runtime, port)
    service.capacity = observed
    target = 'NEEDS_RECONCILIATION' if point == 'unknown_reserve' else 'NOT_AVAILABLE'
    fired = cut_transition(service,
        lambda uow: uow.connection.execute('SELECT state FROM handoff_runtime_attempts WHERE attempt_id=?', (aid,)).fetchone()[0],
        target, boundary)
    with pytest.raises(OSError):
        client.portal.call(service.reserve, aid)
    assert fired == [target]
    assert_unclaimed(runtime, hid, gid)
    assert runtime[2].opens == 0
    retained = client.portal.call(port.get_capacity_reservation, attempt.request)
    if point == 'unknown_reserve':
        assert retained is not None and retained.state == 'HELD'
    else:
        assert retained is None
        client.portal.call(port.release_capacity, competitor_request, observed.competitor.reservation_id, 'CANCELLED')
    restored = build_handoff_runtime_attempts(deps, capacity=observed)
    previous = restored.get(aid)
    assert previous.request == attempt.request
    # The committed pre-send refusal is terminal. Losing the reply cannot
    # turn that attempt back into a candidate after capacity becomes free.
    if point == 'before_reserve' and boundary == 'lost_reply':
        assert not previous.active and not previous.reserve_started
        assert client.portal.call(restored.reserve, aid) == previous
        assert observed.reserves == 0 and runtime[2].opens == 0
        assert_unclaimed(runtime, hid, gid)
        return
    held = client.portal.call(restored.reserve, aid)
    assert held.state == 'RESERVED' and held.request == attempt.request
    if retained is not None:
        assert held.reservation.reservation_id == retained.reservation_id
    claim = restored.claim(aid)
    transfer = build_capacity_admission(deps, capacity=port)
    assert client.portal.call(transfer.consume, claim.operation_id).state == 'CONSUMED'
    wait_receipt(setup, current_turn(setup))
    assert runtime[2].opens == len(runtime[2].native.sent) == 1
    assert restored.claim(aid).operation_id == claim.operation_id
    assert query(setup, 'SELECT count(*) FROM handoff_runtime_attempts')[0][0] == 1
    assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == ('CLAIMED', 1)
    assert query(setup, 'SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (gid,))[0][0] == 1
    assert observed.reserves == (2 if point == 'after_reserve' else 1)


@pytest.mark.parametrize('boundary', ['rollback', 'lost_reply'])
@pytest.mark.parametrize('terminal', ['expired', 'released'])
def test_compensation_commit_cut_recovers_same_proof_without_duplicate_reopen(runtime, boundary, terminal):
    attempts, port, held, claim, hid = committed(runtime)
    setup = runtime[0]
    deps, _, client, *_ = setup
    if terminal == 'expired':
        expire(port)
    else:
        client.portal.call(port.release_capacity, held.request, held.reservation.reservation_id, 'CANCELLED')
    transfer = build_capacity_admission(deps, capacity=port)
    fired = cut_transition(transfer,
        lambda uow: transfer.repository.get(uow, claim.operation_id).state,
        'CANCELLED_NO_EFFECT', boundary)
    with pytest.raises(OSError):
        client.portal.call(transfer.consume, claim.operation_id)
    assert fired == ['CANCELLED_NO_EFFECT']
    assert runtime[2].opens == 0
    assert query(setup, 'SELECT count(*) FROM execution_capacity_compensations')[0][0] == int(boundary == 'lost_reply')
    expected = 'OPEN' if boundary == 'lost_reply' else 'CLAIMED'
    assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == (expected, 1)
    resumed = build_capacity_admission(deps, capacity=port)
    result = client.portal.call(resumed.consume, claim.operation_id)
    assert result.state == 'CANCELLED_NO_EFFECT'
    assert result.operation_id == claim.operation_id and result.reservation.request == held.request
    assert result.reservation.reservation_id == held.reservation.reservation_id
    assert client.portal.call(resumed.consume, claim.operation_id) == result
    assert not attempts.get(held.request.attempt_id).active
    assert query(setup, 'SELECT count(*) FROM execution_capacity_compensations')[0][0] == 1
    assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == ('OPEN', 1)
    assert query(setup, 'SELECT status,ack_level FROM delivery_outbox WHERE operation_id=?', (claim.operation_id,))[0][:] == ('CANCELLED', 'NONE')
    assert {r[0] for r in query(setup, 'SELECT admission_state FROM execution_operations')} == {'RESOLVED_TERMINAL'}
    assert query(setup, 'SELECT lifecycle_state,lease_state FROM execution_sessions')[0][:] == ('FAILED', 'CLOSED')
    assert runtime[2].opens == 0 and not runtime[2].native.sent
