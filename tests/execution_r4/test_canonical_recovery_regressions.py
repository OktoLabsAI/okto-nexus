"""Manual last-resort recovery preserves canonical transport evidence."""
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_canonical_consumption import pull
from test_canonical_recovery import snapshot, recover
from test_canonical_grant_regressions import mcp_helpers
from test_pr34_remediation import tool


def uncertain(connected, monkeypatch):
    setup, binding, native = connected
    enable(setup, binding)
    sent = send(setup, monkeypatch)
    assert sent['ok'], sent
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        turn = dict(uow.connection.execute("SELECT operation_id,session_id FROM execution_operations WHERE action='turn.submit'").fetchone())
    wait_receipt(setup, turn)
    closed = admit(setup, binding, 'uncertain-close', 'runtime.close', session_id=turn['session_id'])
    wait_receipt(setup, closed, stages=('SUCCEEDED',))
    deadline = time.monotonic() + 10
    while snapshot(setup)['status'] != 'OUTCOME_UNKNOWN':
        assert time.monotonic() < deadline
        time.sleep(.02)
    return setup, turn, snapshot(setup), native


def body(row, **changes):
    return dict(action='release_to_inbox', operation_id=row['operation_id'], expected_state=row['status'],
        expected_attempt_id=row['attempt_id'], expected_owner_epoch=row['owner_epoch'],
        idempotency_key='manual-reviewed-recovery', reason='Operator reviewed isolated uncertain fixture',
        acknowledge_duplicate_risk=True, **changes)


def post(setup, payload, actor='operator'):
    return setup[2].post('/api/v1/harness/outbox', headers=setup[3][actor], json=payload)


def test_concurrent_recovery_and_cross_transport_replay_preserve_evidence(connected_local, monkeypatch):
    setup, turn, row, native = uncertain(connected_local, monkeypatch)
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        receipts = [tuple(r) for r in uow.connection.execute('SELECT * FROM execution_receipts')]
    assert pull(setup, monkeypatch) == []
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: post(setup, body(row)), range(2)))
    assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
    assert results[0].json() == results[1].json()
    outcome = results[0].json()['data']
    assert not outcome['native_replayed'] and outcome['duplicate_risk_acknowledged']
    setup[2].headers['host'] = '127.0.0.1:8000'
    replay = tool(setup[2], setup[3]['operator']['Authorization'].removeprefix('Bearer '),
                  'harness_list', dict(view='outbox', maintenance=body(row)))
    assert replay['ok'] and replay['data'] == outcome, replay
    changed = dict(body(row), reason='A conflicting decision')
    assert post(setup, changed).status_code == 409
    assert len(pull(setup, monkeypatch)) == 1
    assert native.opens == 1 and len(native.native.sent) == 1
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert [tuple(r) for r in uow.connection.execute('SELECT * FROM execution_receipts')] == receipts
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_operation_reconciliations').fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1


@pytest.mark.parametrize('change', [dict(acknowledge_duplicate_risk=False), dict(expected_attempt_id='stale'),
    dict(expected_owner_epoch=9000), dict(expected_state='SENDING'), dict(action='cancel_pending', acknowledge_duplicate_risk=False)])
def test_uncertain_recovery_requires_risk_and_current_snapshot(connected_local, monkeypatch, change):
    setup, _, row, native = uncertain(connected_local, monkeypatch)
    response = post(setup, dict(body(row), **change))
    assert response.status_code == 409, response.text
    assert pull(setup, monkeypatch) == []
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_operation_reconciliations').fetchone()[0] == 0
    assert native.opens == 1 and len(native.native.sent) == 1


def test_recovery_requires_operator_with_new_admission_disabled(connected_local, monkeypatch):
    setup, _, row, native = uncertain(connected_local, monkeypatch)
    payload = body(row)
    assert post(setup, payload, actor='subject').status_code == 403
    assert setup[2].get('/api/v1/harness/outbox', headers=setup[3]['subject']).status_code == 403
    setup[2].headers['host'] = '127.0.0.1:8000'
    denied = tool(setup[2], setup[3]['subject']['Authorization'].removeprefix('Bearer '),
                  'harness_list', dict(view='outbox', maintenance=payload))
    assert not denied['ok'] and denied['error']['code'] == 'PERMISSION_DENIED', denied
    setup[0].config.feature_harness_integrations = False
    response = post(setup, payload)
    assert response.status_code == 200, response.text
    inspected = setup[2].get('/api/v1/harness/outbox', headers=setup[3]['operator'], params=dict(operation_id=row['operation_id']))
    assert inspected.status_code == 200, inspected.text
    item = inspected.json()['data']['items'][0]
    assert item['state'] == 'OUTCOME_UNKNOWN'
    assert item['reconciliation']['action'] == 'release_to_inbox'
    assert not any(k in item for k in ('envelope', 'credential_binding', 'context', 'payload'))
    assert len(native.native.sent) == 1


def test_recovery_rolls_back_audit_and_inbox_on_release_failure(connected_local, monkeypatch):
    setup, _, row, _ = uncertain(connected_local, monkeypatch)
    original = setup[0].repos.deliveries.release_runtime_reservation
    def cut(*args, **kwargs):
        original(*args, **kwargs)
        from okto_nexus.errors import OktoNexusError, ErrorCode
        raise OktoNexusError(ErrorCode.CONFLICT, 'Fixture release cut', {})
    monkeypatch.setattr(setup[0].repos.deliveries, 'release_runtime_reservation', cut)
    response = post(setup, body(row))
    assert response.status_code == 409, response.text
    assert snapshot(setup)['reconciliation_id'] is None
    assert pull(setup, monkeypatch) == []
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_operation_reconciliations').fetchone()[0] == 0
