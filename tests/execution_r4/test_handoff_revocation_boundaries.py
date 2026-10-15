"""Current authority is required at every competitive acquisition boundary."""
import asyncio
from contextlib import contextmanager
import time
from types import SimpleNamespace

import pytest

from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from okto_nexus.errors import OktoNexusError
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime
from test_handoff_runtime_attempts import prepared
from test_one_shot_runtime import query
from test_runtime_policy_defaults import save


def revoke(runtime, gid, kind):
    setup, binding, _ = runtime
    deps, _, client, headers, *_ = setup
    if kind == 'policy':
        response = save(setup, agent='subject', broadcast_handoff_auto_claim=False)
        assert response.status_code == 200, response.text
    elif kind == 'grant':
        response = client.delete('/api/v1/harness/grants/' + gid, headers=headers['operator'])
        assert response.status_code == 200, response.text
    else:
        # Reproduce the persisted connection revocation used by replacement.
        # The test isolates its boundary from unrelated onboarding work.
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agent_endpoints SET enabled=0,activation_state='revoked' "
                'WHERE endpoint_id=?', (binding['endpoint_id'],))


@pytest.mark.parametrize('kind', ['policy', 'grant', 'binding'])
@pytest.mark.parametrize('cut', ['before_assess', 'after_assess', 'after_reserve',
                                  'before_consume', 'after_consume', 'before_dispatch', 'before_initial_lease'])
