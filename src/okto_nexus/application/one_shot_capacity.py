"""One-shot compatibility facade over the reusable pool/queue service."""
import json
from functools import wraps

from ..domain.resource_pool import PoolConflict, PoolNotFound
from ..errors import ErrorCode, OktoNexusError


def _pool(conn):
    from ..bootstrap.resource_pool import one_shot_pool
    return one_shot_pool(conn)


def _legacy(row):
    return dict(call_id=row.request_id, agent_id=row.pool_id, executor_id=row.host_id,
        caller_id=row.caller_id, request_hash=row.request_hash, configuration_digest=row.configuration,
        policy_json=json.dumps(row.policy.to_dict(), sort_keys=True, separators=(",", ":")),
        state=row.state, enqueued_at=row.enqueued_at, queue_deadline=row.queue_deadline,
        started_at=row.started_at, execution_deadline=row.execution_deadline,
        admission_deadline=row.admission_deadline,
        outcome_json=json.dumps(row.outcome, sort_keys=True, separators=(",", ":")) if row.outcome is not None else None)


def _translate(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except PoolNotFound as error:
            raise OktoNexusError(ErrorCode.NOT_FOUND, str(error), {}) from error
        except PoolConflict as error:
            raise OktoNexusError(ErrorCode.CONFLICT, str(error), {}) from error
    return wrapped


def policy(conn, agent_id):
    return _pool(conn).tx.policy(agent_id)


@_translate
def _row(conn, call_id):
    return _legacy(_pool(conn).request(call_id))


@_translate
def admit(conn, *, call_id, agent_id, executor_id, caller_id, request_hash, configuration_digest, host_limit, now):
    return _legacy(_pool(conn).admit(request_id=call_id, pool_id=agent_id, host_id=executor_id,
        caller_id=caller_id, request_hash=request_hash, configuration=configuration_digest, host_limit=host_limit, now=now))


@_translate
def reserve_warm(conn, *, agent_id, executor_id, configuration_digest, host_limit, now):
    return _pool(conn).reserve_warm(pool_id=agent_id, host_id=executor_id,
        configuration=configuration_digest, host_limit=host_limit, now=now)


@_translate
def ready(conn, *, slot_id, session_id):
    return _pool(conn).ready(instance_id=slot_id, resource_id=session_id)


@_translate
def started(conn, *, call_id, now):
    return _pool(conn).started(request_id=call_id, now=now)


@_translate
def finish(conn, *, call_id, outcome, now, state="SUCCEEDED"):
    return _pool(conn).finish(request_id=call_id, outcome=outcome, now=now, state=state)


@_translate
def fail(conn, *, call_id, **kwargs):
    return _pool(conn).fail(request_id=call_id, **kwargs)


@_translate
def dispose_confirmed(conn, *, slot_id, session_id):
    return _pool(conn).dispose_confirmed(instance_id=slot_id, resource_id=session_id)


@_translate
def retire_warm(conn, *, agent_id, executor_id, configuration_digest, binding_id=None):
    return _pool(conn).retire_warm(pool_id=agent_id, host_id=executor_id,
        configuration=configuration_digest, binding_id=binding_id)


@_translate
def trim_warm(conn, *, agent_id, executor_id):
    return _pool(conn).trim_warm(pool_id=agent_id, host_id=executor_id)


@_translate
def advance_queue(conn, *, executor_id, host_limit, now):
    return _pool(conn).advance_queue(host_id=executor_id, host_limit=host_limit, now=now)


def pending_outcomes(conn, *, caller_id, limit=100):
    return _pool(conn).queue.outcomes(caller_id=caller_id, limit=limit)


def acknowledge_outcome(conn, *, caller_id, call_id, now):
    pool = _pool(conn)
    pool.tx.require_write()
    return pool.queue.acknowledge(caller_id=caller_id, request_id=call_id, now=now)


@_translate
def warm_failed(conn, *, slot_id, now):
    return _pool(conn).warm_failed(instance_id=slot_id, now=now)


@_translate
def expire_executions(conn, *, executor_id, now):
    return _pool(conn).expire_executions(host_id=executor_id, now=now)


def statistics(conn, *, executor_id, agent_id):
    return _pool(conn).statistics(pool_id=agent_id, host_id=executor_id)
