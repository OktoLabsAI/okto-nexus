"""Idle hub cost (#86): gated stream health, quiet renewals, back-off and lease wake-ups."""
import asyncio
import dataclasses
import logging
import sqlite3
import time
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from okto_nexus.bootstrap import embedded_events
from okto_nexus.bootstrap.embedded_agent_recovery import EmbeddedAgentRecovery, STREAM_FAULT_SQL
from okto_nexus.bootstrap.embedded_dispatch import EmbeddedDispatchOwner, _WakingSessions
from okto_nexus.bootstrap.embedded_events import EmbeddedEventPublisher, Published
from okto_nexus.config import NexusConfig

SERVER, EXECUTOR = "srv", "exe"


@pytest.fixture
def factory(tmp_path):
    factory = ConnectionFactory(NexusConfig(home_dir=tmp_path))
    MigrationRunner(factory).apply()
    return factory


def seed_stream(factory, agent_id, *, error_payload=None, session_id=None):
    """Insert one live stream. Foreign keys are off: only the stream health columns matter."""
    session_id = session_id or "sess-" + agent_id
    conn = sqlite3.connect(factory._config.db_path)
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("INSERT INTO execution_sessions(server_id,executor_id,session_id,binding_id,workspace_id,"
        "workspace_binding_id,open_operation_id,owner_generation,lifecycle_state,stream_epoch,lease_state) "
        "VALUES(?,?,?,?,?,?,?,1,'OPEN','ep','ACTIVE')",
        (SERVER, EXECUTOR, session_id, "b", "w", "wb", "op-" + session_id))
    conn.execute("INSERT INTO execution_local_streams(server_id,executor_id,session_id,stream_epoch,"
        "opening_operation_id,binding_id,agent_id,drained) VALUES(?,?,?,?,?,?,?,0)",
        (SERVER, EXECUTOR, session_id, "ep", "op-" + session_id, "b", agent_id))
    if error_payload is not None:
        conn.execute("INSERT INTO execution_event_ingress(server_id,executor_id,session_id,stream_epoch,sequence,"
            "event_hash,event_type,payload_json,received_at) VALUES(?,?,?,?,1,'h','error',?,'2026-01-01T00:00:00Z')",
            (SERVER, EXECUTOR, session_id, "ep", error_payload))
    conn.commit()
    conn.close()
    return session_id


PUMP_FAILED = ('{"native_type":"core.event_pump_failed","payload":{"code":"EVENT_STREAM_UNAVAILABLE"}}')


def fake_owner(factory, agents, *, recover=None):
    calls = SimpleNamespace(recover=0, publications=0)

    async def recover_publications(agent_id=None, progress=None, **_):
        calls.publications += 1
        return False

    async def events_recover(*, agent_id, stats=None, **_):
        calls.recover += 1
        if recover is not None:
            return await recover(agent_id, stats)
        return False

    owner = SimpleNamespace(
        factory=factory, channel=SimpleNamespace(server_id=SERVER, executor_id=EXECUTOR),
        verify=lambda uow=None: None, _stopping=asyncio.Event(), _activity=asyncio.Event(),
        sessions={a: {"scope": {"agent_id": a}} for a in agents}, active_operations=set(),
        worker_agents={}, workers=set(), idle_interval=10.0, _recovery_enabled=lambda: True,
        _recover_publications=recover_publications, events=SimpleNamespace(recover=events_recover),
        deps=SimpleNamespace(), failure=None)
    return owner, calls


def make_recovery(owner):
    recovery = EmbeddedAgentRecovery(owner)
    recovery.unsettled = False
    recovery.retirement = SimpleNamespace(tick=lambda subjects: None, close=lambda: asyncio.sleep(0))
    return recovery


async def run_tick(recovery):
    await recovery.tick()
    await asyncio.gather(*list(recovery.tasks.values()))


def test_stream_health_plan_uses_the_error_index_and_no_plain_ingress_search(factory):
    with factory.unit_of_work(write=False) as uow:
        plan = [row[3] for row in uow.connection.execute("EXPLAIN QUERY PLAN " + STREAM_FAULT_SQL,
                                                          (SERVER, EXECUTOR, "agent"))]
    text = "\n".join(plan)
    assert "idx_event_ingress_error" in text, text
    assert "sqlite_autoindex_execution_event_ingress" not in text, text
    assert not any("execution_event_ingress" in line and "(server_id=? AND executor_id=?)" in line
                   for line in plan), text


