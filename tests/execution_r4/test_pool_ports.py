"""Run the same pool service through two independent storage adapters.

The in-memory adapter is test-only: production always uses durable SQLite.
It demonstrates that pool rules do not depend on a connection or SQL rows.
"""
import pytest

from okto_nexus.application.resource_pool import ResourcePool
from okto_nexus.adapters.outbound.sqlite.resource_pool import SQLitePoolTransaction
from okto_nexus.domain.resource_pool import PoolPolicy
from test_one_shot_capacity import database, initialize


class MemoryRequests:
    def __init__(self, instances):
        self.rows, self.acks = {}, set()
        self.instances = instances

    def get(self, request_id):
        return self.rows.get(request_id)

    def add(self, request):
        assert request.request_id not in self.rows
        self.save(request)

    def save(self, request):
        self.rows[request.request_id] = request

    def waiting(self, *, host_id, limit):
        return sorted((r for r in self.rows.values() if r.host_id == host_id and
                       (r.state == 'QUEUED' or (r.state == 'ADMITTED' and not self.instances.for_request(r.request_id)))),
                      key=lambda r: (r.enqueued_at, r.request_id))[:limit]

    def preparing_count(self, *, pool_id, host_id=None, configuration=None):
        return sum(r.state == 'ADMITTED' and not self.instances.for_request(r.request_id)
                   and r.pool_id == pool_id and (host_id is None or r.host_id == host_id)
                   and (configuration is None or r.configuration == configuration) for r in self.rows.values())

    def waiting_count(self, *, pool_id=None, host_id=None):
        return sum(r.state == 'QUEUED' and (pool_id is None or r.pool_id == pool_id)
                   and (host_id is None or r.host_id == host_id) for r in self.rows.values())

    def expired(self, *, host_id, now, limit):
        return [r for r in self.waiting(host_id=host_id, limit=limit) if r.state == 'QUEUED' and r.queue_deadline <= now]

    def timed_out(self, *, host_id, now, limit):
        return [r for r in self.rows.values() if r.host_id == host_id and
                ((r.state == 'ADMITTED' and r.admission_deadline <= now) or
                 (r.state == 'RUNNING' and r.execution_deadline <= now))][:limit]

    def outcomes(self, *, caller_id, limit):
        return [r.outcome for r in self.rows.values() if r.caller_id == caller_id
                and r.outcome is not None and r.request_id not in self.acks][:limit]

    def acknowledge(self, *, caller_id, request_id, now):
        row = self.get(request_id)
        if not row or row.caller_id != caller_id or row.outcome is None:
            return False
        self.acks.add(request_id)
        return True


class MemoryInstances:
    def __init__(self):
        self.rows = {}

    def get(self, instance_id):
        return self.rows.get(instance_id)

    def for_request(self, request_id):
        return next((r for r in self.rows.values() if r.request_id == request_id), None)

    def add(self, instance):
        assert instance.instance_id not in self.rows
        self.save(instance)

    def save(self, instance):
        self.rows[instance.instance_id] = instance

    def remove(self, instance_id):
        del self.rows[instance_id]

    def count(self, *, pool_id=None, host_id=None):
        return sum((pool_id is None or r.pool_id == pool_id) and (host_id is None or r.host_id == host_id)
                   for r in self.rows.values())

    def warm(self, *, pool_id, host_id, configuration):
        return next((r for r in self.rows.values() if r.pool_id == pool_id and r.host_id == host_id
                     and r.configuration == configuration and r.state == 'WARM'), None)

    def idle(self, *, pool_id):
        return sorted((r for r in self.rows.values() if r.pool_id == pool_id and r.request_id is None
                       and r.state in ('STARTING', 'WARM')), key=lambda r: (r.created_at, r.instance_id), reverse=True)

    def incompatible(self, *, pool_id, host_id, configuration, binding_id=None):
        return [r for r in self.idle(pool_id=pool_id) if r.host_id == host_id and r.configuration != configuration]

    def states(self, *, pool_id, host_id):
        from collections import Counter
        return dict(Counter(r.state for r in self.rows.values() if r.pool_id == pool_id and r.host_id == host_id))

    def closing_count(self, *, pool_id):
        return sum(r.pool_id == pool_id and r.state == 'CLOSING' for r in self.rows.values())


