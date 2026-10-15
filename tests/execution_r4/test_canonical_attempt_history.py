"""Logical delivery observations remain immutable across canonical execution."""
import sqlite3

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_canonical_result_publication import current_turn
from test_canonical_delivery_retry import wait_delivery


def test_attempt_observations_are_atomic_immutable_and_ignore_heartbeats(connected_local, monkeypatch):
    setup, binding, native = connected_local
    enable(setup, binding)
    created = send(setup, monkeypatch)
    assert created['ok'], created
    operation = created['data']['runtime_operations'][0]
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    wait_delivery(setup, lambda row: row['status'] == 'ACCEPTED')
    deps = setup[0]
    cf = deps.connection_factory
    with cf.unit_of_work(write=False) as uow:
        before = [dict(r) for r in uow.connection.execute(
            'SELECT * FROM runtime_delivery_attempt_events WHERE operation_id=? ORDER BY sequence', (operation,))]
        assert {row['attempt_id'] for row in before} == {turn['operation_id']}
        assert {'PENDING', 'ACCEPTED'} <= {row['state'] for row in before}
    with cf.unit_of_work() as uow:
        uow.connection.execute('UPDATE delivery_outbox SET updated_at=? WHERE operation_id=?',
                               (deps.clock.now_iso(), operation))
    with pytest.raises(RuntimeError, match='commit cut'):
        with cf.unit_of_work() as uow:
            uow.connection.execute("UPDATE delivery_outbox SET status='OUTCOME_UNKNOWN' WHERE operation_id=?", (operation,))
            raise RuntimeError('commit cut')
    for statement in ("UPDATE runtime_delivery_attempt_events SET reason='rewrite'", 'DELETE FROM runtime_delivery_attempt_events'):
        with pytest.raises(sqlite3.IntegrityError, match='runtime_attempt_history_is_immutable'):
            with cf.unit_of_work() as uow:
                uow.connection.execute(statement + ' WHERE operation_id=?', (operation,))
    with cf.unit_of_work(write=False) as uow:
        assert [dict(r) for r in uow.connection.execute(
            'SELECT * FROM runtime_delivery_attempt_events WHERE operation_id=? ORDER BY sequence', (operation,))] == before
        assert uow.connection.execute('SELECT status FROM delivery_outbox WHERE operation_id=?', (operation,)).fetchone()[0] == 'ACCEPTED'
    assert native.opens == 1 and len(native.native.sent) == 1
    wait_receipt(setup, admit(setup, binding, 'history-close', 'runtime.close', session_id=turn['session_id']), stages=('SUCCEEDED',))
