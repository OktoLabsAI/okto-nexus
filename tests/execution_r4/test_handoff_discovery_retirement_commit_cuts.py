"""Discovery and legacy retirement recover their own durable page boundaries."""
from dataclasses import replace

import pytest

from okto_nexus.application.handoff_notice_maintenance import HandoffNoticeMaintenance
from okto_nexus.bootstrap.handoff_runtime_scheduler import build_handoff_runtime_candidates
from okto_nexus.bootstrap.handoff_runtime_attempts import build_handoff_runtime_attempts
from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, assert_unclaimed
from test_canonical_result_publication import current_turn
from test_handoff_automation_principal import prepare
from test_handoff_runtime_candidates import enable_capacity, lease
from test_handoff_notice_retirement import backlog, retirement
from test_handoff_recovery_commit_cuts import cut_transition
from test_one_shot_runtime import query


@pytest.mark.parametrize('boundary', ['rollback', 'lost_reply'])
def test_discovery_commit_cut_reuses_committed_attempt_before_any_host_call(runtime, monkeypatch, boundary):
    setup = runtime[0]
    deps, _, client, *_ = setup
    _, hid, gid = prepare(runtime)
    enable_capacity(runtime)
    current = lease(runtime, hid)
    discovery = build_handoff_runtime_candidates(deps)
    created = []
    original = discovery.attempts.create
    def observe_create(*args, **kwargs):
        result = original(*args, **kwargs)
        created.append(result)
        return result
    monkeypatch.setattr(discovery.attempts, 'create', observe_create)
    fired = cut_transition(discovery,
        lambda uow: uow.connection.execute('SELECT count(*) FROM handoff_runtime_attempts').fetchone()[0],
        1, boundary)
    with pytest.raises(OSError):
        discovery.prepare_page(current, limit=4)
    assert fired == [1] and len(created) == 1
    assert query(setup, 'SELECT count(*) FROM handoff_runtime_attempts')[0][0] == int(boundary == 'lost_reply')
    assert_unclaimed(runtime, hid, gid)
    assert runtime[2].opens == 0
    restarted = build_handoff_runtime_candidates(deps)
    page = restarted.prepare_page(current, limit=4)
    assert len(page.attempt_ids) == 1
    if boundary == 'lost_reply':
        assert page.attempt_ids == (created[0].request.attempt_id,)
    # A rolled-back UUID was never durable or sent to a host. Only the
    # committed attempt may proceed, and subsequent pages reuse that identity.
    assert restarted.prepare_page(current, limit=4).attempt_ids == page.attempt_ids
    assert restarted.prepare_page(replace(current, candidate_cursor=page.cursor), limit=4).attempt_ids == page.attempt_ids
    assert query(setup, 'SELECT count(*) FROM handoff_runtime_attempts')[0][0] == 1
    attempts = build_handoff_runtime_attempts(deps)
    held = client.portal.call(attempts.reserve, page.attempt_ids[0])
    assert held.state == 'RESERVED'
    claim = attempts.claim(page.attempt_ids[0])
    transfer = build_capacity_admission(deps)
    assert client.portal.call(transfer.consume, claim.operation_id).state == 'CONSUMED'
    wait_receipt(setup, current_turn(setup))
    assert runtime[2].opens == len(runtime[2].native.sent) == 1
    assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == ('CLAIMED', 1)


@pytest.mark.parametrize('boundary', ['rollback', 'lost_reply'])
def test_retirement_commit_cut_preserves_cursor_inbox_and_uncertain_history(backlog, boundary):
    def snapshot():
        with backlog.unit_of_work(write=False) as uow:
            return [tuple(row) for row in uow.connection.execute(
                "SELECT * FROM delivery_outbox WHERE operation_id<>'b-safe' ORDER BY operation_id")]
    before = snapshot()
    maintenance = HandoffNoticeMaintenance(factory=backlog, notices=retirement(), page_size=2, now=lambda: 10)
    fired = cut_transition(maintenance,
        lambda uow: uow.connection.execute('SELECT count(*) FROM runtime_handoff_notice_retirements').fetchone()[0],
        1, boundary)
    with pytest.raises(OSError):
        maintenance._page()
    assert fired == [1]
    with backlog.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT notice_cursor FROM handoff_runtime_schedule_scan').fetchone()[0] == ('' if boundary == 'rollback' else 'b-safe')
        assert uow.connection.execute('SELECT count(*) FROM runtime_handoff_notice_retirements').fetchone()[0] == int(boundary == 'lost_reply')
        assert uow.connection.execute("SELECT status FROM delivery_outbox WHERE operation_id='b-safe'").fetchone()[0] == ('PENDING' if boundary == 'rollback' else 'CANCELLED')
    resumed = HandoffNoticeMaintenance(factory=backlog, notices=retirement(), page_size=2, now=lambda: 11)
    assert resumed._page() == int(boundary == 'rollback')
    for _ in range(4):
        assert resumed._page() == 0
    assert snapshot() == before
    with backlog.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM runtime_handoff_notice_retirements').fetchone()[0] == 1
        assert uow.connection.execute('SELECT handoff_id FROM handoff_runtime_schedule').fetchall()[0][0] == 'b-safe'
        assert uow.connection.execute("SELECT status,consumer_kind,read_at FROM message_deliveries WHERE delivery_id='b-safe'").fetchone()[:] == ('unread', None, None)
        assert not uow.connection.execute('SELECT * FROM execution_operations').fetchall()
        assert not uow.connection.execute('PRAGMA foreign_key_check').fetchall()