class MemoryTransaction:
    def __init__(self):
        self.instances = MemoryInstances()
        self.requests = MemoryRequests(self.instances)
        self.delays = {}

    def require_write(self):
        pass  # Tests have one owner and no concurrent access.

    def policy(self, pool_id):
        return PoolPolicy()

    def backoff(self, *, pool_id, host_id):
        return self.delays.get((pool_id, host_id), (0, 0))

    def save_backoff(self, *, pool_id, host_id, failures, until):
        self.delays[pool_id, host_id] = failures, until

    def clear_backoff(self, *, pool_id, host_id):
        self.delays.pop((pool_id, host_id), None)


@pytest.fixture(params=['sqlite', 'memory'])
def pool(request):
    if request.param == 'memory':
        yield ResourcePool(MemoryTransaction())
    else:
        conn = database()
        initialize(conn)
        conn.execute('BEGIN IMMEDIATE')
        try:
            yield ResourcePool(SQLitePoolTransaction(conn))
        finally:
            conn.close()


def admit(pool, request_id, **changes):
    return pool.admit(**(dict(request_id=request_id, pool_id='agent', host_id='host', caller_id='caller',
        request_hash=request_id, configuration='configuration', host_limit=3, now=0) | changes))


def test_adapter_contract_disposal_and_fifo(pool):
    first = admit(pool, 'first')
    assert admit(pool, 'first') == first
    assert admit(pool, 'second').state == 'QUEUED'
    assert admit(pool, 'third', now=1).state == 'QUEUED'
    assert pool.instances.for_request('first') is None
    resource = pool.instances.idle(pool_id='agent')[0]
    pool.ready(instance_id=resource.instance_id, resource_id='resource')
    pool.advance_queue(host_id='host', host_limit=3, now=1)
    pool.started(request_id='first', now=1)
    pool.finish(request_id='first', outcome={'response': 'ok'}, now=2)
    assert pool.advance_queue(host_id='host', host_limit=3, now=3) == []
    assert not pool.dispose_confirmed(instance_id=resource.instance_id, resource_id='wrong-generation')
    assert pool.dispose_confirmed(instance_id=resource.instance_id, resource_id='resource')
    assert not pool.dispose_confirmed(instance_id=resource.instance_id, resource_id='resource')
    assert pool.advance_queue(host_id='host', host_limit=3, now=4) == ['second']
    assert pool.queue.outcomes(caller_id='caller', limit=100)[0]['response'] == 'ok'


def test_adapter_contract_expiry_is_durable_and_not_executed(pool):
    admit(pool, 'first')
    admit(pool, 'expired')
    assert pool.advance_queue(host_id='host', host_limit=3, now=301) == []
    result = pool.queue.outcomes(caller_id='caller', limit=100)[0]
    assert result['error']['code'] == 'POOL_QUEUE_EXPIRED'
    assert result['error']['retry_safe']
    assert pool.instances.for_request('expired') is None
    assert not pool.queue.acknowledge(caller_id='intruder', request_id='expired', now=302)
    assert pool.queue.acknowledge(caller_id='caller', request_id='expired', now=302)
    assert pool.queue.outcomes(caller_id='caller', limit=100) == []


def test_architecture_has_no_infrastructure_dependencies():
    import ast
    import inspect
    from okto_nexus.application import resource_pool, resource_pool_ports
    from okto_nexus.domain import resource_pool as rules
    for module in (resource_pool, resource_pool_ports, rules):
        tree = ast.parse(inspect.getsource(module))
        imports = [n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        assert not any(any(word in item for word in ('sqlite', 'adapters', 'bootstrap', 'nexus_connector_core', 'fastapi')) for item in imports)