def test_idle_agents_do_one_stream_check_each_and_back_off_afterwards(factory):
    agents = [f"agent{i}" for i in range(7)]
    for agent in agents:
        seed_stream(factory, agent)
    owner, calls = fake_owner(factory, agents)

    async def scenario():
        recovery = make_recovery(owner)
        await run_tick(recovery)
        first = factory.unit_counts()[0]
        for _ in range(49):
            await run_tick(recovery)
        return recovery, factory.unit_counts()[0] - first

    recovery, later_reads = asyncio.run(scenario())
    assert recovery.counters["stream_checks"] == 7
    assert calls.recover == 7
    # Per tick, the host reads once for its subjects. No agent reads again while it is quiet.
    assert later_reads <= 49 * 1


def test_error_batch_triggers_a_check_and_the_session_recovers_within_one_tick(factory):
    session_id = seed_stream(factory, "agent", error_payload=PUMP_FAILED)
    state = {"error": False}

    async def recover(agent_id, stats):
        if state["error"]:
            stats["error_seen"] = True
            stats["active"] = True
            state["error"] = False
            return True
        return False

    owner, _ = fake_owner(factory, ["agent"], recover=recover)
    # The pump failure event was stored but the safety net has just run: the batch flag must start the check.
    owner.sessions = {session_id: {"scope": {"agent_id": "agent"}}}
    recovered = []

    async def scenario():
        recovery = make_recovery(owner)
        recovery.recover_session = lambda sid, **kw: recovered.append(sid)
        recovery.health_due_at["agent"] = time.monotonic() + 60
        await run_tick(recovery)
        assert recovered == []
        state["error"] = True
        recovery.next_due_at.clear()
        await run_tick(recovery)
        return recovery

    recovery = asyncio.run(scenario())
    assert recovered == [session_id]
    assert owner.sessions[session_id]["recovery_reason"] == "EVENT_STREAM_UNAVAILABLE"


def test_boot_scan_finds_a_stored_error_event_after_a_restart(factory):
    session_id = seed_stream(factory, "agent", error_payload=PUMP_FAILED)
    owner, _ = fake_owner(factory, ["agent"])
    owner.sessions = {session_id: {"scope": {"agent_id": "agent"}}}
    recovered = []

    async def scenario():
        recovery = make_recovery(owner)  # A new process has no health_due_at entry.
        recovery.recover_session = lambda sid, **kw: recovered.append(sid)
        await run_tick(recovery)

    asyncio.run(scenario())
    assert recovered == [session_id]


def test_lease_renewal_batches_leave_the_host_idle(factory):
    async def recover(agent_id, stats):
        stats["active"] = False
        return True

    owner, _ = fake_owner(factory, ["agent"], recover=recover)

    async def scenario():
        recovery = make_recovery(owner)
        recovery.busy_linger = 0.05
        await run_tick(recovery)
        await asyncio.sleep(.1)
        return recovery

    recovery = asyncio.run(scenario())
    assert not recovery.busy()
    assert "agent" in recovery.next_due_at


def test_new_work_wakes_a_backed_off_agent_at_once(factory):
    owner, calls = fake_owner(factory, ["agent"])

    async def scenario():
        recovery = make_recovery(owner)
        await run_tick(recovery)
        await run_tick(recovery)
        assert calls.recover == 1
        recovery.touch()
        await run_tick(recovery)
        assert calls.recover == 2
        assert owner._activity.is_set()

    asyncio.run(scenario())


@dataclasses.dataclass
class FakeEvent:
    sequence: int
    category: str
    native_type: str
    operation_id: object = None
    payload: dict = dataclasses.field(default_factory=dict)


class FakeJournal:
    def __init__(self, events):
        self.pending = events
        self.acks = []

    async def acknowledge_events(self, cursor, sequence):
        self.acks.append(sequence)

    async def events(self, cursor):
        for event in self.pending:
            yield event


def publisher_for(journal, monkeypatch, *, committed=0):
    owner = SimpleNamespace(
        channel=SimpleNamespace(server_id=SERVER, executor_id=EXECUTOR, connection_id="c", connection_generation=1),
        factory=SimpleNamespace(unit_of_work=None), verify=lambda uow=None: None,
        deps=SimpleNamespace(approvals=None, runtime_dispatcher=None), after=0)

    async def with_history(*, executor_id, session_id, read):
        return await read(journal)

    owner.host = SimpleNamespace(with_history=with_history)
    publisher = EmbeddedEventPublisher(owner)
    publisher._watermark = lambda scope: committed
    monkeypatch.setattr(embedded_events, "commit_execution_events",
                        lambda factory, **kw: {"sequence": kw["frame"]["events"][-1]["sequence"]})
    return publisher


SCOPE = {"server_id": SERVER, "executor_id": EXECUTOR, "binding_id": "b", "agent_id": "agent",
         "session_id": "s", "stream_epoch": "ep"}


