"""T24: no-send proof and physical release obligation commit together."""
import pytest

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.execution_dispatch_ownership import reject_unsent_dispatch
from okto_nexus.application.execution_dispatch import begin_execution_send, reserve_execution_dispatch
from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from okto_nexus.errors import OktoNexusError
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime
from test_handoff_runtime_attempts import prepared
from test_handoff_revocation_boundaries import revoke
from test_handoff_creation_commit_cuts import CommitCut


def state(factory):
    tables = ('execution_dispatch_outbox', 'execution_operations', 'execution_sessions',
              'execution_unsent_dispatch_proofs', 'execution_capacity_admissions', 'handoffs')
    with factory.unit_of_work(write=False) as uow:
        return {name: [tuple(row) for row in uow.connection.execute('SELECT * FROM ' + name + ' ORDER BY rowid')]
                for name in tables}


@pytest.mark.parametrize('boundary', ['rollback', 'lost_reply'])
def test_unsent_fence_commit_cut_preserves_consumption_until_proved_release(runtime, boundary):
    setup, binding, native = runtime
    deps, app, client, *_ = setup
    attempts, port, attempt, hid, gid = prepared(runtime)
    pump = app.state.embedded_dispatch_owner.pump
    # Stop this disposable fixture's automatic sender before making work
    # dispatchable; exercise the same public reserve/authorize/fence functions.
    client.portal.call(pump.stop)
    aid = attempt.request.attempt_id
    assert client.portal.call(attempts.reserve, aid).state == 'RESERVED'
    claimed = attempts.claim(aid)
    transfer = build_capacity_admission(deps, capacity=port)
    assert client.portal.call(transfer.consume, claimed.operation_id).state == 'CONSUMED'
    reservation = reserve_execution_dispatch(deps.connection_factory,
        server_id=binding['server_id'], executor_id=binding['executor_id'],
        remote_ready=True, channel=pump.channel)
    assert reservation is not None
    revoke(runtime, gid, 'policy')
    with pytest.raises(OktoNexusError) as denied:
        begin_execution_send(deps.connection_factory, reservation=reservation, remote_ready=True,
            access=pump.access, fresh_publications=pump.fresh_publications, channel=pump.channel)
    before = state(deps.connection_factory)
    cut = CommitCut(deps.connection_factory, boundary)
    with pytest.raises(OSError):
        reject_unsent_dispatch(cut, reservation=reservation, error=denied.value)
    assert cut.fired
    reopened = ConnectionFactory(deps.config)
    if boundary == 'rollback':
        assert state(reopened) == before
        reject_unsent_dispatch(reopened, reservation=reservation, error=denied.value)
    # Never infer physical availability from the local terminal marker.
    observed = client.portal.call(port.get_capacity_reservation, attempt.request)
    assert observed.state == 'CONSUMED' and observed.consumption is not None
    with reopened.unit_of_work(write=False) as uow:
        proof = uow.connection.execute('SELECT * FROM execution_unsent_dispatch_proofs WHERE operation_id=?',
                                       (reservation.operation_id,)).fetchone()
        assert proof['operation_id'] == reservation.operation_id
        assert proof['attempt_no'] == reservation.attempt_no and proof['attempt_token'] == reservation.attempt_token
        assert uow.connection.execute('SELECT reason FROM execution_capacity_admissions').fetchone()[0] == 'UNSENT_DISPATCH_RELEASE_PENDING'
        assert uow.connection.execute('SELECT count(*) FROM execution_receipts').fetchone()[0] == 0
    resumed = build_capacity_admission(deps, capacity=port)
    result = client.portal.call(resumed.consume, claimed.operation_id)
    assert result.state == 'CONSUMED'
    assert client.portal.call(resumed.consume, claimed.operation_id) == result
    released = client.portal.call(port.get_capacity_reservation, attempt.request)
    assert released.state == 'RELEASED' and released.reservation_id == observed.reservation_id
    with reopened.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT reason FROM execution_capacity_admissions').fetchone()[0] == 'UNSENT_DISPATCH_RELEASED'
        assert uow.connection.execute('SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == ('CLAIMED', 1)
        assert uow.connection.execute('SELECT count(*) FROM execution_capacity_compensations').fetchone()[0] == 0
        proofs = uow.connection.execute('SELECT p.operation_id,p.attempt_no,p.attempt_token,o.action '
            'FROM execution_unsent_dispatch_proofs p JOIN execution_operations o '
            'USING(server_id,executor_id,operation_id)').fetchall()
        assert len(proofs) == 2
        # The dependent initial turn is also fenced, with no invented send
        # attempt or Core receipt. Its opening has the actual sender token.
        child = next(row for row in proofs if row['action'] == 'turn.submit')
        assert child['attempt_no'] == 0 and child['attempt_token'] is None
        assert sum(row['operation_id'] == reservation.operation_id for row in proofs) == 1
    assert native.opens == 0 and not native.native.sent
