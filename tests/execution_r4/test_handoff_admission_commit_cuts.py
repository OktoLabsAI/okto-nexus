"""T24: writer rollback versus lost commit reply use the same retained intent."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from okto_nexus.bootstrap.handoff_runtime_attempts import build_handoff_runtime_attempts
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime
from test_canonical_result_publication import current_turn
from test_handoff_runtime_attempts import prepared, ObservedPort


@pytest.mark.parametrize('stage', ['RESERVING', 'RESERVED', 'CONSUMED'])
@pytest.mark.parametrize('boundary', ['rollback', 'lost_reply'])
def test_admission_commit_cut_recovers_original_ticket_and_one_native_execution(runtime, stage, boundary):
    service, port, attempt, hid, gid = prepared(runtime)
    setup = runtime[0]
    deps, _, client, *_ = setup
    aid = attempt.request.attempt_id
    observed = ObservedPort(runtime, port)
    service.capacity = observed
    factory = service.factory
    fired = []

    def state(uow):
        if stage == 'CONSUMED':
            row = uow.connection.execute('SELECT c.state FROM execution_capacity_admissions c '
                'JOIN handoff_runtime_attempts a ON a.operation_id=c.domain_operation_id WHERE a.attempt_id=?', (aid,)).fetchone()
        else:
            row = uow.connection.execute('SELECT state FROM handoff_runtime_attempts WHERE attempt_id=?', (aid,)).fetchone()
        return row[0] if row else None

    @contextmanager
    def cut(**kwargs):
        changed = False
        with factory.unit_of_work(**kwargs) as uow:
            before = state(uow)
            yield uow
            changed = not fired and kwargs.get('write') is not False and before != stage and state(uow) == stage
            if changed:
                fired.append(stage)
                if boundary == 'rollback':
                    raise OSError('Cut after writes, before commit')
        if changed and boundary == 'lost_reply':
            raise OSError('Commit succeeded, reply lost')

    if stage != 'CONSUMED':
        service.factory = SimpleNamespace(unit_of_work=cut)
        with pytest.raises(OSError):
            client.portal.call(service.reserve, aid)
        assert fired == [stage]
        assert runtime[2].opens == 0
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == ('OPEN', 0)
            assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (gid,)).fetchone()[0] == 0
        restarted = build_handoff_runtime_attempts(deps, capacity=observed)
        held = client.portal.call(restarted.reserve, aid)
        assert held.request == attempt.request and held.state == 'RESERVED'
        service = restarted
    else:
        held = client.portal.call(service.reserve, aid)
    claim = service.claim(aid)
    transfer = build_capacity_admission(deps, capacity=observed)
    if stage == 'CONSUMED':
        transfer.factory = SimpleNamespace(unit_of_work=cut)
        with pytest.raises(OSError):
            client.portal.call(transfer.consume, claim.operation_id)
        assert fired == [stage]
        transfer = build_capacity_admission(deps, capacity=observed)
    admitted = client.portal.call(transfer.consume, claim.operation_id)
    assert admitted.state == 'CONSUMED'
    assert admitted.reservation.reservation_id == held.reservation.reservation_id
    assert client.portal.call(transfer.consume, claim.operation_id) == admitted
    assert service.claim(aid).operation_id == claim.operation_id
    wait_receipt(setup, current_turn(setup))
    assert observed.reserves == 1
    assert runtime[2].opens == len(runtime[2].native.sent) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM handoff_runtime_attempts').fetchone()[0] == 1
        assert uow.connection.execute('SELECT count(*) FROM execution_capacity_admissions').fetchone()[0] == 1
        assert uow.connection.execute('SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == ('CLAIMED', 1)
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (gid,)).fetchone()[0] == 1
