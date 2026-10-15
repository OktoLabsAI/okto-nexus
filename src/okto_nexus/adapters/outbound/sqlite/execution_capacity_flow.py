"""Persist authenticated transport flow control without changing work state."""
import json

from nexus_connector_core import decode_capacity_frame, encode_capacity_frame

from ....errors import ErrorCode, OktoNexusError
from .execution_leases import SqliteExecutionLeaseRepository


def record_capacity_dispatch_state(factory, *, channel, frame):
    frame = decode_capacity_frame(encode_capacity_frame(frame))
    def conflict():
        raise OktoNexusError(ErrorCode.CONFLICT, 'The capacity dispatch observation is stale or inconsistent.', {})
    if frame['type'] != 'capacity.dispatch_state' or any(frame[k] != getattr(channel, k) for k in (
            'server_id', 'executor_id', 'connection_id', 'connection_generation')):
        conflict()
    key = (frame['server_id'], frame['executor_id'], frame['operation_id'])
    raw = json.dumps(frame, sort_keys=True, separators=(',', ':'))
    with factory.unit_of_work() as uow:
        conn = uow.connection
        if not SqliteExecutionLeaseRepository().current_channel(uow, channel):
            conflict()
        row = conn.execute('SELECT p.*,o.dispatch_state,o.reservation_owner,o.reservation_generation '
            'FROM execution_operations p JOIN execution_dispatch_outbox o USING(server_id,executor_id,operation_id) '
            'WHERE p.server_id=? AND p.executor_id=? AND p.operation_id=?', key).fetchone()
        if (row is None or row['dispatch_state'] not in ('SENDING', 'DISPATCHED')
                or row['reservation_owner'] != channel.connection_id
                or row['reservation_generation'] != channel.connection_generation
                or row['subject_agent_id'] != frame['agent_id']
                or any(row[k] != frame[k] for k in ('binding_id', 'session_id', 'intent_hash', 'action'))):
            conflict()
        old = conn.execute('SELECT * FROM execution_capacity_waits '
                           'WHERE server_id=? AND executor_id=? AND operation_id=?', key).fetchone()
        if old is not None:
            if old['connection_id'] != channel.connection_id or old['connection_generation'] != channel.connection_generation:
                conflict()
            if frame['sequence'] <= old['sequence']:
                if frame['sequence'] == old['sequence'] and old['frame_json'] != raw:
                    conflict()
                return False
        elif frame['state'] != 'WAITING' or frame['sequence'] != 1:
            conflict()
        conn.execute('INSERT INTO execution_capacity_waits VALUES(?,?,?,?,?,?,?,?) '
            'ON CONFLICT(server_id,executor_id,operation_id) DO UPDATE SET '
            'sequence=excluded.sequence,state=excluded.state,frame_json=excluded.frame_json',
            (*key, channel.connection_id, channel.connection_generation, frame['sequence'], frame['state'], raw))
        return True
