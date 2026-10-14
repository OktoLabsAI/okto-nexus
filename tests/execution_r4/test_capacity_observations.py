"""Context diagnostics are bounded observations, never an admission promise."""
import asyncio
from dataclasses import replace
import json

import pytest
from nexus_connector_core import CapacityAssessment, CapacityReservation, CapacityConsumption, CoreError
from okto_nexus.application.capacity_observations import CapacityObservations
from okto_nexus.application.runtime_availability import RuntimeAvailabilityService
from test_capacity_link import CHANNEL, request
from test_runtime_availability import observe


def assessment(req, reason='AVAILABLE', revision=1, ttl=5000):
    return CapacityAssessment(req.contract_revision, req.request_hash, reason, revision, ttl)


def registry(port=None):
    now, calls = [10.], []
    class Port:
        async def assess_capacity(self, req):
            calls.append(req)
            return assessment(req)
    service = RuntimeAvailabilityService(enabled=True, monotonic=lambda: now[0])
    host = service.register(CHANNEL, port or Port())
    observe(service, host)
    return service, host, now, calls


def test_contexts_are_distinct_and_reads_do_not_probe_or_wake():
    service, host, now, calls = registry()
    a, b = request(), replace(request('other'), unit='next_turn')
    asyncio.run(service.assess_capacity(a))
    asyncio.run(service.assess_capacity(b))
    service.wake = lambda: pytest.fail('Reading diagnostics woke the scheduler')
    for _ in range(2):
        view = service.capacity_observations('agent')
        assert [r['state'] for r in view['items']] == ['IDLE_OBSERVED', 'OPENING_CAPACITY_OBSERVED']
        assert all(r['fresh'] for r in view['items'])
        assert len(calls) == 2
        assert service.capacity_observations('other-agent') == dict(items=[], has_more=False)
    assert set(view['items'][0]) == {'executor_id','binding_id','workspace_id','session_id','unit',
                                    'context_id','state','reason','age_ms','fresh','valid_for_ms'}
    assert 'request_hash' not in json.dumps(view)
    now[0] += 5
    assert all(r['state'] == 'UNKNOWN' and not r['fresh'] for r in service.capacity_observations('agent')['items'])


@pytest.mark.parametrize('change', ['publication', 'publication_expired', 'recovering', 'clock_rollback', 'scope'])
def test_stale_observation_never_appears_idle(change):
    service, host, now, _ = registry()
    asyncio.run(service.assess_capacity(request()))
    kwargs = {}
    if change == 'publication':
        observe(service, host, revision=2)
    elif change == 'publication_expired':
        observe(service, host, valid_for_ms=0)
    elif change == 'recovering':
        observe(service, host, reason='RECOVERING')
    elif change == 'clock_rollback':
        now[0] -= 1
    else:
        kwargs['validate'] = lambda requests: set()
    row = service.capacity_observations('agent', **kwargs)['items'][0]
    assert row['state'] == 'UNKNOWN' and row['reason'] == 'STALE_OBSERVATION' and not row['fresh']


@pytest.mark.parametrize('reason,state', [('BUSY_AFFINITY','WAITING_CAPACITY'), ('HOST_FULL','WAITING_CAPACITY'),
    ('POOL_FULL','WAITING_CAPACITY'), ('EARLIER_WORK_PENDING','WAITING_CAPACITY'),
    ('NOT_AUTHORIZED','UNKNOWN'), ('RECOVERING','UNKNOWN'), ('CAPACITY_PROTOCOL_UNSUPPORTED','UNKNOWN')])
def test_unavailability_reasons_are_not_converted_to_free_capacity(reason, state):
    req = request()
    class Port:
        async def assess_capacity(self, request):
            return assessment(request, reason)
    service, _, _, _ = registry(Port())
    asyncio.run(service.assess_capacity(req))
    row = service.capacity_observations('agent')['items'][0]
    assert row['state'] == state and row['reason'] == reason


@pytest.mark.parametrize('state,expected', [('HELD','RESERVED'), ('CONSUMED','IN_USE'),
    ('RELEASE_PENDING','RELEASE_PENDING'), ('RELEASED','UNKNOWN'), ('EXPIRED_UNCONSUMED','UNKNOWN'),
    ('NEEDS_RECONCILIATION','UNKNOWN')])
