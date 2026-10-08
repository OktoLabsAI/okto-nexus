"""A durable no-write receipt permits bounded recovery of one logical delivery."""
import time

import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_canonical_identity_lifecycle import second_binding


def wait_delivery(setup, predicate):
    until = time.monotonic() + 15
    while True:
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            row = dict(uow.connection.execute('SELECT * FROM delivery_outbox ORDER BY created_at LIMIT 1').fetchone())
        if predicate(row):
            return row
        assert time.monotonic() < until, (row['status'], row['reason'], row['attempt_count'])
        time.sleep(.02)


@pytest.mark.parametrize('fallback', [False, True])
def test_proven_unsent_delivery_recovers_without_another_inbox_claim(connected_local, monkeypatch, fallback):
    from nexus_connector_core.models import EffectNotSent
    from test_vertical_inventory import _Native
    setup, first, native = connected_local
    deps = setup[0]
    second = second_binding(setup, monkeypatch) if fallback else first
    for binding in (first, second):
        enable(setup, binding)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET selection_group='approved-equivalents',priority=1")
        uow.connection.execute('UPDATE agent_endpoints SET priority=10 WHERE endpoint_id=?', (first['endpoint_id'],))
    calls = []
    original = _Native.send
    async def refuse_once(peer, verb, payload, operation_id, **kwargs):
        calls.append(operation_id)
        if len(calls) == 1:
            raise EffectNotSent('Native write refused before any bytes', code='CAPACITY_EXCEEDED')
        return await original(peer, verb, payload, operation_id, **kwargs)
    monkeypatch.setattr(_Native, 'send', refuse_once)
    created = send(setup, monkeypatch)
    assert created['ok'], created
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = dict(uow.connection.execute('SELECT * FROM delivery_outbox').fetchone())
        first_turn = dict(uow.connection.execute("SELECT operation_id FROM execution_operations WHERE action='turn.submit'").fetchone())
    wait_receipt(setup, first_turn, stages=('FAILED',))
    # No external wake or scan: receipt publication and the persisted deadline
    # must be sufficient to recover the delivery automatically.
    after = wait_delivery(setup, lambda row: row['status'] == 'ACCEPTED')
    assert after['endpoint_id'] == second['endpoint_id']
    assert after['attempt_count'] == 2
    for field in ('operation_id', 'message_id', 'delivery_id', 'request_hash', 'envelope'):
        assert after[field] == before[field]
    assert len(calls) == 2 and len(set(calls)) == 2
    assert len(native.native.sent) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM message_deliveries').fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1
        receipt = uow.connection.execute('SELECT stage,possible_effect,retry_safe FROM execution_receipts WHERE operation_id=? ORDER BY receipt_revision DESC LIMIT 1', (first_turn['operation_id'],)).fetchone()
        assert tuple(receipt) == ('FAILED', 0, 1)
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_delivery_attempt_history').fetchone()[0] == 2
        assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('failure', ['after_write', 'error_text', 'permanent'])
def test_uncertain_or_permanent_failure_never_retries(connected_local, monkeypatch, failure):
    from nexus_connector_core.models import EffectRejected
    from test_vertical_inventory import _Native
    setup, binding, native = connected_local
    enable(setup, binding)
    calls = []
    original = _Native.send
    async def fail(peer, verb, payload, operation_id, **kwargs):
        calls.append(operation_id)
        if failure == 'after_write':
            await original(peer, verb, payload, operation_id, **kwargs)
        if failure == 'permanent':
            raise EffectRejected('Provider refused this operation')
        raise OSError('CAPACITY_EXCEEDED: no write; retry_safe=true')
    monkeypatch.setattr(_Native, 'send', fail)
    assert send(setup, monkeypatch)['ok']
    row = wait_delivery(setup, lambda row: row['status'] in ('FAILED_FINAL', 'OUTCOME_UNKNOWN'))
    for _ in range(3):
        setup[0].runtime_dispatcher.scan_once()
    assert len(calls) == 1
    assert row['next_attempt_at'] is None
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_delivery_attempt_history').fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 1


