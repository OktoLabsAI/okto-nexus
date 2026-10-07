"""Domain recovery must honor the canonical dispatch fence and session owner."""
import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_canonical_consumption import pull


def snapshot(setup):
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        return dict(uow.connection.execute('SELECT * FROM delivery_outbox').fetchone())


def recover(setup, row, action):
    return setup[2].post('/api/v1/harness/outbox', headers=setup[3]['operator'], json=dict(
        action=action, operation_id=row['operation_id'], expected_state=row['status'],
        expected_attempt_id=row['attempt_id'], expected_owner_epoch=row['owner_epoch'],
        idempotency_key='recover-' + action, reason='Review canonical claim recovery',
        acknowledge_duplicate_risk=action != 'cancel_pending'))


def test_live_canonical_session_cannot_release_claim(connected_local, monkeypatch):
    setup, binding, native = connected_local
    enable(setup, binding)
    assert send(setup, monkeypatch)['ok']
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        turn = dict(uow.connection.execute("SELECT operation_id,session_id FROM execution_operations WHERE action='turn.submit'").fetchone())
    wait_receipt(setup, turn)
    inspected = setup[2].post('/api/v1/harness/outbox', headers=setup[3]['operator'],
        json=dict(action='inspect', operation_id=snapshot(setup)['operation_id']))
    assert inspected.status_code == 200, inspected.text
    refs = inspected.json()['data']['items'][0]['canonical_operations']
    assert {r['session_id'] for r in refs} == {turn['session_id']}
    assert {r['action'] for r in refs} == {'runtime.open', 'turn.submit'}
    response = recover(setup, snapshot(setup), 'release_to_inbox')
    assert response.status_code == 409, response.text
    assert 'canonical session' in response.text
    assert pull(setup, monkeypatch) == []
    closed = admit(setup, binding, 'recovery-close', 'runtime.close', session_id=turn['session_id'])
    wait_receipt(setup, closed, stages=('SUCCEEDED',))
    # The close receipt precedes asynchronous domain release. Recover against
    # that final snapshot, rather than racing the background reconciler.
    import time
    deadline = time.monotonic() + 10
    while snapshot(setup)['status'] != 'OUTCOME_UNKNOWN':
        assert time.monotonic() < deadline
        time.sleep(.02)
    row = snapshot(setup)
    response = recover(setup, row, 'release_to_inbox')
    assert response.status_code == 200, response.text
    assert response.json()['data']['duplicate_risk_acknowledged']
    assert len(pull(setup, monkeypatch)) == 1
    assert native.opens == 1 and len(native.native.sent) == 1


def test_cancel_before_canonical_send_keeps_native_unstarted(connected_local, monkeypatch):
    setup, binding, native = connected_local
    enable(setup, binding)
    deps, app, client, *_ = setup
    lock = app.state.embedded_dispatch_owner.pump.send_lock
    client.portal.call(lock.acquire)
    try:
        assert send(setup, monkeypatch)['ok']
        from test_agent_recovery_isolation import eventually
        def reserved():
            with deps.connection_factory.unit_of_work(write=False) as uow:
                return uow.connection.execute("SELECT COUNT(*) FROM execution_dispatch_outbox WHERE dispatch_state='RESERVED'").fetchone()[0] == 1
        eventually(reserved)
        response = recover(setup, snapshot(setup), 'cancel_pending')
        assert response.status_code == 200, response.text
        assert len(pull(setup, monkeypatch)) == 1
    finally:
        client.portal.call(lock.release)
    import time
    deadline = time.monotonic() + 10
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            pending = uow.connection.execute("SELECT COUNT(*) FROM execution_dispatch_outbox WHERE dispatch_state IN ('PENDING','RESERVED','SENDING')").fetchone()[0]
        if not pending:
            break
        assert time.monotonic() < deadline
        time.sleep(.02)
    assert native.opens == 0
    assert snapshot(setup)['status'] == 'CANCELLED'
    # The cancelled reserved attempt must not close the healthy dispatch lane.
    next_open = admit(setup, binding, 'after-reserved-cancellation', 'runtime.start', new_session=True)
    wait_receipt(setup, next_open)
    assert native.opens == 1 and app.state.embedded_dispatch_owner.pump.error is None


def test_pending_domain_projection_cannot_cancel_inflight_canonical_send(connected_local, monkeypatch):
    import asyncio
    import threading
    from test_vertical_inventory import _Native
    setup, binding, native = connected_local
    enable(setup, binding)
    entered, release = threading.Event(), threading.Event()
    original = _Native.send
    async def held(peer, verb, *args, **kwargs):
        result = await original(peer, verb, *args, **kwargs)
        if verb == 'send_turn':
            entered.set()
            while not release.is_set():
                await asyncio.sleep(.01)
        return result
    monkeypatch.setattr(_Native, 'send', held)
    try:
        assert send(setup, monkeypatch)['ok']
        assert entered.wait(10)
        row = snapshot(setup)
        assert row['status'] == 'PENDING'
        response = recover(setup, row, 'cancel_pending')
        assert response.status_code == 409, response.text
        assert 'send fence' in response.text
        assert pull(setup, monkeypatch) == []
    finally:
        release.set()
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        turn = dict(uow.connection.execute("SELECT operation_id,session_id FROM execution_operations WHERE action='turn.submit'").fetchone())
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_operation_reconciliations').fetchone()[0] == 0
    wait_receipt(setup, turn)
    closed = admit(setup, binding, 'inflight-close', 'runtime.close', session_id=turn['session_id'])
    wait_receipt(setup, closed, stages=('SUCCEEDED',))
