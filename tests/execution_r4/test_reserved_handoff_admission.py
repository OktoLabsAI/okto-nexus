"""A real host reservation and canonical claim share exact operation identities."""
from dataclasses import replace
import json
import pytest

from okto_nexus.application.execution_domain_delivery import delivery_session_context
from okto_nexus.application.execution_dispatch import reserve_execution_dispatch
from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from okto_nexus.errors import OktoNexusError
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt, admit
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, assert_unclaimed
from test_handoff_automation_principal import prepare, candidate
from test_canonical_result_publication import current_turn, workspace
from test_capacity_authority import request


def reserve(runtime, *, opening=None):
    service, hid, gid = prepare(runtime)
    setup, binding, _ = runtime
    deps, app, client, *_ = setup
    context = candidate(runtime, service, hid, gid)
    with deps.connection_factory.unit_of_work() as uow:
        _, affinity = delivery_session_context(uow, binding['endpoint_id'], sender_agent_id='caller')
    owner = app.state.embedded_dispatch_owner
    owner.host.capacity_enabled = True
    req = request(setup, binding, scope=opening['scope'] if opening else None,
                  unit='next_turn' if opening else 'new_session')
    req = replace(req, attempt_id=context.request_id, affinity_key=affinity.opaque_key, ttl_ms=60000)
    async def acquire():
        port = await owner.execution_capacity()
        return port, await port.try_reserve_capacity(req)
    port, held = client.portal.call(acquire)
    assert getattr(held, 'state', None) == 'HELD', held
    def claim(reservation=held):
        with deps.connection_factory.unit_of_work() as uow:
            return service.claim_managed_in_transaction(uow, workspace_id=workspace(setup),
                handoff_id=hid, agent_id='subject', context=context,
                runtime_endpoint_id=binding['endpoint_id'], execution_grant_id=gid,
                idempotency_key=context.request_id, capacity_reservation=reservation)
    return service, hid, gid, port, held, claim


