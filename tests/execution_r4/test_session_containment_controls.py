"""Pending session containment must retain authenticated stop controls."""
from test_local_realization import local_setup
from test_embedded_dispatch import connected_local, wait_receipt
from test_operator_runtime import resolve, submit


def test_pending_obligation_does_not_block_operator_interrupt_and_close(connected_local):
    setup, binding, native = connected_local
    response = resolve(setup, binding, new_session=True)
    assert response.status_code == 200, response.text
    opened = response.json()
    assert submit(setup, opened).status_code == 202
    wait_receipt(setup, opened)
    # Exercise the shared dispatch guard with a durable obligation; authenticated
    # remote creation of this record is covered by test_session_containment_obligation.
    scope = opened['scope']
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute('INSERT INTO execution_session_containment(server_id,executor_id,session_id,'
            'owner_generation,opening_operation_id,opening_intent_hash,request_json,recorded_at) '
            "VALUES (?,?,?,?,?,?,'{}',?)", (scope['server_id'], scope['executor_id'], scope['session_id'],
                scope['session_owner_generation'], opened['operation_id'], opened['intent_hash'],
                setup[0].clock.now_iso()))
    for action, options in [('turn.interrupt', {'target': {'kind': 'current_run', 'expected_turn_id': None}}),
                            ('runtime.close', {})]:
        response = resolve(setup, binding, intent_id='contain-' + action, intent=action,
                           session_id=opened['session_id'], **options)
        assert response.status_code == 200, response.text
        operation = response.json()
        accepted = submit(setup, operation)
        assert accepted.status_code == 202, accepted.text
        wait_receipt(setup, operation, ('SUCCEEDED',) if action == 'runtime.close' else ('SUBMITTED', 'SUCCEEDED'))
        if action == 'turn.interrupt':
            assert ('interrupt', operation['operation_id']) in native.native.sent
    assert native.opens == 1 and native.native.stopped
