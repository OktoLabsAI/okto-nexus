"""Only durable, correlated no-write evidence permits risk-free inbox release."""
import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract
from test_canonical_delivery import connected_local, enable, send
from test_canonical_delivery_retry import wait_delivery
from test_canonical_consumption import pull
from test_canonical_recovery_regressions import body, post
from test_canonical_grant_regressions import mcp_helpers
from test_pr34_remediation import tool


def rejected_before_write(connected, monkeypatch):
    from nexus_connector_core.models import EffectNotSent
    from test_vertical_inventory import _Native
    setup, binding, native = connected
    enable(setup, binding)
    calls = []
    async def refuse(peer, verb, payload, operation_id, **kwargs):
        calls.append(operation_id)
        raise EffectNotSent('Refused before writing bytes', code='CAPACITY_EXCEEDED')
    monkeypatch.setattr(_Native, 'send', refuse)
    sent = send(setup, monkeypatch)
    assert sent['ok'], sent
    row = wait_delivery(setup, lambda item: item['status'] == 'REJECTED')
    assert row['reason'] == 'native_write_not_started' and row['ack_level'] == 'NONE'
    assert len(calls) == row['attempt_count'] == 3 and native.native.sent == []
    return setup, row, native, calls, sent['data']


def request(row):
    return dict(body(row), acknowledge_duplicate_risk=False)


@pytest.mark.parametrize('surface', ['rest', 'mcp'])
def test_proven_not_sent_release_preserves_transport_evidence_and_original_inbox(connected_local, monkeypatch, surface):
    setup, row, native, calls, sent = rejected_before_write(connected_local, monkeypatch)
    client, headers = setup[2:4]
    payload = request(row)
    denied = tool(client, headers['subject']['Authorization'].removeprefix('Bearer '),
                  'harness_list', dict(view='outbox', maintenance=payload))
    assert denied['error']['code'] == 'PERMISSION_DENIED', denied
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        receipts = [tuple(r) for r in uow.connection.execute('SELECT * FROM execution_receipts')]
    if surface == 'rest':
        response = post(setup, payload)
        assert response.status_code == 200, response.text
        result = response.json()['data']
    else:
        response = tool(client, headers['operator']['Authorization'].removeprefix('Bearer '),
                        'harness_list', dict(view='outbox', maintenance=payload))
        assert response['ok'], response
        result = response['data']
    assert result['transport_state'] == 'REJECTED'
    assert result['inbox_released'] and not result['native_replayed']
    assert not result['duplicate_risk_acknowledged'] and not result['endpoint_quarantined']
    repeated = tool(client, headers['operator']['Authorization'].removeprefix('Bearer '),
                    'harness_list', dict(view='outbox', maintenance=payload))
    assert repeated['ok'] and repeated['data'] == result, repeated
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        current = dict(uow.connection.execute('SELECT * FROM delivery_outbox').fetchone())
        assert all(current[k] == row[k] for k in ('status', 'reason', 'ack_level', 'attempt_id', 'attempt_count'))
        assert [tuple(r) for r in uow.connection.execute('SELECT * FROM execution_receipts')] == receipts
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_operation_reconciliations').fetchone()[0] == 1
    assert [item['message_id'] for item in pull(setup, monkeypatch)] == [sent['message_id']]
    assert len(calls) == 3 and native.native.sent == []


@pytest.mark.parametrize('changed', [
    {'reason': 'peer_rejected'}, {'ack_level': 'TRANSPORT_WRITE'},
    {'status': 'OUTCOME_UNKNOWN'}, {'native_turn_id': 'observed-turn'},
    {'native_thread_id': 'observed-thread'}, {'attempt_id': None},
])
def test_release_requires_complete_server_owned_non_delivery_proof(connected_local, monkeypatch, changed):
    setup, row, native, calls, _ = rejected_before_write(connected_local, monkeypatch)
    with setup[0].connection_factory.unit_of_work() as uow:
        key, value = next(iter(changed.items()))
        uow.connection.execute(f'UPDATE delivery_outbox SET {key}=? WHERE operation_id=?', (value, row['operation_id']))
    response = post(setup, request(row | changed))
    assert response.status_code == 409, response.text
    assert pull(setup, monkeypatch) == []
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_operation_reconciliations').fetchone()[0] == 0
    assert len(calls) == 3 and native.native.sent == []


@pytest.mark.parametrize('changed', ['possible_effect', 'retry_safe', 'proof_operation_id'])
def test_display_label_cannot_replace_correlated_core_proof(connected_local, monkeypatch, changed):
    setup, row, native, calls, _ = rejected_before_write(connected_local, monkeypatch)
    with setup[0].connection_factory.unit_of_work() as uow:
        if changed == 'proof_operation_id':
            # An existing different receipt is not proof for the final attempt.
            uow.connection.execute('UPDATE execution_delivery_attempt_history SET proof_operation_id=? '
                'WHERE domain_operation_id=? AND proof_operation_id=?', (calls[0], row['operation_id'], calls[-1]))
        else:
            uow.connection.execute(f'UPDATE execution_receipts SET {changed}=? WHERE operation_id=?',
                                   (int(changed == 'possible_effect'), calls[-1]))
    response = post(setup, request(row))
    assert response.status_code == 409, response.text
    assert pull(setup, monkeypatch) == []
    assert len(calls) == 3 and native.native.sent == []


def test_safe_release_audit_and_inbox_roll_back_together(connected_local, monkeypatch):
    from okto_nexus.errors import ErrorCode, OktoNexusError
    setup, row, _, _, _ = rejected_before_write(connected_local, monkeypatch)
    original = setup[0].repos.deliveries.release_runtime_reservation
    def cut(*args, **kwargs):
        original(*args, **kwargs)
        raise OktoNexusError(ErrorCode.CONFLICT, 'Isolated commit cut', {})
    monkeypatch.setattr(setup[0].repos.deliveries, 'release_runtime_reservation', cut)
    response = post(setup, request(row))
    assert response.status_code == 409, response.text
    assert pull(setup, monkeypatch) == []
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        current = dict(uow.connection.execute('SELECT * FROM delivery_outbox').fetchone())
        assert current['reconciliation_id'] is None and current['status'] == 'REJECTED'
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_operation_reconciliations').fetchone()[0] == 0
