"""Host proof, canonical ownership and local send fencing share one commit."""
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from okto_nexus.errors import OktoNexusError
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime
from test_handoff_runtime_attempts import prepared


def committed(runtime, **handoff_options):
    attempts, port, attempt, hid, gid = prepared(runtime, **handoff_options)
    client = runtime[0][2]
    held = client.portal.call(attempts.reserve, attempt.request.attempt_id)
    claim = attempts.claim(attempt.request.attempt_id)
    return attempts, port, held, claim, hid


def expire(port):
    original = port._clock
    port._clock = SimpleNamespace(monotonic=lambda: original.monotonic() + 61)


@pytest.mark.parametrize('terminal', ['expired', 'released'])
def test_unconsumed_claim_reopens_once_and_next_generation_executes(runtime, terminal):
    attempts, port, held, claim, hid = committed(runtime)
    deps, _, client, *_ = runtime[0]
    transfer = build_capacity_admission(deps, capacity=port)
    if terminal == 'expired':
        expire(port)
    else:
        client.portal.call(port.release_capacity, held.request, held.reservation.reservation_id, 'CANCELLED')
    result = client.portal.call(transfer.consume, claim.operation_id)
    assert result.state == 'CANCELLED_NO_EFFECT'
    assert client.portal.call(transfer.consume, claim.operation_id) == result
    retired = attempts.get(held.request.attempt_id)
    assert not retired.active and retired.operation_id == claim.operation_id
    assert retired.state == 'FAILED_NO_EFFECT'
    assert runtime[2].opens == 0
    with deps.connection_factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        assert conn.execute('SELECT status,claimed_by,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == ('OPEN', None, 1)
        assert conn.execute('SELECT count(*) FROM execution_capacity_compensations').fetchone()[0] == 1
        assert conn.execute('SELECT lifecycle_state,lease_state FROM execution_sessions').fetchone()[:] == ('FAILED', 'CLOSED')
        assert set(r[0] for r in conn.execute('SELECT admission_state FROM execution_operations')) == {'RESOLVED_TERMINAL'}
        assert conn.execute('SELECT status,ack_level FROM delivery_outbox WHERE operation_id=?', (claim.operation_id,)).fetchone()[:] == ('CANCELLED', 'NONE')
        assert conn.execute('SELECT consumer_kind,read_at FROM message_deliveries d JOIN delivery_outbox o USING(delivery_id) '
            'WHERE o.operation_id=?', (claim.operation_id,)).fetchone()[:] == ('push', None)
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    principal = replace(held.principal, attempt_id='after-proved-no-consumption')
    request = replace(held.request, attempt_id=principal.attempt_id,
                      scope=replace(held.request.scope, session_id='new-session-after-compensation'))
    next_attempt = attempts.prepare(principal=principal, request=request, claim_generation=1)
    client.portal.call(attempts.reserve, next_attempt.request.attempt_id)
    next_claim = attempts.claim(next_attempt.request.attempt_id)
    assert next_claim.operation_id != claim.operation_id
    assert client.portal.call(transfer.consume, next_claim.operation_id).state == 'CONSUMED'
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT p.* FROM execution_operations p JOIN execution_domain_deliveries m "
            "USING(server_id,executor_id,operation_id) WHERE m.domain_operation_id=? AND p.action='turn.submit'",
            (next_claim.operation_id,)).fetchone()
    wait_receipt(runtime[0], dict(row))
    # A late duplicate compensation cannot reopen the newer claim.
    assert client.portal.call(transfer.consume, claim.operation_id) == result
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == ('CLAIMED', 2)
    assert runtime[2].opens == len(runtime[2].native.sent) == 1


