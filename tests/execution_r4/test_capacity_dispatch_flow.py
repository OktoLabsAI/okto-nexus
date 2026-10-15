"""Authenticated waiting is transport accounting, never an execution receipt."""
from dataclasses import replace
import json

import pytest
from nexus_connector_core import CAPACITY_CONTRACT_REVISION

from okto_nexus.adapters.outbound.sqlite.execution_capacity_flow import record_capacity_dispatch_state
from okto_nexus.application.execution_dispatch import begin_execution_send
from okto_nexus.errors import OktoNexusError
from test_dispatch_capacity import backlog, reserve
from test_dispatch_pump import owner


def begin(state):
    deps, app, access, _, _, channel, *_ = state
    reservation = reserve(state)
    authorized = begin_execution_send(deps.connection_factory, reservation=reservation, remote_ready=True,
        access=access, fresh_publications=app.state.inventory_fresh_publications, channel=channel)
    source = authorized.frame
    return {key: source[key] for key in ('server_id', 'executor_id', 'connection_id', 'connection_generation',
        'binding_id', 'agent_id', 'session_id', 'operation_id', 'intent_hash', 'action')} | dict(
            contract_revision=CAPACITY_CONTRACT_REVISION, type='capacity.dispatch_state', state='WAITING', sequence=1)


def record(state, frame, channel=None):
    return record_capacity_dispatch_state(state[0].connection_factory, channel=channel or state[5], frame=frame)


def test_waiting_donates_only_worker_credit_and_preserves_wire_bytes(owner):
    frame = begin(owner)
    assert record(owner, frame)
    assert record(owner, frame) is False
    backlog(owner, 'turn.submit', 1, payload='"healthy"')
    with owner[0].connection_factory.unit_of_work() as uow:
        owner[0].repos.agents.upsert(uow, agent_id='healthy', role='reviewer')
        uow.connection.execute("UPDATE execution_operations SET subject_agent_id='healthy' WHERE action='turn.submit'")
        cost = uow.connection.execute('SELECT reserved_bytes FROM execution_dispatch_outbox WHERE operation_id=?',
                                      (frame['operation_id'],)).fetchone()[0]
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_receipts').fetchone()[0] == 0
    assert reserve(owner, regular_items=1, regular_bytes=cost) is None
    assert record(owner, dict(frame, state='RUNNING', sequence=2))
    assert record(owner, frame) is False  # Reordered old waiting must not free a worker.
    assert reserve(owner, regular_items=1) is None
    assert record(owner, dict(frame, sequence=3))
    assert reserve(owner, regular_items=1).operation_id == 'backlog-turn.submit-0000'
    with owner[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT dispatch_state,attempt_no,reserved_bytes FROM execution_dispatch_outbox '
            'WHERE operation_id=?', (frame['operation_id'],)).fetchone()[:] == ('SENDING', 1, cost)
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_receipts').fetchone()[0] == 0


@pytest.mark.parametrize('field,value', [('agent_id', 'foreign'), ('binding_id', 'foreign'),
    ('session_id', 'foreign'), ('operation_id', 'foreign'), ('intent_hash', 'sha256:' + 'f' * 64),
    ('action', 'turn.submit'), ('connection_id', 'foreign'), ('connection_generation', 999),
    ('state', 'RUNNING'), ('sequence', 2)])
def test_wait_flow_refuses_mismatched_operation_or_initial_state(owner, field, value):
    frame = begin(owner)
    with pytest.raises(OktoNexusError):
        record(owner, dict(frame, **{field: value}))
    assert record(owner, frame)


def test_same_sequence_cannot_change_state_and_replaced_owner_cannot_publish(owner):
    frame = begin(owner)
    assert record(owner, frame)
    with pytest.raises(OktoNexusError):
        record(owner, dict(frame, state='RUNNING'))
    replacement = replace(owner[5], connection_id='new-owner', connection_generation=owner[5].connection_generation + 1)
    with owner[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE execution_executors SET generation=?,owner_instance_id=? WHERE executor_id=?',
                               (replacement.connection_generation, replacement.connection_id, replacement.executor_id))
    with pytest.raises(OktoNexusError):
        record(owner, dict(frame, state='RUNNING', sequence=2))
    # New channel authority does not inherit the old transport reservation.
    with pytest.raises(OktoNexusError):
        record(owner, dict(frame, connection_id=replacement.connection_id,
                           connection_generation=replacement.connection_generation), replacement)


@pytest.mark.parametrize('waiting_count,available', [(24, True), (31, True), (32, False)])
def test_waiters_keep_shared_item_bound_without_prematurely_blocking_progress(owner, waiting_count, available):
    frame = begin(owner)
    assert record(owner, frame)
    backlog(owner, 'turn.submit', waiting_count, payload='"small"')
    factory, channel = owner[0].connection_factory, owner[5]
    with factory.unit_of_work() as uow:
        for index in range(waiting_count):
            op = f'backlog-turn.submit-{index:04d}'
            agent = f'agent-{index}'
            owner[0].repos.agents.upsert(uow, agent_id=agent, role='reviewer')
            uow.connection.execute('UPDATE execution_operations SET subject_agent_id=? WHERE operation_id=?', (agent, op))
            if index == waiting_count - 1:
                continue  # The last row is new independent work.
            uow.connection.execute("UPDATE execution_dispatch_outbox SET dispatch_state='SENDING',reservation_class='regular',"
                "reserved_bytes=7,reservation_owner=?,reservation_generation=? WHERE operation_id=?",
                (channel.connection_id, channel.connection_generation, op))
            value = dict(frame, operation_id=op, agent_id=agent, action='turn.submit')
            uow.connection.execute('INSERT INTO execution_capacity_waits VALUES(?,?,?,?,?,?,?,?)',
                (channel.server_id, channel.executor_id, op, channel.connection_id, channel.connection_generation,
                 1, 'WAITING', json.dumps(value)))
    result = reserve(owner, regular_items=1)
    assert (result is not None) is available
    if available:
        assert result.operation_id == f'backlog-turn.submit-{waiting_count - 1:04d}'