def test_revocation_cannot_cross_acquisition_boundary(runtime, kind, cut, warm=False, lose_release=False):
    setup, _, native = runtime
    deps, app, client, *_ = setup
    attempts, port, attempt, hid, gid = prepared(runtime, warm=warm)
    aid = attempt.request.attempt_id
    calls = []
    releases = []

    def invalidate():
        calls.append(cut)
        revoke(runtime, gid, kind)

    class CutPort:
        def __getattr__(self, name):
            return getattr(port, name)

        async def assess_capacity(self, req):
            value = await port.assess_capacity(req)
            if cut == 'after_assess':
                await asyncio.to_thread(invalidate)
            return value

        async def try_reserve_capacity(self, req):
            value = await port.try_reserve_capacity(req)
            if cut == 'after_reserve':
                await asyncio.to_thread(invalidate)
            return value

        async def consume_capacity(self, *args):
            value = await port.consume_capacity(*args)
            if cut == 'after_consume':
                await asyncio.to_thread(invalidate)
            return value

        async def release_capacity(self, *args):
            value = await port.release_capacity(*args)
            releases.append(value)
            if lose_release and len(releases) == 1:
                raise TimeoutError('Host release committed but reply was lost')
            return value

    attempts.capacity = CutPort()
    if cut == 'before_assess':
        invalidate()
    if cut in {'before_assess', 'after_assess'}:
        with pytest.raises(OktoNexusError):
            client.portal.call(attempts.reserve, aid)
    else:
        assert client.portal.call(attempts.reserve, aid).state == 'RESERVED'
    if cut in {'before_assess', 'after_assess', 'after_reserve'}:
        with pytest.raises(OktoNexusError):
            attempts.claim(aid)
        final = client.portal.call(attempts.release, aid)
        assert final.state == 'CANCELLED_NO_EFFECT' and not final.active
        assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == ('OPEN', 0)
        assert query(setup, 'SELECT count(*) FROM runtime_handoff_bindings')[0][0] == 0
        assert query(setup, 'SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (gid,))[0][0] == 0
    else:
        committed = attempts.claim(aid)
        transfer = build_capacity_admission(deps, capacity=CutPort())
        if cut == 'before_consume':
            invalidate()
        if cut == 'before_dispatch':
            from okto_nexus.application.handoff_runtime_service import HandoffRuntimeService
            from okto_nexus.bootstrap.handoff_runtime_scheduler import build_handoff_runtime_scheduler
            service = HandoffRuntimeService(build_handoff_runtime_scheduler(deps,
                capacity=CutPort(), acquisition_enabled=False))
            lock = app.state.embedded_dispatch_owner.pump.send_lock
            client.portal.call(lock.acquire)
            try:
                assert client.portal.call(transfer.consume, committed.operation_id).state == 'CONSUMED'
                invalidate()
            finally:
                client.portal.call(lock.release)
            client.portal.call(service.start)
            try:
                until = time.monotonic() + 15
                while query(setup, "SELECT 1 FROM execution_dispatch_outbox WHERE dispatch_state<>'RESOLVED_TERMINAL' "
                        'AND operation_id IN (SELECT operation_id FROM execution_domain_deliveries WHERE domain_operation_id=?)',
                        (committed.operation_id,)):
                    assert time.monotonic() < until
                    time.sleep(.02)
                # The host must not retain an unused physical slot forever after
                # the Server proves that dispatch was rejected before any send.
                observed = client.portal.call(port.get_capacity_reservation, attempt.request)
                while observed.state != 'RELEASED' and time.monotonic() < until:
                    time.sleep(.02)
                    observed = client.portal.call(port.get_capacity_reservation, attempt.request)
                assert observed.state == 'RELEASED', observed
                while query(setup, "SELECT 1 FROM execution_capacity_admissions WHERE state<>'CONSUMED'"):
                    assert time.monotonic() < until
                    time.sleep(.02)
                assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == ('CLAIMED', 1)
                assert query(setup, 'SELECT count(*) FROM execution_capacity_compensations')[0][0] == 0
                if lose_release:
                    assert len(releases) >= 2 and releases[0] == releases[1]
            finally:
                client.portal.call(service.aclose)
        elif cut == 'before_initial_lease':
            owner = app.state.embedded_dispatch_owner
            original = owner._request_grant
            async def revoke_before_lease(request):
                if request['purpose'] == 'initial' and not calls:
                    await asyncio.to_thread(invalidate)
                return await original(request)
            owner._request_grant = revoke_before_lease
            client.portal.call(transfer.consume, committed.operation_id)
            until = time.monotonic() + 15
            while query(setup, "SELECT 1 FROM execution_sessions WHERE lifecycle_state<>'CLOSED'"):
                assert time.monotonic() < until
                time.sleep(.02)
            assert client.portal.call(port.get_capacity_reservation, attempt.request).state == 'RELEASED'
            assert query(setup, 'SELECT state FROM execution_session_containment')[0][0] == 'RELEASED'
            assert not owner.agents.blocked and owner.failure is None
        else:
            result = client.portal.call(transfer.consume, committed.operation_id)
            assert result.state == 'CANCELLED_NO_EFFECT'
            assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == ('OPEN', 1)
            assert client.portal.call(transfer.consume, committed.operation_id) == result
        assert query(setup, 'SELECT count(*) FROM runtime_handoff_bindings')[0][0] == 1
        assert query(setup, 'SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (gid,))[0][0] == 1
    assert calls == [cut]
    assert native.opens == int(warm) and not native.native.sent
    assert not query(setup, "SELECT 1 FROM execution_receipts r JOIN execution_operations o "
        "USING(server_id,executor_id,operation_id) WHERE o.action='turn.submit' AND r.possible_effect=1")
    if warm:
        assert not native.native.stopped


@pytest.mark.parametrize('kind', ['policy', 'grant'])
@pytest.mark.parametrize('lose_release', [False, True])
def test_unsent_warm_release_preserves_native_session_and_retries_original_ticket(runtime, kind, lose_release):
    test_revocation_cannot_cross_acquisition_boundary(runtime, kind, 'before_dispatch',
                                                     warm=True, lose_release=lose_release)


@pytest.mark.parametrize('fault', ['missing_proof', 'wrong_attempt_token', 'commit_rollback', 'lost_commit_reply'])
def test_unsent_release_recovers_only_from_exact_proof_and_original_operation(runtime, monkeypatch, fault):
    setup, _, native = runtime
    deps, app, client, *_ = setup
    attempts, port, attempt, hid, gid = prepared(runtime)
    aid = attempt.request.attempt_id
    assert client.portal.call(attempts.reserve, aid).state == 'RESERVED'
    committed = attempts.claim(aid)
    transfer = build_capacity_admission(deps, capacity=port)
    lock = app.state.embedded_dispatch_owner.pump.send_lock
    client.portal.call(lock.acquire)
    try:
        client.portal.call(transfer.consume, committed.operation_id)
        revoke(runtime, gid, 'policy')
    finally:
        client.portal.call(lock.release)
    until = time.monotonic() + 15
    while not query(setup, "SELECT 1 FROM execution_capacity_admissions WHERE reason='UNSENT_DISPATCH_RELEASE_PENDING'"):
        assert time.monotonic() < until
        time.sleep(.02)
    proofs = [dict(row) for row in query(setup, 'SELECT * FROM execution_unsent_dispatch_proofs')]
    if fault in {'missing_proof', 'wrong_attempt_token'}:
        with deps.connection_factory.unit_of_work() as uow:
            if fault == 'missing_proof':
                uow.connection.execute('DELETE FROM execution_unsent_dispatch_proofs')
            else:
                uow.connection.execute("UPDATE execution_unsent_dispatch_proofs SET attempt_token='foreign-attempt'")
        with pytest.raises(OktoNexusError, match='UNSENT_DISPATCH_PROOF_REQUIRED'):
            client.portal.call(transfer.consume, committed.operation_id)
        # No RPC was authorized by a missing/mismatched Server send fence.
        assert client.portal.call(port.get_capacity_reservation, attempt.request).state == 'CONSUMED'
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('DELETE FROM execution_unsent_dispatch_proofs')
            for proof in proofs:
                uow.connection.execute('INSERT INTO execution_unsent_dispatch_proofs (' + ','.join(proof) + ') '
                    'VALUES (' + ','.join('?' for _ in proof) + ')', tuple(proof.values()))
    else:
        with monkeypatch.context() as patch:
            if fault == 'commit_rollback':
                original = transfer.repository.released_after_unsent_refusal
                def cut(*args):
                    original(*args)
                    raise OSError('Release facts updated but Server transaction rolled back')
                patch.setattr(transfer.repository, 'released_after_unsent_refusal', cut)
            else:
                factory = transfer.factory
                once = []
                @contextmanager
                def cut_after_commit(**options):
                    with factory.unit_of_work(**options) as uow:
                        yield uow
                        recorded = uow.connection.execute("SELECT 1 FROM execution_capacity_admissions "
                            "WHERE reason='UNSENT_DISPATCH_RELEASED'").fetchone()
                    if recorded and not once:
                        once.append(True)
                        raise OSError('Server release committed but reply lost')
                patch.setattr(transfer, 'factory', SimpleNamespace(unit_of_work=cut_after_commit))
            with pytest.raises(OSError):
                client.portal.call(transfer.consume, committed.operation_id)
        assert client.portal.call(port.get_capacity_reservation, attempt.request).state == 'RELEASED'
        reason = query(setup, 'SELECT reason FROM execution_capacity_admissions')[0][0]
        assert reason == ('UNSENT_DISPATCH_RELEASE_PENDING' if fault == 'commit_rollback' else 'UNSENT_DISPATCH_RELEASED')
    result = client.portal.call(transfer.consume, committed.operation_id)
    assert result.state == 'CONSUMED' and result.reservation.state == 'RELEASED'
    assert client.portal.call(transfer.consume, committed.operation_id) == result
    assert attempts.claim(aid).operation_id == committed.operation_id
    assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == ('CLAIMED', 1)
    assert query(setup, 'SELECT count(*) FROM execution_capacity_compensations')[0][0] == 0
    assert query(setup, 'SELECT count(*) FROM handoff_runtime_attempts')[0][0] == 1
    assert native.opens == 0