def test_retries_are_bounded_and_retain_durable_proof(connected_local, monkeypatch):
    from nexus_connector_core.models import EffectNotSent
    from test_vertical_inventory import _Native
    setup, binding, native = connected_local
    enable(setup, binding)
    calls = []
    async def refuse(peer, verb, payload, operation_id, **kwargs):
        calls.append(operation_id)
        raise EffectNotSent('No native write', code='CAPACITY_EXCEEDED')
    monkeypatch.setattr(_Native, 'send', refuse)
    assert send(setup, monkeypatch)['ok']
    row = wait_delivery(setup, lambda row: row['status'] == 'REJECTED')
    assert row['attempt_count'] == 3 and row['next_attempt_at'] is None
    assert row['ack_level'] == 'NONE' and row['reason'] == 'native_write_not_started'
    for _ in range(3):
        setup[0].runtime_dispatcher.scan_once()
    assert len(calls) == len(set(calls)) == 3
    assert native.native.sent == []
    _, _, client, headers, *_ = setup
    inspected = client.get('/api/v1/harness/outbox', headers=headers['operator'], params={'operation_id': row['operation_id']})
    assert inspected.status_code == 200, inspected.text
    history = inspected.json()['data']['items'][0]['canonical_attempt_history']
    assert {entry['attempt_number'] for entry in history} == {1, 2, 3}
    assert {entry['proof_operation_id'] for entry in history} == set(calls)
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM message_deliveries').fetchone()[0] == 1
        assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []
    from test_canonical_consumption import pull
    released = client.post('/api/v1/harness/outbox', headers=headers['operator'], json=dict(
        action='release_to_inbox', operation_id=row['operation_id'], expected_state=row['status'],
        expected_attempt_id=row['attempt_id'], expected_owner_epoch=row['owner_epoch'],
        idempotency_key='release-exhausted-retry', reason='All attempts proved unsent',
        acknowledge_duplicate_risk=False))
    assert released.status_code == 200, released.text
    assert released.json()['data']['inbox_released']
    assert not released.json()['data']['duplicate_risk_acknowledged']
    assert len(pull(setup, monkeypatch)) == 1
    assert len(calls) == 3 and native.native.sent == []


@pytest.mark.parametrize('change', ['actor', 'source', 'target', 'cancel'])
def test_retry_revalidates_authority_and_accepts_cancellation(connected_local, monkeypatch, change):
    from nexus_connector_core.models import EffectNotSent
    from test_vertical_inventory import _Native
    from okto_nexus.domain.base import iso_plus
    setup, first, native = connected_local
    second = second_binding(setup, monkeypatch)
    deps, _, client, headers, *_ = setup
    for binding in (first, second):
        enable(setup, binding)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET selection_group='approved-equivalents',priority=1")
        uow.connection.execute('UPDATE agent_endpoints SET priority=10 WHERE endpoint_id=?', (first['endpoint_id'],))
    frozen = deps.clock.now_iso()
    monkeypatch.setattr(deps.clock, 'now_iso', lambda: frozen)
    calls = []
    async def refuse(peer, verb, payload, operation_id, **kwargs):
        calls.append(operation_id)
        raise EffectNotSent('No native write', code='CAPACITY_EXCEEDED')
    monkeypatch.setattr(_Native, 'send', refuse)
    assert send(setup, monkeypatch)['ok']
    pending = wait_delivery(setup, lambda row: row['status'] == 'RETRY_WAIT' and row['reason'] == 'native_write_not_started')
    assert pending['next_binding'] is not None
    if change == 'cancel':
        request = dict(action='cancel_pending', operation_id=pending['operation_id'], expected_state='RETRY_WAIT',
            expected_attempt_id=pending['attempt_id'], expected_owner_epoch=pending['owner_epoch'],
            idempotency_key='cancel-safe-retry', reason='Operator cancelled before retry')
        cancelled = client.post('/api/v1/harness/outbox', headers=headers['operator'], json=request)
        assert cancelled.status_code == 200, cancelled.text
    else:
        with deps.connection_factory.unit_of_work() as uow:
            if change == 'actor':
                uow.connection.execute("UPDATE agents SET is_active=0 WHERE agent_id='operator'")
            else:
                target = first if change == 'source' else second
                uow.connection.execute('UPDATE agent_endpoints SET enabled=0,revision=revision+1 WHERE endpoint_id=?', (target['endpoint_id'],))
    monkeypatch.setattr(deps.clock, 'now_iso', lambda: iso_plus(pending['next_attempt_at'], .1))
    deps.runtime_dispatcher.wake()
    final = wait_delivery(setup, lambda row: row['status'] in ('CANCELLED', 'REJECTED'))
    assert final['status'] == ('CANCELLED' if change == 'cancel' else 'REJECTED')
    assert len(calls) == 1 and native.native.sent == []


def held_retry(connected, monkeypatch):
    from nexus_connector_core.models import EffectNotSent
    from test_vertical_inventory import _Native
    setup, binding, native = connected
    frozen = setup[0].clock.now_iso()
    monkeypatch.setattr(setup[0].clock, 'now_iso', lambda: frozen)
    calls = []
    async def refuse(peer, verb, payload, operation_id, **kwargs):
        calls.append(operation_id)
        raise EffectNotSent('No bytes written', code='CAPACITY_EXCEEDED')
    monkeypatch.setattr(_Native, 'send', refuse)
    assert send(setup, monkeypatch)['ok']
    row = wait_delivery(setup, lambda row: row['status'] == 'RETRY_WAIT' and row['reason'] == 'native_write_not_started')
    return setup, row, native, calls


def test_retry_deadline_preserves_lane_order_for_messages_and_commands(connected_local, monkeypatch):
    from test_embedded_dispatch import admit
    setup, first, native, calls = held_retry(connected_local, monkeypatch)
    assert send(setup, monkeypatch)['ok']
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        session = uow.connection.execute('SELECT session_id FROM execution_sessions').fetchone()[0]
    command = admit(setup, connected_local[1], 'later-than-retry', 'turn.submit', session_id=session, text='Later direct turn')
    for _ in range(5):
        setup[0].runtime_dispatcher.scan_once()
    current = wait_delivery(setup, lambda row: row['status'] == 'RETRY_WAIT')
    assert current['attempt_count'] == 1 and current['next_attempt_at'] == first['next_attempt_at']
    assert len(calls) == 1 and native.native.sent == [], (calls, command['operation_id'])
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_receipts WHERE operation_id=?', (command['operation_id'],)).fetchone()[0] == 0


