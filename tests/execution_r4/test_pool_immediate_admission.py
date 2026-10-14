"""Immediate competitive admission is distinct from explicit queued work."""
import pytest

from okto_nexus.domain.resource_pool import PoolInstance, PoolPolicy, PoolUnavailable
from test_pool_ports import pool, admit


def test_busy_pool_with_free_queue_does_not_create_losing_call(pool):
    admit(pool, 'existing')
    with pytest.raises(PoolUnavailable):
        admit(pool, 'competitive', immediate_only=True)
    assert pool.queue.get('competitive') is None
    assert pool.queue.outcomes(caller_id='caller', limit=100) == []
    assert admit(pool, 'explicit').state == 'QUEUED'


def test_warm_admission_reuses_one_physical_slot_at_host_ceiling(pool):
    pool.instances.add(PoolInstance('warm', 'agent', 'host', 'configuration', 'WARM', 0,
                                    resource_id='warm-session'))
    first = admit(pool, 'competitive', immediate_only=True, host_limit=1)
    assert first.state == 'ADMITTED'
    assert pool.instances.count(host_id='host') == 1
    assert pool.instances.for_request(first.request_id).resource_id == 'warm-session'
    assert admit(pool, 'competitive', immediate_only=True, host_limit=1) == first
    with pytest.raises(PoolUnavailable):
        admit(pool, 'other-broadcast', immediate_only=True, host_limit=1)
    assert pool.queue.get('other-broadcast') is None


def test_cold_slot_is_assigned_and_startup_is_bounded(pool):
    first = admit(pool, 'competitive', immediate_only=True, now=5)
    slot = pool.instances.for_request(first.request_id)
    assert slot.state == 'STARTING' and slot.resource_id is None
    assert first.admission_deadline == 65
    assert pool.queue.waiting(host_id='host', limit=100) == []
    # This admission does not launch a provider. Its deadline cannot free an
    # uncertain STARTING resource; disposal still needs the normal proof.
    pool.expire_executions(host_id='host', now=66)
    assert pool.instances.get(slot.instance_id).state == 'CLOSING'
    with pytest.raises(PoolUnavailable):
        admit(pool, 'next', immediate_only=True)


@pytest.mark.parametrize('state', ['STARTING', 'CLOSING'])
def test_starting_and_closing_are_not_free_resources(pool, state):
    pool.instances.add(PoolInstance('occupied', 'agent', 'host', 'configuration', state, 0))
    with pytest.raises(PoolUnavailable):
        admit(pool, 'competitive', immediate_only=True)
    assert pool.queue.get('competitive') is None


def test_unlimited_pool_still_obeys_physical_host(pool, monkeypatch):
    monkeypatch.setattr(pool.tx, 'policy', lambda _: PoolPolicy(max_parallel=0))
    assert admit(pool, 'first', immediate_only=True, host_limit=1).state == 'ADMITTED'
    with pytest.raises(PoolUnavailable, match='HOST_FULL'):
        admit(pool, 'second', immediate_only=True, host_limit=1)
    assert pool.instances.count(host_id='host') == 1


def test_immediate_does_not_overtake_preparing_or_queued_work(pool):
    admit(pool, 'first')
    slot = pool.instances.idle(pool_id='agent')[0]
    pool.ready(instance_id=slot.instance_id, resource_id='session')
    with pytest.raises(PoolUnavailable, match='EARLIER_WORK_PENDING'):
        admit(pool, 'competitive', immediate_only=True)
    assert pool.instances.get(slot.instance_id).state == 'WARM'
    assert pool.advance_queue(host_id='host', host_limit=3, now=1) == ['first']
    admit(pool, 'queued')
    pool.started(request_id='first', now=1)
    pool.finish(request_id='first', outcome={'response': 'done'}, now=2)
    pool.dispose_confirmed(instance_id=slot.instance_id, resource_id='session')
    with pytest.raises(PoolUnavailable, match='EARLIER_WORK_PENDING'):
        admit(pool, 'competitive', immediate_only=True, now=3)
    assert pool.advance_queue(host_id='host', host_limit=3, now=3) == ['queued']


def test_warm_resource_with_different_configuration_is_not_admitted(pool):
    pool.instances.add(PoolInstance('old', 'agent', 'host', 'previous-config', 'WARM', 0,
                                    resource_id='old-session'))
    with pytest.raises(PoolUnavailable):
        admit(pool, 'competitive', immediate_only=True)
    assert pool.instances.get('old').request_id is None
