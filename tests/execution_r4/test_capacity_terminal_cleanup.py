"""An unused execution ticket cannot undo canonical cancellation or decisions."""
import asyncio
from dataclasses import replace

import pytest

from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from okto_nexus.bootstrap.handoff_runtime_scheduler import build_handoff_runtime_candidates
from okto_nexus.application.handoff_runtime_processor import HandoffRuntimeProcessor
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, call
from test_handoff_runtime_attempts import prepared
from test_handoff_runtime_candidates import lease
from test_capacity_compensation import committed, expire


@pytest.mark.parametrize('decision', ['reject', 'complete', 'verify', 'rework'])
@pytest.mark.parametrize('expired', [False, True])
def test_unconsumed_ticket_cleanup_preserves_canonical_decision(runtime, decision, expired):
    verifiable = decision in {'verify', 'rework'}
    runtime[0][0].config.feature_verification = verifiable
    attempts, port, held, claim, hid = committed(runtime,
        **({'acceptance_criteria': ['Creator reviews the evidence']} if verifiable else {}))
    deps, _, client, *_ = runtime[0]
    response = call(runtime, 'handoff_reject' if decision == 'reject' else 'handoff_complete',
        actor='subject', handoff_id=hid, agent_id='subject', claim_epoch=1,
        **({'reason': 'No execution needed'} if decision == 'reject' else {'result': 'Resolved outside this pending execution'}))
    assert response['ok'], response
    if decision == 'rework':
        verdict = call(runtime, 'handoff_verify', handoff_id=hid, agent_id='caller', claim_epoch=1,
                       verdict='fail', feedback='Keep the same owner for rework')
        assert verdict['ok'], verdict
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = tuple(uow.connection.execute('SELECT status,claimed_by,claim_epoch,result,rejected_reason FROM handoffs '
                                             'WHERE handoff_id=?', (hid,)).fetchone())
    if expired:
        expire(port)
    transfer = build_capacity_admission(deps, capacity=port)
    outcome = client.portal.call(transfer.consume, claim.operation_id)
    assert outcome.state == 'CANCELLED_NO_EFFECT'
    assert outcome.reservation.state == ('EXPIRED_UNCONSUMED' if expired else 'RELEASED')
    assert not attempts.get(held.request.attempt_id).active
    assert client.portal.call(transfer.consume, claim.operation_id) == outcome
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert tuple(uow.connection.execute('SELECT status,claimed_by,claim_epoch,result,rejected_reason FROM handoffs '
                                           'WHERE handoff_id=?', (hid,)).fetchone()) == before
        assert uow.connection.execute('SELECT count(*) FROM execution_capacity_compensations').fetchone()[0] == 1
    assert before[:3] == ({'reject': 'REJECTED', 'complete': 'COMPLETED', 'verify': 'VERIFYING', 'rework': 'CLAIMED'}[decision],
                         'subject', 2 if decision == 'rework' else 1)
    discovery = build_handoff_runtime_candidates(deps)
    page = discovery.prepare_page(replace(lease(runtime, hid), claim_generation=before[2]), limit=4)
    assert page.settled and not page.attempt_ids
    assert runtime[2].opens == 0


@pytest.mark.parametrize('lost_reserve_reply', [False, True])
def test_creator_cancellation_cleans_candidate_without_claim_or_execution(runtime, lost_reserve_reply):
    attempts, port, attempt, hid, gid = prepared(runtime)
    deps, _, client, *_ = runtime[0]

    class Lost:
        def __getattr__(self, name):
            return getattr(port, name)

        async def try_reserve_capacity(self, req):
            self.held = await port.try_reserve_capacity(req)
            raise TimeoutError('The reserve succeeded but the reply was lost')

    if lost_reserve_reply:
        attempts.capacity = Lost()
        with pytest.raises(TimeoutError):
            client.portal.call(attempts.reserve, attempt.request.attempt_id)
        attempts.capacity = port
    else:
        client.portal.call(attempts.reserve, attempt.request.attempt_id)
    cancelled = call(runtime, 'handoff_cancel', handoff_id=hid, agent_id='caller', reason='Retracted before claim')
    assert cancelled['ok'], cancelled
    processor = HandoffRuntimeProcessor(candidates=build_handoff_runtime_candidates(deps), attempts=attempts,
                                        admission=build_capacity_admission(deps, capacity=port))
    client.portal.call(processor.process, lease(runtime, hid))
    assert not attempts.get(attempt.request.attempt_id).active
    assert client.portal.call(processor.process, lease(runtime, hid)).done
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == ('CANCELLED', 0)
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (gid,)).fetchone()[0] == 0
        assert uow.connection.execute('SELECT count(*) FROM execution_operations').fetchone()[0] == 0
    assert runtime[2].opens == 0


@pytest.mark.parametrize('cut', ['before_consume', 'after_consume', 'lost_response'])
def test_canonical_decision_racing_consumption_retires_only_unstarted_work(runtime, cut):
    attempts, port, held, claim, hid = committed(runtime)
    deps, _, client, *_ = runtime[0]

    class DecisionDuringTransfer:
        def __getattr__(self, name):
            return getattr(port, name)

        async def consume_capacity(self, *args):
            async def reject():
                response = await asyncio.to_thread(call, runtime, 'handoff_reject', actor='subject',
                    handoff_id=hid, agent_id='subject', claim_epoch=1, reason='Explicit decision racing transport')
                assert response['ok'], response
            if cut == 'before_consume':
                await reject()
            result = await port.consume_capacity(*args)
            assert result.state == 'CONSUMED'
            if cut != 'before_consume':
                await reject()
            if cut == 'lost_response':
                raise TimeoutError('Consume committed, decision changed, then response was lost')
            return result

    transfer = build_capacity_admission(deps, capacity=DecisionDuringTransfer())
    if cut == 'lost_response':
        with pytest.raises(TimeoutError):
            client.portal.call(transfer.consume, claim.operation_id)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert transfer.repository.get(uow, claim.operation_id).state == 'NEEDS_RECONCILIATION'
        transfer = build_capacity_admission(deps, capacity=port)
    result = client.portal.call(transfer.consume, claim.operation_id)
    assert result.state == 'CANCELLED_NO_EFFECT'
    assert result.reservation.state == 'RELEASED'
    assert result.reservation.consumption == result.consumption
    assert not attempts.get(held.request.attempt_id).active
    assert runtime[2].opens == 0
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == ('REJECTED', 1)
        assert uow.connection.execute('SELECT count(*) FROM execution_receipts').fetchone()[0] == 0
    # Core confirms physical release and still remembers the consumed IDs.
    async def physical():
        ledger = await runtime[0][1].state.embedded_core_host._ledger()
        return await ledger.owned_slot_page()
    assert not client.portal.call(physical).reservations
