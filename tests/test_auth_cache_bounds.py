"""Bounded positive authentication cache, invalidation races and identity churn."""
import concurrent.futures
import json
import os
import platform
import threading
import time
import tracemalloc

import pytest

from test_auth_service import FakeAgentRepo, StubClock
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteAgentRepo
from okto_nexus.domain.keys import hash_api_key


def key(index):
    return "nxs_" + format(index, "048x")


def populated(capacity=2):
    repo, clock = FakeAgentRepo(), StubClock()
    for index in range(4):
        repo.upsert(None, agent_id=str(index))
        repo.set_key_hash(None, agent_id=str(index), api_key_hash=hash_api_key(key(index)))
    return AgentKeyAuthService(repo, clock, cache_max_entries=capacity), repo, clock


def test_lru_eviction_keeps_both_indexes_bounded_and_invalidation_working():
    service, repo, clock = populated()
    for index in (0, 1, 0, 2):
        assert service.resolve(None, key(index)).agent_id == str(index)
    before = repo.lookups
    service.resolve(None, key(0))
    assert repo.lookups == before
    service.resolve(None, key(1))
    assert repo.lookups == before + 1
    assert len(service._by_hash) == len(service._hash_by_agent) == 2
    service.set_active(None, agent_id="1", is_active=False)
    assert service.resolve(None, key(1)) is None
    clock.advance_seconds(61)
    service.resolve(None, key(0))
    assert len(service._by_hash) == len(service._hash_by_agent) <= 2
    service.invalidate_all()
    assert not service._by_hash and not service._hash_by_agent


@pytest.mark.parametrize("scope", ["agent", "all"])
def test_lookup_started_before_invalidation_cannot_repopulate_cache(scope):
    service, repo, _ = populated()
    entered, resume = threading.Event(), threading.Event()
    original = repo.get_active_by_key_hash
    def held(*args, **kwargs):
        result = original(*args, **kwargs)
        entered.set()
        assert resume.wait(5)
        return result
    repo.get_active_by_key_hash = held
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(service.resolve, None, key(0))
        try:
            assert entered.wait(5)
            if scope == "agent":
                service.invalidate_agent("0")
            else:
                service.invalidate_all()
        finally:
            resume.set()
        pending.result(timeout=5)
    assert not service._by_hash and not service._hash_by_agent
    repo.get_active_by_key_hash = original
    service.resolve(None, key(0))
    assert repo.lookups == 2


@pytest.mark.parametrize("options", [
    {"cache_max_entries": -1}, {"cache_max_entries": 4097},
    {"cache_max_entries": True}, {"cache_ttl_seconds": -1},
    {"cache_ttl_seconds": 61}, {"cache_ttl_seconds": float("inf")},
    {"cache_ttl_seconds": float("nan")},
])
def test_invalid_cache_limits_refused(options):
    with pytest.raises(ValueError):
        AgentKeyAuthService(FakeAgentRepo(), StubClock(), **options)


def test_zero_capacity_disables_positive_cache():
    service, repo, _ = populated(0)
    for _ in range(3):
        assert service.resolve(None, key(0)) is not None
    assert repo.lookups == 3 and not service._by_hash and not service._hash_by_agent


def test_100k_sqlite_identities_use_indexed_lookup_and_bounded_cache(migrated_factory, record_property):
    clock = StubClock()
    repo = SqliteAgentRepo(clock)
    service = AgentKeyAuthService(repo, clock)
    count = 100_000
    threads_before = threading.active_count()
    with migrated_factory.unit_of_work() as uow:
        uow.connection.executemany(
            "INSERT INTO agents(agent_id,created_at,api_key_hash,is_active) VALUES(?,?,?,1)",
            ((str(i), clock.now_iso(), hash_api_key(key(i))) for i in range(count)))
    with migrated_factory.unit_of_work() as uow:
        plan = [row[3] for row in uow.connection.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM agents WHERE api_key_hash=? AND is_active=1",
            (hash_api_key(key(0)),))]
        assert any("SEARCH" in line and "INDEX" in line for line in plan), plan
        started = time.perf_counter()
        tracemalloc.start()
        samples = []
        try:
            for index in range(count):
                assert service.resolve(uow, key(index)).agent_id == str(index)
                if (index + 1) % 25_000 == 0:
                    current, peak = tracemalloc.get_traced_memory()
                    samples.append(dict(identities=index + 1, current_bytes=current, peak_bytes=peak,
                                        entries=len(service._by_hash), reverse_entries=len(service._hash_by_agent)))
                    assert len(service._by_hash) == len(service._hash_by_agent) == 4096
            # Churn includes cache hits, expiry, synchronous revocation and reactivation.
            for index in range(count - 100, count):
                service.set_active(uow, agent_id=str(index), is_active=False)
                assert service.resolve(uow, key(index)) is None
                service.set_active(uow, agent_id=str(index), is_active=True)
                assert service.resolve(uow, key(index)) is not None
            clock.advance_seconds(61)
            assert service.resolve(uow, key(count - 1)) is not None
        finally:
            tracemalloc.stop()
        elapsed = time.perf_counter() - started
    # Stable fixture payloads must plateau after capacity, independent of row count.
    assert samples[-1]["current_bytes"] < samples[0]["current_bytes"] * 1.5 + 262144
    threads_after = threading.active_count()
    assert threads_after == threads_before
    record_property("auth_cache_load", json.dumps(dict(
        identities=count, elapsed_seconds=elapsed, samples=samples, query_plan=plan,
        threads_before=threads_before, threads_after=threads_after,
        platform=platform.platform(), processor=platform.processor(), logical_cpus=os.cpu_count(),
        topology="Actual SQLite adapter and migrated database; one transaction for measured lookups; no providers.")))
