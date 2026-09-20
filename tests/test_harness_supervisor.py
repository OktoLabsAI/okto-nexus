"""Phase 3.5 (harness-integrations) - the supervisor (ADR 0004 D1/D3/D8/D10).

Uses a FAKE connector (:class:`FakeConnector` below) throughout - driving a
real harness binary is Phase 4's job, not this one's. The fake is capable of
FAILING in the two ways D8 calls out explicitly: wedging (``start()`` never
returns) and dying/erroring (``events()`` raises), because failure isolation
is the entire point of this test file.

Covers, at minimum (per the Phase 3.5 task):
* supervisor lifecycle (open -> live -> close; open_declared boot path)
* failure isolation (a connector that fails to start, and one that wedges,
  never affect another already-open session or the supervisor itself)
* event fan-out ordering (in-memory publish happens BEFORE, and is never
  gated by, the durable DB write)
* D3 agent registration; D10 notable-event message delivery; capability
  gating on send/steer.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any

import pytest

from okto_nexus.adapters.outbound.harness.subscribers import (
    InMemoryHarnessSubscriberRegistry,
)
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.events_repo import (
    SqliteEventEmitter,
    SqliteEventRepo,
)
from okto_nexus.adapters.outbound.sqlite.harness_repo import (
    SqliteHarnessEventRepo,
    SqliteHarnessSessionRepo,
)
from okto_nexus.adapters.outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteSessionRepo,
    SqliteWorkspaceRepo,
)
from okto_nexus.adapters.outbound.sqlite.messages_repo import (
    SqliteChannelRepo,
    SqliteMessageDeliveryRepo,
    SqliteMessageRepo,
)
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from okto_nexus.application.harness_supervisor import (
    HarnessBootSpec,
    HarnessSupervisor,
)
from okto_nexus.application.messages import MessageService
from okto_nexus.config import NexusConfig
from okto_nexus.domain.base import utc_now_iso
from okto_nexus.domain.harness import (
    STATUS_ENDED,
    STATUS_ERRORED,
    STATUS_RUNNING,
    STATUS_STARTING,
    STEER_TIMING_NEXT_TURN_BOUNDARY,
    HarnessCapabilities,
    HarnessEvent,
    HarnessSession,
    new_harness_session_id,
)
from okto_nexus.errors import ErrorCode, OktoNexusError


# --------------------------------------------------------------------------- #
# Test double: FakeConnector
# --------------------------------------------------------------------------- #
class FakeConnector:
    """A stand-in :class:`~okto_nexus.application.ports.HarnessConnector`.

    Behaviour is entirely driven by the constructor flags / helper methods so
    each test builds exactly the failure shape it needs:

    * ``wedge_start=True`` -> :meth:`start` blocks FOREVER (never returns),
      simulating D8's "looks alive, delivers nothing" at boot time.
    * ``start_error=<exc>`` -> :meth:`start` raises immediately.
    * full-duplex (``capabilities.send_only=False``): :meth:`events` is a
      BLOCKING generator fed by :meth:`push_event`/:meth:`crash`/:meth:`end`,
      matching pi/codex/claude_code_stream's real shape.
    * send-only (``capabilities.send_only=True``): :meth:`events` returns a
      FINITE snapshot (whatever is queued right now), matching
      ``ClaudeCodeAttachConnector``'s real shape.
    """

    _RAISE = object()
    _STOP = object()

    def __init__(
        self,
        *,
        kind: str = "pi",
        capabilities: HarnessCapabilities | None = None,
        wedge_start: bool = False,
        wedge_close: bool = False,
        start_error: BaseException | None = None,
    ) -> None:
        self.capabilities = capabilities or HarnessCapabilities(
            send_only=False,
            steer_timing=STEER_TIMING_NEXT_TURN_BOUNDARY,
            interrupt_requires_settle_wait=False,
            multiplexes_sessions=False,
            observes_session_end=True,
        )
        self._kind = kind
        self._wedge_start = wedge_start
        self._wedge_close = wedge_close
        self._start_error = start_error
        self._queue: "queue.Queue[Any]" = queue.Queue()
        self._never = threading.Event()  # used only to wedge start() forever
        self._never_close = threading.Event()  # used only to wedge close() forever
        self.session: HarnessSession | None = None
        self.sent_commands: list[Any] = []
        self.close_called = False

    def start(self, *, owning_agent_id: str) -> HarnessSession:
        if self._wedge_start:
            self._never.wait()  # never set -> blocks forever, by design
        if self._start_error is not None:
            raise self._start_error
        session_id = new_harness_session_id()
        self.session = HarnessSession(
            session_id=session_id,
            harness_kind=self._kind,
            owning_agent_id=owning_agent_id,
            status=STATUS_STARTING,
            capabilities=self.capabilities,
            started_at=utc_now_iso(),
        )
        return self.session

    def send(self, session: HarnessSession, command: Any) -> None:
        self.sent_commands.append(command)

    def events(self):
        if self.capabilities.send_only:
            drained = []
            while True:
                try:
                    drained.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            return iter([e for e in drained if e not in (self._RAISE, self._STOP)])
        return self._pump_forever()

    def _pump_forever(self):
        while True:
            item = self._queue.get()
            if item is self._RAISE:
                raise RuntimeError("fake connector crashed")
            if item is self._STOP:
                return
            yield item

    def push_event(self, event: HarnessEvent) -> None:
        self._queue.put(event)

    def crash(self) -> None:
        self._queue.put(self._RAISE)

    def end(self) -> None:
        self._queue.put(self._STOP)

    def close(self) -> None:
        if self._wedge_close:
            self._never_close.wait()  # never set -> blocks forever, by design
        self.close_called = True
        self.end()


def make_event(
    session_id: str, *, kind: str = "output_delta", native_event: str = "native/x", **kw
) -> HarnessEvent:
    return HarnessEvent(
        session_id=session_id,
        harness_kind="pi",
        kind=kind,
        native_event=native_event,
        occurred_at=utc_now_iso(),
        **kw,
    )


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def make_factory(tmp_path, name: str = "home") -> ConnectionFactory:
    f = ConnectionFactory(NexusConfig(home_dir=tmp_path / name))
    MigrationRunner(f).apply()
    return f


class _Clock:
    def now_iso(self) -> str:
        return utc_now_iso()

    def now_epoch(self) -> float:
        return time.time()


def make_message_service(factory, clock) -> MessageService:
    events_repo = SqliteEventRepo(clock)
    return MessageService(
        connection_factory=factory,
        channels=SqliteChannelRepo(clock),
        messages=SqliteMessageRepo(clock),
        workspaces=SqliteWorkspaceRepo(clock),
        agents=SqliteAgentRepo(clock),
        sessions=SqliteSessionRepo(clock),
        deliveries=SqliteMessageDeliveryRepo(clock),
        event_emitter=SqliteEventEmitter(events_repo),
        clock=clock,
        max_inline_bytes=65536,
    )


def make_supervisor(
    factory, clock, *, messages=None, start_timeout_s=5.0, close_timeout_s=5.0
) -> HarnessSupervisor:
    return HarnessSupervisor(
        connection_factory=factory,
        clock=clock,
        agents=SqliteAgentRepo(clock),
        sessions=SqliteHarnessSessionRepo(clock),
        events=SqliteHarnessEventRepo(clock),
        subscribers=InMemoryHarnessSubscriberRegistry(),
        messages=messages,
        start_timeout_s=start_timeout_s,
        close_timeout_s=close_timeout_s,
    )


def mkproj(tmp_path, name="proj") -> str:
    p = tmp_path / name
    p.mkdir(exist_ok=True)
    return str(p)


def wait_until(predicate, *, timeout_s: float = 5.0, interval_s: float = 0.01) -> bool:
    """Test-only bounded poll (NOT part of the harness path itself - this is
    test synchronisation for a background thread, exactly like the rest of
    this repo's test suite uses short sleeps to await async effects)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval_s)
    return predicate()


# --------------------------------------------------------------------------- #
# open() / lifecycle
# --------------------------------------------------------------------------- #
def test_open_registers_agent_and_marks_session_running(tmp_path):
    factory = make_factory(tmp_path)
    clock = _Clock()
    supervisor = make_supervisor(factory, clock)
    connector = FakeConnector()

    session = supervisor.open(
        kind="pi",
        connector=connector,
        owning_agent_id="harness-pi-1",
        project_root=mkproj(tmp_path),
    )

    assert session.status == STATUS_RUNNING
    assert supervisor.get(session.session_id) is session

    with factory.unit_of_work() as uow:
        agent = SqliteAgentRepo(clock).get(uow, "harness-pi-1")
    assert agent is not None
    assert agent.metadata.get("harness_kind") == "pi"

    with factory.unit_of_work() as uow:
        row = SqliteHarnessSessionRepo(clock).get(uow, session_id=session.session_id)
    assert row is not None
    assert row.status == STATUS_RUNNING


def test_open_rejects_a_connector_that_fails_to_start(tmp_path):
    factory = make_factory(tmp_path)
    clock = _Clock()
    supervisor = make_supervisor(factory, clock)
    connector = FakeConnector(start_error=RuntimeError("boom"))

    with pytest.raises(OktoNexusError) as excinfo:
        supervisor.open(
            kind="pi",
            connector=connector,
            owning_agent_id="harness-broken",
            project_root=mkproj(tmp_path),
        )
    assert excinfo.value.code == ErrorCode.INTERNAL_ERROR
    assert supervisor.list_live() == []


def test_open_bounded_by_start_timeout_when_connector_wedges(tmp_path):
    factory = make_factory(tmp_path)
    clock = _Clock()
    supervisor = make_supervisor(factory, clock, start_timeout_s=0.3)
    connector = FakeConnector(wedge_start=True)

    started = time.monotonic()
    with pytest.raises(OktoNexusError) as excinfo:
        supervisor.open(
            kind="pi",
            connector=connector,
            owning_agent_id="harness-wedged",
            project_root=mkproj(tmp_path),
        )
    elapsed = time.monotonic() - started
    assert excinfo.value.code == ErrorCode.INTERNAL_ERROR
    # Bounded: must return close to the configured timeout, never hang.
    assert elapsed < 2.0
    assert supervisor.list_live() == []


def test_failed_and_wedged_opens_never_affect_an_already_open_session(tmp_path):
    factory = make_factory(tmp_path)
    clock = _Clock()
    supervisor = make_supervisor(factory, clock, start_timeout_s=0.3)

    good = FakeConnector()
    good_session = supervisor.open(
        kind="pi",
        connector=good,
        owning_agent_id="harness-good",
        project_root=mkproj(tmp_path),
    )

    with pytest.raises(OktoNexusError):
        supervisor.open(
            kind="codex",
            connector=FakeConnector(start_error=RuntimeError("boom")),
            owning_agent_id="harness-broken",
            project_root=mkproj(tmp_path, "proj2"),
        )
    with pytest.raises(OktoNexusError):
        supervisor.open(
            kind="codex",
            connector=FakeConnector(wedge_start=True),
            owning_agent_id="harness-wedged",
            project_root=mkproj(tmp_path, "proj3"),
        )

    # The good session is untouched by either failure.
    assert supervisor.get(good_session.session_id) is not None
    assert [s.session_id for s in supervisor.list_live()] == [good_session.session_id]

    # And it still pumps events normally afterward.
    event = make_event(good_session.session_id)
    good.push_event(event)
    assert wait_until(
        lambda: len(supervisor.replay_events(good_session.session_id)) == 1
    )


def test_open_declared_isolates_boot_time_failures(tmp_path):
    factory = make_factory(tmp_path)
    clock = _Clock()
    supervisor = make_supervisor(factory, clock, start_timeout_s=0.3)

    good = FakeConnector()
    specs = [
        HarnessBootSpec(
            kind="pi",
            connector=good,
            owning_agent_id="boot-good",
            project_root=mkproj(tmp_path, "boot-good"),
        ),
        HarnessBootSpec(
            kind="codex",
            connector=FakeConnector(start_error=RuntimeError("boom")),
            owning_agent_id="boot-broken",
            project_root=mkproj(tmp_path, "boot-broken"),
        ),
        HarnessBootSpec(
            kind="codex",
            connector=FakeConnector(wedge_start=True),
            owning_agent_id="boot-wedged",
            project_root=mkproj(tmp_path, "boot-wedged"),
        ),
    ]

    results = supervisor.open_declared(specs)  # must never raise

    assert len(results) == 3
    assert results[0].session is not None and results[0].error is None
    assert results[1].session is None and isinstance(results[1].error, OktoNexusError)
    assert results[2].session is None and isinstance(results[2].error, OktoNexusError)
    assert [s.session_id for s in supervisor.list_live()] == [results[0].session.session_id]


# --------------------------------------------------------------------------- #
# Event fan-out ordering (in-memory publish is never gated by the DB write)
# --------------------------------------------------------------------------- #
class _OrderCheckingRegistry:
    """Records, for each publish, how many rows THIS event's session already
    has durably persisted at the moment publish() runs. If publish always
    happens before persistence, that count is 0 for every event the FIRST
    time it is published (each event is only ever published once)."""

    def __init__(self, factory, clock) -> None:
        self._factory = factory
        self._events_repo = SqliteHarnessEventRepo(clock)
        self.rows_persisted_at_publish_time: list[int] = []

    def subscribe(self, session_id, callback):
        return None

    def unsubscribe(self, handle):
        pass

    def publish(self, event: HarnessEvent) -> None:
        with self._factory.unit_of_work(write=False) as uow:
            rows = self._events_repo.list_for_session(uow, session_id=event.session_id)
        self.rows_persisted_at_publish_time.append(len(rows))


def test_publish_happens_before_the_durable_write_for_every_event(tmp_path):
    factory = make_factory(tmp_path)
    clock = _Clock()
    registry = _OrderCheckingRegistry(factory, clock)
    supervisor = HarnessSupervisor(
        connection_factory=factory,
        clock=clock,
        agents=SqliteAgentRepo(clock),
        sessions=SqliteHarnessSessionRepo(clock),
        events=SqliteHarnessEventRepo(clock),
        subscribers=registry,
    )
    connector = FakeConnector()
    session = supervisor.open(
        kind="pi",
        connector=connector,
        owning_agent_id="harness-order",
        project_root=mkproj(tmp_path),
    )

    for i in range(3):
        connector.push_event(make_event(session.session_id, native_event=f"native/{i}"))

    assert wait_until(lambda: len(registry.rows_persisted_at_publish_time) == 3)
    # Event i's publish() sees exactly i rows already persisted (the PRIOR
    # events, never itself): if persistence ever ran BEFORE publish for a
    # given event, that event's own count would be i+1, not i. [0, 1, 2] is
    # the proof that publish precedes persistence for every single event,
    # every time - never the other way round.
    assert registry.rows_persisted_at_publish_time == [0, 1, 2]
    # ... and all three DID eventually land durably.
    assert wait_until(lambda: len(supervisor.replay_events(session.session_id)) == 3)


def test_a_broken_subscriber_registry_does_not_stop_persistence(tmp_path):
    factory = make_factory(tmp_path)
    clock = _Clock()

    class _ExplodingRegistry:
        def subscribe(self, session_id, callback):
            return None

        def unsubscribe(self, handle):
            pass

        def publish(self, event):
            raise RuntimeError("subscriber registry is broken")

    supervisor = HarnessSupervisor(
        connection_factory=factory,
        clock=clock,
        agents=SqliteAgentRepo(clock),
        sessions=SqliteHarnessSessionRepo(clock),
        events=SqliteHarnessEventRepo(clock),
        subscribers=_ExplodingRegistry(),
    )
    connector = FakeConnector()
    session = supervisor.open(
        kind="pi",
        connector=connector,
        owning_agent_id="harness-explode",
        project_root=mkproj(tmp_path),
    )
    connector.push_event(make_event(session.session_id))

    assert wait_until(lambda: len(supervisor.replay_events(session.session_id)) == 1)
    # The session is still live - a broken registry never reaped it.
    assert supervisor.get(session.session_id) is not None


# --------------------------------------------------------------------------- #
# Reaping on child death (observing vs non-observing connectors)
# --------------------------------------------------------------------------- #
def test_connector_crash_reaps_session_as_errored(tmp_path):
    factory = make_factory(tmp_path)
    clock = _Clock()
    supervisor = make_supervisor(factory, clock)
    connector = FakeConnector()
    session = supervisor.open(
        kind="pi",
        connector=connector,
        owning_agent_id="harness-crash",
        project_root=mkproj(tmp_path),
    )
    connector.crash()

    assert wait_until(lambda: supervisor.get(session.session_id) is None)
    with factory.unit_of_work() as uow:
        row = SqliteHarnessSessionRepo(clock).get(uow, session_id=session.session_id)
    assert row.status == STATUS_ERRORED
    assert row.ended_at is not None


def test_connector_natural_end_reaps_session_as_ended(tmp_path):
    factory = make_factory(tmp_path)
    clock = _Clock()
    supervisor = make_supervisor(factory, clock)
    connector = FakeConnector()
    session = supervisor.open(
        kind="pi",
        connector=connector,
        owning_agent_id="harness-natural-end",
        project_root=mkproj(tmp_path),
    )
    connector.end()

    assert wait_until(lambda: supervisor.get(session.session_id) is None)
    with factory.unit_of_work() as uow:
        row = SqliteHarnessSessionRepo(clock).get(uow, session_id=session.session_id)
    assert row.status == STATUS_ENDED


def test_non_observing_connector_death_is_never_fabricated_as_ended(tmp_path):
    """D7b/cc-socks shape: observes_session_end=False. Reaping must remove the
    session from the LIVE registry (Nexus stops tracking it) WITHOUT writing
    a terminal status the connector never actually observed."""
    factory = make_factory(tmp_path)
    clock = _Clock()
    supervisor = make_supervisor(factory, clock)
    caps = HarnessCapabilities(
        send_only=True,
        steer_timing=None,
        interrupt_requires_settle_wait=False,
        multiplexes_sessions=False,
        observes_session_end=False,
    )
    connector = FakeConnector(kind="claude_code", capabilities=caps)
    session = supervisor.open(
        kind="claude_code",
        connector=connector,
        owning_agent_id="harness-attach",
        project_root=mkproj(tmp_path),
    )
    assert session.status == STATUS_RUNNING

    supervisor.close(session.session_id)

    assert supervisor.get(session.session_id) is None
    with factory.unit_of_work() as uow:
        row = SqliteHarnessSessionRepo(clock).get(uow, session_id=session.session_id)
    # Never fabricated ENDED/ERRORED - status is whatever open() persisted.
    assert row.status == STATUS_RUNNING
    assert row.ended_at is None


# --------------------------------------------------------------------------- #
# close()
# --------------------------------------------------------------------------- #
def test_close_sends_end_and_persists_ended(tmp_path):
    factory = make_factory(tmp_path)
    clock = _Clock()
    supervisor = make_supervisor(factory, clock)
    connector = FakeConnector()
    session = supervisor.open(
        kind="pi",
        connector=connector,
        owning_agent_id="harness-close",
        project_root=mkproj(tmp_path),
    )

    returned = supervisor.close(session.session_id)

    assert returned.session_id == session.session_id
    assert any(c.verb == "end" for c in connector.sent_commands)
    assert connector.close_called is True
    assert supervisor.get(session.session_id) is None
    with factory.unit_of_work() as uow:
        row = SqliteHarnessSessionRepo(clock).get(uow, session_id=session.session_id)
    assert row.status == STATUS_ENDED


def test_close_unknown_session_raises_not_found(tmp_path):
    factory = make_factory(tmp_path)
    clock = _Clock()
    supervisor = make_supervisor(factory, clock)
    with pytest.raises(OktoNexusError) as excinfo:
        supervisor.close("hsess_does_not_exist")
    assert excinfo.value.code == ErrorCode.NOT_FOUND


def test_close_bounded_by_close_timeout_when_connector_close_wedges(tmp_path):
    """D8: EVERY supervisor-side wait is bounded, including the ones inside
    ``close()`` (:meth:`_bounded_call`), not only ``open()``'s. A connector
    whose own ``close()`` lifecycle helper wedges must still let this
    supervisor's ``close()`` return promptly - AND the terminal status must
    still land, proving teardown-before-finish does not make the durable
    write hostage to a stuck connector."""
    factory = make_factory(tmp_path)
    clock = _Clock()
    supervisor = make_supervisor(factory, clock, close_timeout_s=0.3)
    connector = FakeConnector(wedge_close=True)
    session = supervisor.open(
        kind="pi",
        connector=connector,
        owning_agent_id="harness-close-wedge",
        project_root=mkproj(tmp_path),
    )

    started = time.monotonic()
    returned = supervisor.close(session.session_id)
    elapsed = time.monotonic() - started

    assert elapsed < 2.0
    assert returned.session_id == session.session_id
    assert supervisor.get(session.session_id) is None
    with factory.unit_of_work() as uow:
        row = SqliteHarnessSessionRepo(clock).get(uow, session_id=session.session_id)
    assert row.status == STATUS_ENDED


# --------------------------------------------------------------------------- #
# send() capability gating
# --------------------------------------------------------------------------- #
def test_send_rejects_steer_when_unsupported(tmp_path):
    factory = make_factory(tmp_path)
    clock = _Clock()
    supervisor = make_supervisor(factory, clock)
    caps = HarnessCapabilities(
        send_only=False,
        steer_timing=None,
        interrupt_requires_settle_wait=False,
        multiplexes_sessions=False,
        observes_session_end=True,
    )
    connector = FakeConnector(capabilities=caps)
    session = supervisor.open(
        kind="pi",
        connector=connector,
        owning_agent_id="harness-nosteer",
        project_root=mkproj(tmp_path),
    )

    with pytest.raises(OktoNexusError) as excinfo:
        supervisor.send(session.session_id, "steer", {"content": "x"})
    assert excinfo.value.code == ErrorCode.VALIDATION_ERROR
    assert connector.sent_commands == []


def test_send_only_connector_rejects_everything_but_send_turn(tmp_path):
    factory = make_factory(tmp_path)
    clock = _Clock()
    supervisor = make_supervisor(factory, clock)
    caps = HarnessCapabilities(
        send_only=True,
        steer_timing=None,
        interrupt_requires_settle_wait=False,
        multiplexes_sessions=False,
        observes_session_end=False,
    )
    connector = FakeConnector(kind="claude_code", capabilities=caps)
    session = supervisor.open(
        kind="claude_code",
        connector=connector,
        owning_agent_id="harness-sendonly",
        project_root=mkproj(tmp_path),
    )

    with pytest.raises(OktoNexusError) as excinfo:
        supervisor.send(session.session_id, "interrupt")
    assert excinfo.value.code == ErrorCode.VALIDATION_ERROR

    supervisor.send(session.session_id, "send_turn", {"content": "hi"})
    assert len(connector.sent_commands) == 1
    assert connector.sent_commands[0].verb == "send_turn"


def test_send_unknown_session_raises_not_found(tmp_path):
    factory = make_factory(tmp_path)
    clock = _Clock()
    supervisor = make_supervisor(factory, clock)
    with pytest.raises(OktoNexusError) as excinfo:
        supervisor.send("hsess_missing", "send_turn", {})
    assert excinfo.value.code == ErrorCode.NOT_FOUND


def test_send_only_connector_drains_its_finite_events_synchronously(tmp_path):
    """cc-socks-shaped: events() is a snapshot, never a blocking pump, so no
    background thread is spawned; a synchronous error queued by send() must
    still reach the durable event log through send() itself."""
    factory = make_factory(tmp_path)
    clock = _Clock()
    supervisor = make_supervisor(factory, clock)
    caps = HarnessCapabilities(
        send_only=True,
        steer_timing=None,
        interrupt_requires_settle_wait=False,
        multiplexes_sessions=False,
        observes_session_end=False,
    )
    connector = FakeConnector(kind="claude_code", capabilities=caps)
    session = supervisor.open(
        kind="claude_code",
        connector=connector,
        owning_agent_id="harness-drain",
        project_root=mkproj(tmp_path),
    )

    def _send_with_synchronous_error(sess, command):
        connector.sent_commands.append(command)
        connector.push_event(
            make_event(session.session_id, kind="error", native_event="send_failed")
        )

    connector.send = _send_with_synchronous_error  # type: ignore[method-assign]
    supervisor.send(session.session_id, "send_turn", {"content": "hi"})

    events = supervisor.replay_events(session.session_id)
    assert len(events) == 1
    assert events[0].kind == "error"


class BroadcastSendOnlyConnector:
    """cc-socks-shaped, matching ``ClaudeCodeAttachConnector`` AFTER its
    RES-A2 fan-out fix: ``events()`` returns a SNAPSHOT of an append-only
    history, never a destructive drain. Every call returns every event
    recorded so far, including ones already handled by an earlier call -
    this is the exact shape ``HarnessSupervisor.send`` must now cope with."""

    def __init__(self, *, kind: str = "claude_code") -> None:
        self.capabilities = HarnessCapabilities(
            send_only=True,
            steer_timing=None,
            interrupt_requires_settle_wait=False,
            multiplexes_sessions=False,
            observes_session_end=False,
        )
        self._kind = kind
        self._history: list[Any] = []
        self.sent_commands: list[Any] = []
        self.session: HarnessSession | None = None

    def start(self, *, owning_agent_id: str) -> HarnessSession:
        session_id = new_harness_session_id()
        self.session = HarnessSession(
            session_id=session_id,
            harness_kind=self._kind,
            owning_agent_id=owning_agent_id,
            status=STATUS_STARTING,
            capabilities=self.capabilities,
            started_at=utc_now_iso(),
        )
        return self.session

    def send(self, session: HarnessSession, command: Any) -> None:
        self.sent_commands.append(command)
        assert self.session is not None
        self._history.append(
            make_event(self.session.session_id, kind="turn_completed", native_event="agent_settled")
        )

    def events(self):
        # Broadcast snapshot, never a drain - mirrors the real connector.
        return iter(list(self._history))


def test_send_only_connector_delivers_each_event_exactly_once_across_multiple_sends(tmp_path):
    """RES-A2 follow-up regression: ``ClaudeCodeAttachConnector.events()`` is
    now a broadcast snapshot of an append-only history rather than a
    destructive drain (fixing a real fan-out defect where two concurrent
    consumers used to split the stream). The supervisor's send_only branch
    must therefore track its own cursor so that after N sends, event #1 is
    NOT re-handled N times - each event is published/persisted/notified
    exactly once, no matter how many times send() is called on the session."""
    factory = make_factory(tmp_path)
    clock = _Clock()
    with factory.unit_of_work() as uow:
        SqliteAgentRepo(clock).upsert(uow, agent_id="watcher")
    messages = make_message_service(factory, clock)
    supervisor = make_supervisor(factory, clock, messages=messages)
    connector = BroadcastSendOnlyConnector()
    session = supervisor.open(
        kind="claude_code",
        connector=connector,
        owning_agent_id="harness-exactly-once",
        project_root=mkproj(tmp_path),
        notify_target={"strategy": "direct", "agent_id": "watcher"},
    )

    published: list[Any] = []
    supervisor._subscribers.subscribe(  # type: ignore[attr-defined]
        session.session_id, lambda event: published.append(event)
    )

    for _ in range(3):
        supervisor.send(session.session_id, "send_turn", {"content": "hi"})

    persisted = supervisor.replay_events(session.session_id)
    assert len(persisted) == 3, f"expected 3 persisted events after 3 sends, got {len(persisted)}"
    assert len(published) == 3, f"expected 3 published events after 3 sends, got {len(published)}"


# --------------------------------------------------------------------------- #
# D10: notable events also delivered as messages through the existing inbox
# --------------------------------------------------------------------------- #
def test_turn_completed_is_delivered_as_a_direct_message(tmp_path):
    factory = make_factory(tmp_path)
    clock = _Clock()
    messages = make_message_service(factory, clock)
    with factory.unit_of_work() as uow:
        SqliteAgentRepo(clock).upsert(uow, agent_id="watcher")
    supervisor = make_supervisor(factory, clock, messages=messages)
    connector = FakeConnector()
    project = mkproj(tmp_path)
    session = supervisor.open(
        kind="pi",
        connector=connector,
        owning_agent_id="harness-notable",
        project_root=project,
        notify_target={"strategy": "direct", "agent_id": "watcher"},
    )

    connector.push_event(
        make_event(session.session_id, kind="turn_completed", native_event="agent_settled")
    )

    def _delivery_count() -> int:
        with factory.unit_of_work() as uow:
            return uow.connection.execute(
                "SELECT COUNT(*) FROM message_deliveries WHERE recipient_agent_id = ?",
                ("watcher",),
            ).fetchone()[0]

    assert wait_until(lambda: _delivery_count() == 1)
    with factory.unit_of_work() as uow:
        row = uow.connection.execute(
            "SELECT m.from_agent_id, m.subject FROM messages m "
            "JOIN message_deliveries d ON d.message_id = m.message_id "
            "WHERE d.recipient_agent_id = ?",
            ("watcher",),
        ).fetchone()
    assert row["from_agent_id"] == "harness-notable"
    assert "turn_completed" in row["subject"]


def test_output_delta_is_not_delivered_as_a_message(tmp_path):
    factory = make_factory(tmp_path)
    clock = _Clock()
    messages = make_message_service(factory, clock)
    with factory.unit_of_work() as uow:
        SqliteAgentRepo(clock).upsert(uow, agent_id="watcher")
    supervisor = make_supervisor(factory, clock, messages=messages)
    connector = FakeConnector()
    session = supervisor.open(
        kind="pi",
        connector=connector,
        owning_agent_id="harness-quiet",
        project_root=mkproj(tmp_path),
        notify_target={"strategy": "direct", "agent_id": "watcher"},
    )

    connector.push_event(make_event(session.session_id, kind="output_delta"))
    assert wait_until(lambda: len(supervisor.replay_events(session.session_id)) == 1)

    with factory.unit_of_work() as uow:
        count = uow.connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    assert count == 0


def test_notable_message_delivery_failure_never_breaks_the_pump(tmp_path):
    factory = make_factory(tmp_path)
    clock = _Clock()

    class _ExplodingMessages:
        def create_message(self, **kwargs):
            raise RuntimeError("message service is down")

    supervisor = make_supervisor(factory, clock, messages=_ExplodingMessages())
    connector = FakeConnector()
    session = supervisor.open(
        kind="pi",
        connector=connector,
        owning_agent_id="harness-msgfail",
        project_root=mkproj(tmp_path),
    )
    connector.push_event(make_event(session.session_id, kind="turn_completed"))
    connector.push_event(make_event(session.session_id, kind="output_delta", native_event="after"))

    assert wait_until(lambda: len(supervisor.replay_events(session.session_id)) == 2)
    assert supervisor.get(session.session_id) is not None


def test_no_messages_service_wired_is_a_silent_noop(tmp_path):
    factory = make_factory(tmp_path)
    clock = _Clock()
    supervisor = make_supervisor(factory, clock, messages=None)
    connector = FakeConnector()
    session = supervisor.open(
        kind="pi",
        connector=connector,
        owning_agent_id="harness-nomsg",
        project_root=mkproj(tmp_path),
    )
    connector.push_event(make_event(session.session_id, kind="turn_completed"))
    assert wait_until(lambda: len(supervisor.replay_events(session.session_id)) == 1)
    with factory.unit_of_work() as uow:
        count = uow.connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    assert count == 0
