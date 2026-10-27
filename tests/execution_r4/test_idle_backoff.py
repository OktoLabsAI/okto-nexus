"""Idle serve loops sleep up to the idle interval. Pending work keeps the short tick."""
import asyncio
from contextlib import contextmanager
import functools
import time
from types import SimpleNamespace

import pytest

from okto_nexus.application import execution_dispatch_pump as pumps
from okto_nexus.application import runtime_recovery
from okto_nexus.application.handoff_runtime_scheduler import HandoffRuntimeScheduler
from okto_nexus.bootstrap.embedded_agent_recovery import EmbeddedAgentRecovery
from okto_nexus.bootstrap.embedded_dispatch import EmbeddedDispatchOwner
from okto_nexus.config import NexusConfig


async def until(condition, timeout=5):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "The condition never became true"
        await asyncio.sleep(.01)


def maintenance_owner(monkeypatch, *, busy, idle_interval):
    monkeypatch.setattr(runtime_recovery, "drain_pending", lambda deps: None)
    ticks = []

    async def tick():
        ticks.append(time.monotonic())

    owner = SimpleNamespace(
        _stopping=asyncio.Event(), _activity=asyncio.Event(), failure=None, deps=None,
        idle_interval=idle_interval, agents=SimpleNamespace(tick=tick, busy=lambda: busy[0]),
        capacity_publication=SimpleNamespace(tick=lambda: None))
    owner._idle_sleep = functools.partial(EmbeddedDispatchOwner._idle_sleep, owner)
    return owner, ticks


def test_idle_maintenance_ticks_at_the_idle_interval_and_busy_maintenance_at_the_short_tick(monkeypatch):
    async def scenario():
        busy = [False]
        owner, ticks = maintenance_owner(monkeypatch, busy=busy, idle_interval=5)
        task = asyncio.create_task(EmbeddedDispatchOwner._maintain(owner))
        try:
            await until(lambda: len(ticks) == 1)
            await asyncio.sleep(.5)
            assert len(ticks) == 1, "An idle loop ticked at the short interval"
            busy[0] = True
            owner._activity.set()
            await until(lambda: len(ticks) >= 4)
        finally:
            owner._stopping.set()
            await task

    asyncio.run(scenario())


def test_activity_wakes_an_idle_maintenance_loop(monkeypatch):
    async def scenario():
        owner, ticks = maintenance_owner(monkeypatch, busy=[False], idle_interval=60)
        task = asyncio.create_task(EmbeddedDispatchOwner._maintain(owner))
        try:
            await until(lambda: len(ticks) == 1)
            owner._activity.set()
            await until(lambda: len(ticks) == 2)
        finally:
            owner._stopping.set()
            await asyncio.wait_for(task, 5)

    asyncio.run(scenario())


def test_shutdown_ends_an_idle_maintenance_sleep_at_once(monkeypatch):
    async def scenario():
        owner, ticks = maintenance_owner(monkeypatch, busy=[False], idle_interval=60)
        task = asyncio.create_task(EmbeddedDispatchOwner._maintain(owner))
        await until(lambda: len(ticks) == 1)
        owner._stopping.set()
        await asyncio.wait_for(task, 5)

    asyncio.run(scenario())


def test_idle_interval_comes_from_the_configuration():
    owner = object.__new__(EmbeddedDispatchOwner)
    owner.deps = SimpleNamespace(config=NexusConfig(runtime_idle_interval_ms=2500))
    assert owner.idle_interval == 2.5
    owner.deps = None
    assert owner.idle_interval == 1.0


def recovery(**owner_fields):
    owner = SimpleNamespace(workers=set(), sessions={}, _activity=asyncio.Event(), active_operations=set(),
                            worker_agents={}, idle_interval=1.0, **owner_fields)
    agents = EmbeddedAgentRecovery(owner)
    agents.last_active = time.monotonic() - 3600
    agents.unsettled = False
    return owner, agents


def test_host_is_idle_until_work_shows():
    async def scenario():
        owner, agents = recovery()
        assert not agents.busy()
        agents.touch()
        assert agents.busy() and owner._activity.is_set()
        agents.last_active -= 3600
        for state in (lambda: agents.blocked.add("a"), lambda: setattr(agents, "unsettled", True),
                      lambda: owner.workers.add("task"), lambda: agents.session_tasks.update(s="task"),
                      lambda: owner.sessions.update(s={"recovering": True})):
            assert not agents.busy()
            state()
            assert agents.busy()
            agents.blocked.clear(), owner.workers.clear(), agents.session_tasks.clear(), owner.sessions.clear()
            agents.unsettled = False

    asyncio.run(scenario())


def test_open_session_alone_is_not_pending_work():
    async def scenario():
        started = []
        owner, agents = recovery(_stopping=asyncio.Event(), _recovery_enabled=lambda: True)
        owner.sessions = {"s": {"scope": {"agent_id": "a"}}}
        agents.retirement = SimpleNamespace(tick=lambda subjects: None)
        async def run(agent_id, recovering):
            started.append(agent_id)
        agents._run = run
        agents._pending_subjects = lambda: {"a"}
        await agents._tick()
        await asyncio.gather(*agents.tasks.values())
        assert started == ["a"] and not agents.unsettled and not agents.busy()
        agents._pending_subjects = lambda: {"a", "retiring"}
        await agents._tick()
        assert agents.unsettled and agents.busy()

    asyncio.run(scenario())