@pytest.mark.parametrize('fault', ['missing', 'timeout', 'wrong_request', 'stale_revision', 'consumed_then_released'])
def test_uncertain_or_nonmatching_proof_never_reopens_claim(runtime, fault):
    attempts, port, held, claim, hid = committed(runtime)
    deps, _, client, *_ = runtime[0]
    transfer = build_capacity_admission(deps, capacity=port)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        admission = transfer.repository.get(uow, claim.operation_id)
    if fault == 'consumed_then_released':
        client.portal.call(port.consume_capacity, held.request, held.reservation.reservation_id, admission.consumption)
        observed = client.portal.call(port.release_capacity, held.request, held.reservation.reservation_id, 'CANCELLED')
        assert observed.consumption == admission.consumption
        # Even a host release is insufficient if the Server's send fence was
        # crossed. It may have run before stopping; never infer no-effect.
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE execution_dispatch_outbox SET dispatch_state='SENDING' WHERE operation_id IN "
                '(SELECT operation_id FROM execution_domain_deliveries WHERE domain_operation_id=?)', (claim.operation_id,))
    else:
        observed = client.portal.call(port.release_capacity, held.request, held.reservation.reservation_id, 'CANCELLED')
    if fault == 'wrong_request':
        observed = replace(observed, request=replace(held.request, ttl_ms=1000))
    if fault == 'stale_revision':
        # The stored observation advanced; replaying an older valid DTO must
        # be rejected, rather than testing the DTO's positive-integer check.
        newer = replace(admission.reservation, capacity_revision=observed.capacity_revision + 1)
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('UPDATE execution_capacity_admissions SET reservation_json=? WHERE domain_operation_id=?',
                                  (json.dumps(newer.to_dict()), claim.operation_id))

    class Observe:
        async def get_capacity_reservation(self, req):
            if fault == 'timeout':
                raise TimeoutError('No response is not a no-effect proof')
            return None if fault == 'missing' else observed

        async def consume_capacity(self, *args):
            return await port.consume_capacity(*args)

    transfer.capacity = Observe()
    with pytest.raises(Exception):
        client.portal.call(transfer.consume, claim.operation_id)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert transfer.repository.get(uow, claim.operation_id).state == 'NEEDS_RECONCILIATION'
        assert uow.connection.execute('SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == ('CLAIMED', 1)
        assert uow.connection.execute('SELECT count(*) FROM execution_capacity_compensations').fetchone()[0] == 0
    assert attempts.get(held.request.attempt_id).active
    assert runtime[2].opens == 0


def test_expiry_between_lookup_and_consumption_is_compensated(runtime):
    attempts, port, held, claim, hid = committed(runtime)
    deps, _, client, *_ = runtime[0]

    class ExpireDuringTransfer:
        async def get_capacity_reservation(self, req):
            return await port.get_capacity_reservation(req)

        async def consume_capacity(self, *args):
            expire(port)
            return await port.consume_capacity(*args)

    transfer = build_capacity_admission(deps, capacity=ExpireDuringTransfer())
    result = client.portal.call(transfer.consume, claim.operation_id)
    assert result.state == 'CANCELLED_NO_EFFECT' and result.reservation.state == 'EXPIRED_UNCONSUMED'
    # The original ticket can never be consumed late, even with identical IDs.
    from nexus_connector_core import CoreError
    with pytest.raises(CoreError, match='RECOVERING'):
        client.portal.call(port.consume_capacity, held.request, held.reservation.reservation_id, result.consumption)
    late = client.portal.call(port.get_capacity_reservation, held.request)
    assert late.state == 'EXPIRED_UNCONSUMED' and late.consumption is None
    assert not attempts.get(held.request.attempt_id).active
    assert runtime[2].opens == 0


@pytest.mark.parametrize('expired', [False, True])
def test_revoked_automation_retires_original_unconsumed_ticket(runtime, expired):
    from test_runtime_policy_defaults import save
    attempts, port, held, claim, hid = committed(runtime)
    deps, _, client, *_ = runtime[0]
    assert save(runtime[0], agent='subject', broadcast_handoff_auto_claim=False).status_code == 200
    if expired:
        expire(port)
    transfer = build_capacity_admission(deps, capacity=port)
    result = client.portal.call(transfer.consume, claim.operation_id)
    assert result.state == 'CANCELLED_NO_EFFECT'
    assert result.reservation.state == ('EXPIRED_UNCONSUMED' if expired else 'RELEASED')
    assert not attempts.get(held.request.attempt_id).active
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[0] == 'OPEN'
    assert runtime[2].opens == 0


@pytest.mark.parametrize('changed', ['dispatch', 'operation_hash'])
def test_diverging_canonical_state_rolls_back_compensation(runtime, changed):
    attempts, port, held, claim, hid = committed(runtime)
    deps, _, client, *_ = runtime[0]
    expire(port)
    with deps.connection_factory.unit_of_work() as uow:
        if changed == 'dispatch':
            uow.connection.execute("UPDATE execution_dispatch_outbox SET dispatch_state='SENDING' WHERE operation_id IN "
                '(SELECT operation_id FROM execution_domain_deliveries WHERE domain_operation_id=?)', (claim.operation_id,))
        else:
            uow.connection.execute("UPDATE execution_capacity_admissions SET consumption_json="
                "json_set(consumption_json,'$.turn_intent_hash',?) WHERE domain_operation_id=?", ('sha256:' + '0' * 64, claim.operation_id))
    transfer = build_capacity_admission(deps, capacity=port)
    with pytest.raises(OktoNexusError):
        client.portal.call(transfer.consume, claim.operation_id)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert transfer.repository.get(uow, claim.operation_id).state == 'NEEDS_RECONCILIATION'
        assert uow.connection.execute('SELECT count(*) FROM execution_capacity_compensations').fetchone()[0] == 0
        assert uow.connection.execute('SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == ('CLAIMED', 1)
    assert attempts.get(held.request.attempt_id).active
    assert runtime[2].opens == 0


def test_compensation_rollback_retains_claim_and_retry_finishes_atomically(runtime, monkeypatch):
    attempts, port, held, claim, hid = committed(runtime)
    deps, _, client, *_ = runtime[0]
    expire(port)
    transfer = build_capacity_admission(deps, capacity=port)
    original = transfer.recover

    def cut(uow, operation_id):
        original(uow, operation_id)
        raise OSError('Cut after reopen, before committing proof and cancellation')

    monkeypatch.setattr(transfer, 'recover', cut)
    with pytest.raises(OSError):
        client.portal.call(transfer.consume, claim.operation_id)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM execution_capacity_compensations').fetchone()[0] == 0
        assert uow.connection.execute('SELECT status FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[0] == 'CLAIMED'
        assert set(r[0] for r in uow.connection.execute('SELECT admission_state FROM execution_operations')) == {'ACCEPTED'}
    assert attempts.get(held.request.attempt_id).active
    resumed = build_capacity_admission(deps, capacity=port)
    assert client.portal.call(resumed.consume, claim.operation_id).state == 'CANCELLED_NO_EFFECT'
    assert not attempts.get(held.request.attempt_id).active
    assert runtime[2].opens == 0


@pytest.mark.parametrize('warm', [False, True])
@pytest.mark.parametrize('consumed_before_cleanup', [False, True])
def test_one_shot_compensation_closes_slot_without_sending_work_or_error_reply(runtime, monkeypatch, warm, consumed_before_cleanup):
    from okto_nexus.application import one_shot_capacity
    from okto_nexus.application.one_shot_settings import read, save
    from okto_nexus.application.execution_domain_delivery import delivery_session_context
    from test_sender_sessions import Peers, configure
    from test_one_shot_runtime import query, wait_until
    from test_handoff_automation_principal import prepare, candidate
    from test_canonical_result_publication import workspace
    from test_capacity_authority import request

    setup, binding, _ = runtime
    deps, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    owner.host.capacity_enabled = True
    peers = Peers()
    owner.native_factory = peers
    configure(setup, binding, 'one_shot')
    handoffs, hid, gid = prepare(runtime)
    with deps.connection_factory.unit_of_work() as uow:
        settings = read(uow.connection)
        save(uow.connection, expected_revision=settings['revision'],
             settings=settings['settings'] | dict(max_parallel=2, warm_instances=int(warm)))
    if warm:
        wait_until(setup, lambda: query(setup, "SELECT 1 FROM one_shot_slots WHERE state='WARM'"))
    monkeypatch.setattr(one_shot_capacity, 'reserve_warm', lambda *args, **kwargs: None)
    context = candidate(runtime, handoffs, hid, gid)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        opened = uow.connection.execute("SELECT expected_revisions_json FROM execution_operations WHERE action='runtime.open'").fetchone()
        _, affinity = delivery_session_context(uow, binding['endpoint_id'], sender_agent_id='caller')
    req = request(setup, binding, scope=json.loads(opened[0]) if warm else None,
                  unit='next_turn' if warm else 'new_session')
    req = replace(req, attempt_id=context.request_id, affinity_key=affinity.capacity_key(req.scope.session_id), ttl_ms=60000)
    port = client.portal.call(owner.execution_capacity)
    held = client.portal.call(port.try_reserve_capacity, req)
    assert getattr(held, 'state', None) == 'HELD', held
    with deps.connection_factory.unit_of_work() as uow:
        result = handoffs.claim_managed_in_transaction(uow, workspace_id=workspace(setup), handoff_id=hid,
            agent_id='subject', context=context, runtime_endpoint_id=binding['endpoint_id'],
            execution_grant_id=gid, idempotency_key=context.request_id, capacity_reservation=held)
    identity = result['runtime_operation']['operation_id']
    transfer = build_capacity_admission(deps, capacity=port)
    if consumed_before_cleanup:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            original = transfer.repository.get(uow, identity)
        client.portal.call(port.consume_capacity, req, held.reservation_id, original.consumption)
        released = client.portal.call(port.release_capacity, req, held.reservation_id, 'CANCELLED')
        assert released.state == 'RELEASED' and released.consumption == original.consumption
    else:
        expire(port)
    assert client.portal.call(transfer.consume, identity).state == 'CANCELLED_NO_EFFECT'
    wait_until(setup, lambda: not query(setup, 'SELECT 1 FROM one_shot_slots WHERE call_id=?', (identity,)))
    assert query(setup, 'SELECT state,started_at,notification_message_id FROM one_shot_calls WHERE call_id=?',
                 (identity,))[0][:] == ('CANCELLED', None, None)
    assert query(setup, 'SELECT status FROM handoffs WHERE handoff_id=?', (hid,))[0][0] == 'OPEN'
    assert all(action != 'send_turn' for peer in peers.sessions.values() for action, _ in peer.sent)


def test_old_schedule_generation_cannot_cancel_new_candidate(runtime):
    from okto_nexus.bootstrap.handoff_runtime_scheduler import build_handoff_runtime_candidates
    from test_handoff_runtime_candidates import enable_capacity, lease

    attempts, port, held, claim, hid = committed(runtime)
    deps, _, client, *_ = runtime[0]
    enable_capacity(runtime)
    expire(port)
    result = client.portal.call(build_capacity_admission(deps, capacity=port).consume, claim.operation_id)
    assert result.state == 'CANCELLED_NO_EFFECT'
    discovery = build_handoff_runtime_candidates(deps)
    old_lease = lease(runtime, hid)
    next_lease = replace(old_lease, claim_generation=1)
    page = discovery.prepare_page(next_lease, limit=4)
    assert len(page.attempt_ids) == 1
    current_id = page.attempt_ids[0]
    current = attempts.get(current_id)
    assert current.state == 'WAITING' and current.active and current.claim_generation == 1
    old_page = discovery.prepare_page(old_lease, limit=4)
    assert old_page.settled and old_page.attempt_ids == ()
    assert attempts.get(current_id) == current
    assert discovery.prepare_page(next_lease, limit=4).attempt_ids == (current_id,)


def test_scheduler_restarts_after_compensation_and_discovers_next_claim_generation(runtime):
    import asyncio
    import time
    from okto_nexus.bootstrap.handoff_runtime_scheduler import build_handoff_runtime_scheduler
    from test_handoff_runtime_candidates import enable_capacity

    attempts, port, held, claim, hid = committed(runtime)
    setup = runtime[0]
    deps, _, client, *_ = setup
    enable_capacity(runtime)
    expire(port)
    clock = [time.time()]

    def count(state):
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return uow.connection.execute('SELECT count(*) FROM execution_capacity_admissions WHERE state=?', (state,)).fetchone()[0]

    async def drive(scheduler, state):
        try:
            async with asyncio.timeout(15):
                while not count(state):
                    scheduler.tick()
                    await asyncio.sleep(.02)
                    clock[0] += 1
        finally:
            assert await scheduler.aclose(timeout=5) == 0

    async def run():
        scheduler = build_handoff_runtime_scheduler(deps, capacity=port,
            now=lambda: clock[0], monotonic=lambda: clock[0])
        await drive(scheduler, 'CANCELLED_NO_EFFECT')
        clock[0] += 6
        restarted = build_handoff_runtime_scheduler(deps, capacity=port,
            now=lambda: clock[0], monotonic=lambda: clock[0])
        await drive(restarted, 'CONSUMED')

    client.portal.call(run)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        assert conn.execute('SELECT count(*) FROM handoff_runtime_attempts').fetchone()[0] == 2
        assert conn.execute('SELECT count(*) FROM execution_capacity_compensations').fetchone()[0] == 1
        assert conn.execute('SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == ('CLAIMED', 2)
        turn = conn.execute("SELECT p.* FROM execution_operations p JOIN execution_domain_deliveries m "
            "USING(server_id,executor_id,operation_id) JOIN execution_capacity_admissions a ON a.domain_operation_id=m.domain_operation_id "
            "WHERE a.state='CONSUMED' AND p.action='turn.submit'").fetchone()
    wait_receipt(setup, dict(turn))
    assert runtime[2].opens == len(runtime[2].native.sent) == 1