@pytest.mark.parametrize('field,value', [('ack_level','TRANSPORT_WRITE'), ('retry_basis',None), ('reason','unknown')])
def test_retry_label_cannot_replace_no_effect_proof_for_cancel(connected_local, monkeypatch, field, value):
    from test_canonical_recovery import recover
    setup, row, native, calls = held_retry(connected_local, monkeypatch)
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute(f'UPDATE delivery_outbox SET {field}=? WHERE operation_id=?', (value, row['operation_id']))
    denied = recover(setup, row, 'cancel_pending')
    assert denied.status_code == 409, denied.text
    assert len(calls) == 1 and native.native.sent == []


def test_retry_wait_does_not_block_session_close(connected_local, monkeypatch):
    from test_embedded_dispatch import admit
    setup, _, native, calls = held_retry(connected_local, monkeypatch)
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        session = uow.connection.execute('SELECT session_id FROM execution_sessions').fetchone()[0]
    closed = admit(setup, connected_local[1], 'close-during-retry', 'runtime.close', session_id=session)
    wait_receipt(setup, closed, stages=('SUCCEEDED',))
    assert native.native.stopped and len(calls) == 1


def test_retry_wait_does_not_block_an_independent_session(connected_local, monkeypatch):
    from test_embedded_dispatch import admit
    setup, row, native, calls = held_retry(connected_local, monkeypatch)
    opened = admit(setup, connected_local[1], 'independent-of-retry', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    other = admit(setup, connected_local[1], 'independent-turn', 'turn.submit',
        session_id=opened['scope']['session_id'], text='A separate session can proceed')
    wait_receipt(setup, other, stages=('FAILED',))
    assert len(calls) == 2 and calls[-1] == other['operation_id'] and native.opens == 2
    current = wait_delivery(setup, lambda current: current['status'] == 'RETRY_WAIT')
    assert current['attempt_count'] == 1 and current['next_attempt_at'] == row['next_attempt_at']


def test_new_dispatch_owner_preserves_retry_deadline(connected_local, monkeypatch):
    from okto_nexus.application.runtime_dispatcher import RuntimeDispatcher
    setup, row, native, calls = held_retry(connected_local, monkeypatch)
    deps = setup[0]
    old = deps.runtime_dispatcher
    old.quiesce()
    old.close()
    fresh = RuntimeDispatcher(connection_factory=deps.connection_factory, repo=old.repo,
        clock=deps.clock, validate=old.validate, dispatch=old.dispatch)
    fresh.admit_canonical, fresh.select_fallback = old.admit_canonical, old.select_fallback
    deps.runtime_dispatcher = fresh
    assert fresh.start()
    try:
        fresh.scan_once()
        current = wait_delivery(setup, lambda current: current['status'] == 'RETRY_WAIT')
        for field in ('next_attempt_at', 'attempt_count', 'attempt_id', 'operation_id'):
            assert current[field] == row[field]
        assert len(calls) == 1 and native.native.sent == []
    finally:
        fresh.close()


def test_uncommitted_no_effect_proof_cannot_authorize_retry(connected_local, monkeypatch):
    import threading
    from nexus_connector_core.models import EffectNotSent
    from test_vertical_inventory import _Native
    from okto_nexus.application import execution_delivery_retry
    setup, binding, native = connected_local
    calls, failed = [], threading.Event()
    allow = threading.Event()
    original = execution_delivery_retry.mark_retry_wait
    async def refuse(peer, verb, payload, operation_id, **kwargs):
        calls.append(operation_id)
        raise EffectNotSent('No native write', code='CAPACITY_EXCEEDED')
    def cut(conn, operation_id):
        original(conn, operation_id)
        if not allow.is_set():
            failed.set()
            raise OSError('Receipt transaction interrupted before commit')
    monkeypatch.setattr(_Native, 'send', refuse)
    monkeypatch.setattr(execution_delivery_retry, 'mark_retry_wait', cut)
    try:
        assert send(setup, monkeypatch)['ok']
        assert failed.wait(10)
        for _ in range(5):
            setup[0].runtime_dispatcher.scan_once()
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            row = dict(uow.connection.execute('SELECT * FROM delivery_outbox').fetchone())
            assert row['next_attempt_at'] is None and row['attempt_count'] == 1
            assert uow.connection.execute('SELECT COUNT(*) FROM execution_delivery_attempt_history').fetchone()[0] == 0
            assert uow.connection.execute("SELECT COUNT(*) FROM execution_receipts WHERE stage='FAILED'").fetchone()[0] == 0
        assert len(calls) == 1 and native.native.sent == []
    finally:
        allow.set()
    final = wait_delivery(setup, lambda current: current['status'] == 'REJECTED')
    assert final['attempt_count'] == len(calls) == 3