def test_reservation_observation_and_release_are_not_implicit_free_capacity(state, expected):
    service, host, now, _ = registry()
    req = request()
    consumption = CapacityConsumption('turn', 'sha256:'+'c'*64, 'open', 'sha256:'+'d'*64) if state == 'CONSUMED' else None
    result = CapacityReservation('reserved', req, state, 1, 2000 if state == 'HELD' else 0, consumption)
    service.diagnostics.record(req, result, host.channel)
    row = service.capacity_observations('agent')['items'][0]
    assert row['state'] == expected and row['reason'] == state
    now[0] += 2 if state == 'HELD' else 5
    assert not service.capacity_observations('agent')['items'][0]['fresh']


@pytest.mark.parametrize('fail', [False, True])
def test_pending_mutation_invalidates_assessments_even_when_response_is_lost(fail):
    async def run():
        started, finish = asyncio.Event(), asyncio.Event()
        req = request()
        class Port:
            async def assess_capacity(self, request):
                return assessment(request)
            async def try_reserve_capacity(self, request):
                started.set()
                await finish.wait()
                if fail:
                    raise CoreError('NEEDS_RECONCILIATION', 'lost', possible_effect=True)
                return CapacityReservation('reserved', request, 'HELD', 2, 5000, None)
        service, _, _, _ = registry(Port())
        await service.assess_capacity(req)
        task = asyncio.create_task(service.try_reserve_capacity(req))
        await started.wait()
        assert service.capacity_observations('agent')['items'] == []
        await service.assess_capacity(req)
        assert service.capacity_observations('agent')['items'] == []
        finish.set()
        if fail:
            with pytest.raises(CoreError, match='NEEDS_RECONCILIATION'):
                await task
            assert service.capacity_observations('agent')['items'] == []
        else:
            await task
            assert service.capacity_observations('agent')['items'][0]['state'] == 'RESERVED'
    asyncio.run(run())


def test_late_pre_mutation_assessment_cannot_overwrite_reservation():
    async def run():
        entered, finish = asyncio.Event(), asyncio.Event()
        req = request()
        class Port:
            async def assess_capacity(self, request):
                entered.set()
                await finish.wait()
                return assessment(request)
            async def try_reserve_capacity(self, request):
                return CapacityReservation('reserved', request, 'HELD', 2, 5000, None)
        service, _, _, _ = registry(Port())
        task = asyncio.create_task(service.assess_capacity(req))
        await entered.wait()
        await service.try_reserve_capacity(req)
        finish.set()
        await task
        assert service.capacity_observations('agent')['items'][0]['state'] == 'RESERVED'
    asyncio.run(run())


def test_mismatched_results_older_revisions_and_owner_replacement_cannot_refresh_cache():
    service, host, _, _ = registry()
    req = request()
    service.diagnostics.record(req, assessment(req, 'HOST_FULL', 3), host.channel)
    service.diagnostics.record(req, assessment(req, revision=2), host.channel)
    service.diagnostics.record(req, assessment(request('foreign'), revision=4), host.channel)
    assert service.capacity_observations('agent')['items'][0]['reason'] == 'HOST_FULL'
    service.register(replace(CHANNEL, connection_id='new', connection_generation=2), object())
    assert service.capacity_observations('agent')['items'] == []


def test_cache_and_pages_are_bounded_without_cross_agent_leaks():
    service, host, _, _ = registry()
    service.diagnostics = CapacityObservations(monotonic=service.monotonic, limit=25)
    for i in range(30):
        req = request(str(i))
        service.diagnostics.record(req, assessment(req), host.channel)
    view = service.capacity_observations('agent')
    assert len(service.diagnostics._items) == 25
    assert len(view['items']) == 20 and view['has_more']
    assert view['items'][0]['session_id'] == '29'
    assert service.capacity_observations('foreign')['items'] == []


def test_slow_configuration_read_does_not_extend_observation_deadline():
    service, _, now, _ = registry()
    asyncio.run(service.assess_capacity(request()))
    def validate(requests):
        now[0] += 6
        return {r.request_hash for r in requests}
    row = service.capacity_observations('agent', validate=validate)['items'][0]
    assert row['state'] == 'UNKNOWN' and row['valid_for_ms'] == 0