@pytest.mark.parametrize(("events", "faults", "touched"), [(False, [], False), (True, [], True), (False, ["s"], True)])
def test_only_a_publication_or_a_fault_counts_as_work(events, faults, touched):
    async def scenario():
        async def publications(**kwargs):
            return False

        async def recover(stats=None, **kwargs):
            stats["active"] = events  # A lease renewal alone sets it false.
            return True

        owner, agents = recovery(_recover_publications=publications, events=SimpleNamespace(recover=recover),
                                 channel=None)
        owner.sessions = {"s": {}}
        agents._check_stream_health = lambda agent_id, active: faults
        recovered = []
        agents.recover_session = recovered.append
        before = agents.last_active
        await agents._publish("a")
        assert (agents.last_active != before) is touched
        assert recovered == faults

    asyncio.run(scenario())


class Store:
    """A store double with a change probe and a count of scans."""

    def __init__(self):
        self.version, self.scans = 0, 0

    def data_version(self):
        return self.version


def start_pump(monkeypatch, store, *, idle_interval, probe=True):
    monkeypatch.setattr(pumps, "recover_fenced_reservations", lambda **kwargs: None)
    monkeypatch.setattr(pumps, "release_dispatch_owner", lambda **kwargs: None)
    def reserve(**kwargs):
        store.scans += 1
    monkeypatch.setattr(pumps, "reserve_execution_dispatch", reserve)
    factory = store if probe else SimpleNamespace()
    return pumps.ExecutionDispatchPump(factory=factory, channel=SimpleNamespace(server_id="s", executor_id="e", connection_id="c"),
        access=None, fresh_publications={}, send=None, send_lock=None, verify_link=lambda: None,
        close_link=None, poll_interval=.01, idle_interval=idle_interval)


def test_idle_pump_scans_again_only_after_a_commit(monkeypatch):
    async def scenario():
        store = Store()
        pump = start_pump(monkeypatch, store, idle_interval=60)
        pump.start()
        try:
            await until(lambda: store.scans == 1)
            await asyncio.sleep(.3)
            assert store.scans == 1, "An idle pump scanned without a commit"
            store.version += 1
            await until(lambda: store.scans == 2)
            await asyncio.sleep(.1)
            assert store.scans == 2
        finally:
            await pump.stop()

    asyncio.run(scenario())


def test_idle_pump_rescans_when_the_idle_interval_passes(monkeypatch):
    async def scenario():
        store = Store()
        pump = start_pump(monkeypatch, store, idle_interval=.2)
        pump.start()
        try:
            await until(lambda: store.scans >= 3)
        finally:
            await pump.stop()

    asyncio.run(scenario())


def test_pump_without_a_change_probe_scans_every_poll(monkeypatch):
    async def scenario():
        store = Store()
        pump = start_pump(monkeypatch, store, idle_interval=60, probe=False)
        pump.start()
        try:
            await until(lambda: store.scans >= 5)
        finally:
            await pump.stop()

    asyncio.run(scenario())


def scheduler(store, clock, **options):
    reads = []

    @contextmanager
    def unit_of_work():
        yield SimpleNamespace()

    class Repository:
        def wake(self, uow): reads.append("wake")
        def renew(self, uow, lease, **kwargs): reads.append("renew")
        def sweep(self, uow, **kwargs): reads.append("sweep")
        def lease_due(self, uow, **kwargs):
            reads.append("lease_due")
            return ()

    store.unit_of_work = unit_of_work
    return HandoffRuntimeScheduler(factory=store, repository=Repository(), processor=None,
        monotonic=lambda: clock[0], **options), reads


def test_idle_scheduler_reads_the_store_only_after_a_commit_a_wake_or_a_sweep_or_the_idle_interval():
    async def scenario():
        store, clock = Store(), [100.0]
        planner, reads = scheduler(store, clock, sweep_seconds=1000, idle_seconds=10)
        async def plan():
            reads.clear()
            await planner._plan()
            return list(reads)
        assert await plan() == ["sweep", "lease_due"]  # First plan sweeps.
        assert await plan() == []  # Nothing committed, nothing woke it.
        clock[0] += 5
        assert await plan() == []
        store.version += 1
        assert await plan() == ["lease_due"]  # A commit shows.
        assert await plan() == []
        planner.wake()
        assert await plan() == ["wake", "lease_due"]  # A wake shows.
        assert await plan() == []
        clock[0] += 10
        assert await plan() == ["lease_due"]  # Due times need the idle interval.
        clock[0] += 1000
        assert await plan() == ["sweep", "lease_due"]  # A sweep is due.

    asyncio.run(scenario())


def test_scheduler_without_a_change_probe_reads_every_tick():
    async def scenario():
        planner, reads = scheduler(SimpleNamespace(), [100.0], sweep_seconds=1000, idle_seconds=10)
        await planner._plan()
        await planner._plan()
        assert reads == ["sweep", "lease_due", "lease_due"]

    asyncio.run(scenario())
