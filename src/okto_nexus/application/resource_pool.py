"""Reusable single-use pool and queue use cases; no infrastructure imports.

Methods only make short durable decisions. Starting, calling and disposing a
resource are independently dispatched effects; they never run under this unit
of work. The same service is used for embedded and remote runtime hosts.
"""
from dataclasses import replace
from typing import Callable
import uuid

from ..domain.resource_pool import PoolConflict, PoolInstance, PoolNotFound, PoolRequest
from .resource_pool_ports import PoolTransaction


class ResourcePool:
    def __init__(self, transaction: PoolTransaction, *, error_prefix='POOL',
                 identity: Callable[[], str] = lambda: 'slot_' + uuid.uuid4().hex):
        self.tx = transaction
        self.queue = transaction.requests
        self.instances = transaction.instances
        self.prefix = error_prefix
        self.identity = identity

    def request(self, request_id):
        row = self.queue.get(request_id)
        if row is None:
            raise PoolNotFound('Pool request not found.')
        return row

    def _claim(self, request, policy, host_limit, now):
        own = self.instances.count(pool_id=request.pool_id)
        total = self.instances.count(host_id=request.host_id)
        warm = self.instances.warm(pool_id=request.pool_id, host_id=request.host_id,
                                   configuration=request.configuration)
        if warm:
            if not policy.may_claim(occupied=own, host_occupied=total, host_limit=host_limit):
                return False
            self.instances.save(replace(warm, state='CLAIMED', request_id=request.request_id))
        else:
            # Reserve capacity, not a particular cold resource. The oldest
            # compatible caller receives whichever instance becomes ready first.
            pending = self.queue.preparing_count(pool_id=request.pool_id, host_id=request.host_id,
                                                 configuration=request.configuration)
            idle = sum(r.host_id == request.host_id and r.configuration == request.configuration
                       for r in self.instances.idle(pool_id=request.pool_id))
            required = pending + (request.state != 'ADMITTED')
            if idle < required:
                if not policy.room(occupied=own, host_occupied=total, host_limit=host_limit):
                    return False
                self.instances.add(PoolInstance(self.identity(), request.pool_id, request.host_id,
                    request.configuration, 'STARTING', now))
            if request.state == 'ADMITTED':
                return False
        self.queue.save(replace(request, state='ADMITTED',
            admission_deadline=request.admission_deadline or now + policy.queue_timeout_seconds))
        return True

    def admit(self, *, request_id, pool_id, host_id, caller_id, request_hash,
              configuration, host_limit, now):
        self.tx.require_write()
        previous = self.queue.get(request_id)
        if previous:
            if (previous.pool_id, previous.host_id, previous.caller_id, previous.request_hash) != (
                    pool_id, host_id, caller_id, request_hash):
                raise PoolConflict('Request identity already has another payload.')
            return previous
        policy = self.tx.policy(pool_id)
        waiting = self.queue.waiting_count(pool_id=pool_id)
        request = PoolRequest(request_id, pool_id, host_id, caller_id, request_hash,
            configuration, policy, 'QUEUED', now, now + policy.queue_timeout_seconds)
        self.queue.add(request)
        # Assign ready resources to existing callers before admitting newcomers.
        if self.instances.warm(pool_id=pool_id, host_id=host_id, configuration=configuration):
            self.advance_queue(host_id=host_id, host_limit=host_limit, now=now, exclude=request_id)
        if not waiting and self._claim(request, policy, host_limit, now):
            return self.request(request_id)
        if policy.overflow == 'reject' or waiting >= policy.queue_capacity:
            self.fail(request_id=request_id, code=self.prefix + '_CAPACITY_EXCEEDED',
                      stage='admission', message='Pool capacity is exhausted.', now=now, retry_safe=True)
        return self.request(request_id)

    def reserve_warm(self, *, pool_id, host_id, configuration, host_limit, now):
        self.tx.require_write()
        policy = self.tx.policy(pool_id)
        if self.tx.backoff(pool_id=pool_id, host_id=host_id)[1] > now:
            return None
        # Give pending callers the first opportunity to consume host capacity.
        if self.queue.waiting_count(host_id=host_id):
            return None
        if len(self.instances.idle(pool_id=pool_id)) >= policy.warm_instances + self.queue.preparing_count(pool_id=pool_id) or not policy.room(
                occupied=self.instances.count(pool_id=pool_id),
                host_occupied=self.instances.count(host_id=host_id), host_limit=host_limit):
            return None
        instance = PoolInstance(self.identity(), pool_id, host_id, configuration, 'STARTING', now)
        self.instances.add(instance)
        return instance.instance_id

    def ready(self, *, instance_id, resource_id):
        self.tx.require_write()
        row = self.instances.get(instance_id)
        if not row or row.state not in ('STARTING', 'CLOSING') or row.resource_id not in (None, resource_id):
            raise PoolConflict('Pool instance is not starting.')
        state = 'CLOSING' if row.state == 'CLOSING' else 'WARM' if row.request_id is None else 'CLAIMED'
        self.instances.save(replace(row, state=state, resource_id=resource_id))
        if state == 'WARM':
            self.tx.clear_backoff(pool_id=row.pool_id, host_id=row.host_id)

    def started(self, *, request_id, now):
        self.tx.require_write()
        request = self.request(request_id)
        if request.state == 'RUNNING':
            return
        instance = self.instances.for_request(request_id)
        if request.state != 'ADMITTED' or not instance or instance.state != 'CLAIMED':
            raise PoolConflict('Pool request is not ready.')
        self.queue.save(replace(request, state='RUNNING', started_at=now,
            execution_deadline=now + request.policy.execution_timeout_seconds))
        self.instances.save(replace(instance, state='RUNNING'))

    def finish(self, *, request_id, outcome, now, state='SUCCEEDED'):
        self.tx.require_write()
        request = self.request(request_id)
        if request.outcome is not None:
            return request.outcome
        if state not in ('SUCCEEDED', 'FAILED', 'CANCELLED') or (state == 'SUCCEEDED' and request.state != 'RUNNING'):
            raise PoolConflict('Invalid pool terminal transition.')
        if type(outcome) is not dict or set(outcome) & {'call_id', 'state', 'completed_at'}:
            raise ValueError('Outcome cannot replace request identity or terminal state.')
        result = dict(call_id=request_id, state=state, completed_at=now, **outcome)
        self.queue.save(replace(request, state=state, outcome=result))
        instance = self.instances.for_request(request_id)
        if instance:
            self.instances.save(replace(instance, state='CLOSING'))
        return result

    def fail(self, *, request_id, code, stage, message, now, retry_safe=False, cancelled=False):
        began = self.request(request_id).started_at is not None
        error = dict(call_id=request_id, code=code, message=message, stage=stage,
                     execution_started=began, possible_effect=began, retry_safe=retry_safe and not began)
        return self.finish(request_id=request_id, outcome={'error': error}, now=now,
                           state='CANCELLED' if cancelled else 'FAILED')

    def dispose_confirmed(self, *, instance_id, resource_id):
        self.tx.require_write()
        row = self.instances.get(instance_id)
        if not row or row.resource_id != resource_id or row.state != 'CLOSING':
            return False
        self.instances.remove(instance_id)
        return True

    def retire_warm(self, *, pool_id, host_id, configuration, binding_id=None):
        self.tx.require_write()
        rows = self.instances.incompatible(pool_id=pool_id, host_id=host_id,
            configuration=configuration, binding_id=binding_id)
        for row in rows:
            self.instances.save(replace(row, state='CLOSING'))
        return len(rows)

    def trim_warm(self, *, pool_id, host_id):
        self.tx.require_write()
        policy = self.tx.policy(pool_id)
        occupied = self.instances.count(pool_id=pool_id) - self.instances.closing_count(pool_id=pool_id)
        idle = self.instances.idle(pool_id=pool_id)
        excess = max(0, len(idle) - policy.warm_instances - self.queue.preparing_count(pool_id=pool_id),
                     occupied - policy.max_parallel if policy.max_parallel else 0)
        for row in idle[:excess]:
            self.instances.save(replace(row, state='CLOSING'))
        return min(excess, len(idle))

    def advance_queue(self, *, host_id, host_limit, now, exclude=None):
        self.tx.require_write()
        for request in self.queue.expired(host_id=host_id, now=now, limit=1024):
            self.fail(request_id=request.request_id, code=self.prefix + '_QUEUE_EXPIRED', stage='queue',
                      message='The call expired before execution started.', now=now, retry_safe=True)
        admitted, blocked = [], set()
        for request in self.queue.waiting(host_id=host_id, limit=1024):
            if request.request_id == exclude:
                continue
            # An expired item outside this expiry batch must never execute.
            deadline = request.admission_deadline if request.state == 'ADMITTED' else request.queue_deadline
            if request.pool_id in blocked or deadline <= now:
                blocked.add(request.pool_id)
                continue
            if self._claim(request, self.tx.policy(request.pool_id), host_limit, now):
                admitted.append(request.request_id)
            elif request.state != 'ADMITTED':
                blocked.add(request.pool_id)
        return admitted

    def expire_executions(self, *, host_id, now):
        self.tx.require_write()
        rows = self.queue.timed_out(host_id=host_id, now=now, limit=1024)
        for request in rows:
            opening = request.state == 'ADMITTED'
            self.fail(request_id=request.request_id,
                code=self.prefix + ('_START_TIMEOUT' if opening else '_EXECUTION_TIMEOUT'),
                stage='opening' if opening else 'execution', message='The execution deadline was exceeded.',
                now=now, retry_safe=opening)
        return len(rows)

    def warm_failed(self, *, instance_id, now):
        self.tx.require_write()
        row = self.instances.get(instance_id)
        if not row or row.request_id is not None or row.state == 'CLOSING':
            return
        self.instances.save(replace(row, state='CLOSING'))
        failures = min(self.tx.backoff(pool_id=row.pool_id, host_id=row.host_id)[0] + 1, 16)
        self.tx.save_backoff(pool_id=row.pool_id, host_id=row.host_id,
            failures=failures, until=now + min(2 ** failures, 300))

    def statistics(self, *, pool_id, host_id):
        states = self.instances.states(pool_id=pool_id, host_id=host_id)
        return dict(starting=states.get('STARTING', 0), warm=states.get('WARM', 0),
            claimed=states.get('CLAIMED', 0), running=states.get('RUNNING', 0), closing=states.get('CLOSING', 0),
            queued=self.queue.waiting_count(pool_id=pool_id, host_id=host_id), occupied=sum(states.values()))