@pytest.mark.parametrize("kinds, active, error", [
    ([("lifecycle", "core.lease_renewed")], False, False),
    ([("lifecycle", "core.lease_renewed"), ("output", "text")], True, False),
    ([("error", "core.event_pump_failed")], True, True),
])
def test_step_reports_active_and_error_seen(monkeypatch, kinds, active, error):
    events = [FakeEvent(i + 1, category, native) for i, (category, native) in enumerate(kinds)]
    publisher = publisher_for(FakeJournal(events), monkeypatch)
    result = asyncio.run(publisher.step(SCOPE))
    assert isinstance(result, Published) and result
    assert (result.active, result.error_seen) == (active, error)


def test_step_skips_the_empty_ack_it_already_sent(monkeypatch):
    journal = FakeJournal([])
    publisher = publisher_for(journal, monkeypatch, committed=4)
    assert asyncio.run(publisher.step(SCOPE)) is False
    assert journal.acks == [4]
    assert asyncio.run(publisher.step(SCOPE)) is False
    assert journal.acks == [4]
    # A moved watermark is sent again.
    publisher._watermark = lambda scope: 7
    asyncio.run(publisher.step(SCOPE))
    assert journal.acks == [4, 7]


def test_lease_loop_wakes_rarely_for_idle_sessions():
    scans = []

    class Sessions(_WakingSessions):
        def items(self):
            scans.append(time.monotonic())
            return super().items()

    async def scenario():
        owner = SimpleNamespace(
            _stopping=asyncio.Event(), _lease_wake=asyncio.Event(), failure=None,
            agents=SimpleNamespace(blocked=set()), lease_wait_cap=EmbeddedDispatchOwner.lease_wait_cap)
        owner.sessions = Sessions(owner._lease_wake)
        for index in range(3):
            owner.sessions[f"s{index}"] = {"scope": {"agent_id": "a"}, "renew_at": time.monotonic() + 100}
        task = asyncio.create_task(EmbeddedDispatchOwner._maintain_leases(owner))
        await asyncio.sleep(10)
        owner._stopping.set()
        await task
        return owner

    asyncio.run(scenario())
    assert len(scans) <= 4, scans


def test_lease_loop_renews_a_due_session_and_wakes_for_a_new_one():
    renewed = []

    async def scenario():
        owner = SimpleNamespace(
            _stopping=asyncio.Event(), _lease_wake=asyncio.Event(), failure=None,
            agents=SimpleNamespace(blocked=set()), lease_wait_cap=5.0, renewals=set())
        owner.sessions = _WakingSessions(owner._lease_wake)

        async def renew(session_id, session):
            renewed.append(session_id)
            session["renew_at"] = time.monotonic() + 100
            owner._lease_wake.set()
        owner._renew_owned = renew
        task = asyncio.create_task(EmbeddedDispatchOwner._maintain_leases(owner))
        await asyncio.sleep(.05)
        started = time.monotonic()
        owner.sessions["late"] = {"scope": {"agent_id": "a"}, "renew_at": started + .2}
        while "late" not in renewed:
            await asyncio.sleep(.01)
            assert time.monotonic() - started < 2
        owner._stopping.set()
        await task
        return time.monotonic() - started

    elapsed = asyncio.run(scenario())
    assert .15 < elapsed < 1.0


def test_renewal_jitter_stays_inside_the_half_life_margin():
    class Executor:
        lease_request_started = time.monotonic()
    owner = SimpleNamespace(_lease_wake=asyncio.Event())
    values = set()
    for _ in range(50):
        session = {"executor": Executor()}
        applied = SimpleNamespace(context=SimpleNamespace(lease_deadline_monotonic=time.monotonic() + 100))
        EmbeddedDispatchOwner._schedule_renewal(owner, session, applied)
        values.add(round(session["renew_at"] - time.monotonic()))
        assert 44 <= session["renew_at"] - time.monotonic() <= 56
    assert len(values) > 1
    assert owner._lease_wake.is_set()


def test_counters_log_one_line_when_a_counter_moved(factory, caplog):
    owner, _ = fake_owner(factory, ["agent"])

    async def scenario():
        recovery = make_recovery(owner)
        recovery.counter_interval = 0.0
        recovery._counter_log_at = 0.0
        await run_tick(recovery)
        await run_tick(recovery)

    with caplog.at_level(logging.INFO, logger="okto_nexus.bootstrap.embedded_agent_recovery"):
        asyncio.run(scenario())
    lines = [r.getMessage() for r in caplog.records if "runtime idle counters" in r.getMessage()]
    assert lines and all("stream_checks=" in line and "read_units=" in line for line in lines)