@pytest.mark.parametrize('lose_consume_response', [False, True])
def test_cold_reserved_claim_waits_for_transfer_and_retries_same_operations(runtime, lose_consume_response):
    setup, binding, native = runtime
    deps, app, client, *_ = setup
    _, hid, gid, port, held, claim = reserve(runtime)
    result = claim()
    operation = result['runtime_operation']['operation_id']
    assert claim()['runtime_operation']['operation_id'] == operation
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT session_id FROM execution_sessions').fetchone()[0] == held.request.scope.session_id
        assert uow.connection.execute('SELECT state FROM execution_capacity_admissions').fetchone()[0] == 'WAITING_CONSUMPTION'
    channel = app.state.embedded_dispatch_owner.channel
    assert reserve_execution_dispatch(deps.connection_factory, server_id=channel.server_id,
        executor_id=channel.executor_id, channel=channel, remote_ready=True) is None
    assert native.opens == 0

    class LoseOnce:
        async def consume_capacity(self, *args):
            # Acquiring another Server writer during host I/O must succeed.
            with deps.connection_factory.unit_of_work() as uow:
                assert uow.connection.execute('SELECT 1').fetchone()[0] == 1
            self.observed = await port.consume_capacity(*args)
            raise TimeoutError('Lost host reply after committed consumption')

    if lose_consume_response:
        adapter = LoseOnce()
        transfer = build_capacity_admission(deps, capacity=adapter)
        with pytest.raises(TimeoutError):
            client.portal.call(transfer.consume, operation)
        assert adapter.observed.state == 'CONSUMED'
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT state FROM execution_capacity_admissions').fetchone()[0] == 'NEEDS_RECONCILIATION'
        assert native.opens == 0
    transfer = build_capacity_admission(deps, capacity=port)
    assert client.portal.call(transfer.consume, operation).state == 'CONSUMED'
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    assert turn['session_id'] == held.request.scope.session_id
    assert native.opens == len(native.native.sent) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (gid,)).fetchone()[0] == 1
        assert uow.connection.execute('SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == ('CLAIMED', 1)
        assert uow.connection.execute('SELECT count(*) FROM execution_operations').fetchone()[0] == 2


def test_earlier_turn_admitted_after_host_reserve_keeps_handoff_open(runtime):
    setup, binding, native = runtime
    # This existing idle session is the only shared affinity.
    setup[1].state.embedded_dispatch_owner.host.capacity_enabled = True
    opened = admit(setup, binding, 'before-reserve', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    _, hid, gid, port, held, claim = reserve(runtime, opening=opened)
    later = admit(setup, binding, 'ordinary-before-claim', 'turn.submit',
                  session_id=opened['session_id'], text='Earlier admitted work has priority')
    with pytest.raises(OktoNexusError, match='EARLIER_WORK_PENDING'):
        claim()
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == ('OPEN', 0)
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (gid,)).fetchone()[0] == 0
        assert uow.connection.execute('SELECT count(*) FROM execution_capacity_admissions').fetchone()[0] == 0
    async def release():
        return await port.release_capacity(held.request, held.reservation_id, 'LOST')
    assert setup[2].portal.call(release).state == 'RELEASED'
    wait_receipt(setup, later)
    assert native.native.sent == [('send_turn', later['operation_id'])]


def test_failed_link_persistence_rolls_back_claim_grant_session_and_operations(runtime, monkeypatch):
    service, hid, gid, port, held, claim = reserve(runtime)
    repository = service.runtime_work.capacity_admissions
    attach = repository.attach
    def fail(uow, **kwargs):
        attach(uow, **kwargs)
        raise OSError('Cut after capacity linkage before commit')
    monkeypatch.setattr(repository, 'attach', fail)
    with pytest.raises(OSError):
        claim()
    assert_unclaimed(runtime, hid, gid)
    with runtime[0][0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM execution_capacity_admissions').fetchone()[0] == 0
        assert uow.connection.execute('SELECT count(*) FROM execution_sessions').fetchone()[0] == 0
    async def release():
        return await port.release_capacity(held.request, held.reservation_id, 'LOST')
    assert runtime[0][2].portal.call(release).state == 'RELEASED'


def test_reserved_turn_blocks_later_ordinary_turn_but_not_control(runtime):
    from types import SimpleNamespace
    from test_sender_sessions import complete
    setup, binding, native = runtime
    deps, app, client, *_ = setup
    _, _, _, port, _, claim = reserve(runtime)
    result = claim()
    transfer = build_capacity_admission(deps, capacity=port)
    client.portal.call(transfer.consume, result['runtime_operation']['operation_id'])
    winner = current_turn(setup)
    wait_receipt(setup, winner)
    later = admit(setup, binding, 'after-reserved-winner', 'turn.submit',
                  session_id=winner['session_id'], text='Preserve normal queued work behind the winner')
    channel = app.state.embedded_dispatch_owner.channel
    assert reserve_execution_dispatch(deps.connection_factory, server_id=channel.server_id,
        executor_id=channel.executor_id, channel=channel, remote_ready=True) is None
    interrupted = admit(setup, binding, 'reserved-control', 'turn.interrupt', session_id=winner['session_id'],
                        target=dict(kind='current_run', expected_turn_id=None))
    wait_receipt(setup, interrupted)
    assert native.native.sent == [('send_turn', winner['operation_id']), ('interrupt', interrupted['operation_id'])]
    complete(setup, SimpleNamespace(sessions={winner['session_id']: native.native}), winner, 'Native completion evidence')
    wait_receipt(setup, later)
    assert native.native.sent[-1] == ('send_turn', later['operation_id'])
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status FROM handoffs').fetchone()[0] == 'CLAIMED'


def test_reserved_warm_one_shot_uses_existing_physical_slot(runtime, monkeypatch):
    from test_sender_sessions import Peers, configure
    from test_one_shot_runtime import query, wait_until
    from okto_nexus.application import one_shot_capacity
    from okto_nexus.application.one_shot_settings import read, save
    setup, binding, _ = runtime
    deps, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    owner.host.capacity_enabled = True
    peers = Peers()
    owner.native_factory = peers
    configure(setup, binding, 'one_shot')
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='none' WHERE endpoint_id=?", (binding['endpoint_id'],))
    service, hid, gid = prepare(runtime)
    with deps.connection_factory.unit_of_work() as uow:
        settings = read(uow.connection)
        save(uow.connection, expected_revision=settings['revision'],
             settings=settings['settings'] | dict(max_parallel=2, warm_instances=1))
    wait_until(setup, lambda: query(setup, "SELECT 1 FROM one_shot_slots WHERE state='WARM'"))
    # Refill is a separate independent opening; isolate this slot's transfer.
    monkeypatch.setattr(one_shot_capacity, 'reserve_warm', lambda *args, **kwargs: None)
    context = candidate(runtime, service, hid, gid)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        opened = uow.connection.execute("SELECT session_id,expected_revisions_json FROM execution_operations WHERE action='runtime.open'").fetchone()
        _, affinity = delivery_session_context(uow, binding['endpoint_id'], sender_agent_id='caller')
    req = replace(request(setup, binding, scope=json.loads(opened['expected_revisions_json']), unit='next_turn'),
                  attempt_id=context.request_id, affinity_key=affinity.opaque_key, ttl_ms=60000)
    async def acquire():
        port = await owner.execution_capacity()
        ledger = await owner.host._ledger()
        before = await ledger.owned_slot_page()
        return port, ledger, before, await port.try_reserve_capacity(req)
    port, ledger, before, held = client.portal.call(acquire)
    assert getattr(held, 'state', None) == 'HELD', held
    assert len(before.reservations) == 1
    with deps.connection_factory.unit_of_work() as uow:
        result = service.claim_managed_in_transaction(uow, workspace_id=workspace(setup),
            handoff_id=hid, agent_id='subject', context=context, runtime_endpoint_id=binding['endpoint_id'],
            execution_grant_id=gid, idempotency_key=context.request_id, capacity_reservation=held)
    transfer = build_capacity_admission(deps, capacity=port)
    admitted = client.portal.call(transfer.consume, result['runtime_operation']['operation_id'])
    assert admitted.consumption.opening_operation_id is None
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    assert turn['session_id'] == opened['session_id']
    assert len(peers.sessions) == 1
    assert client.portal.call(ledger.owned_slot_page).reservations == before.reservations
