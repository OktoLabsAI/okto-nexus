"""SYS-03 / UAT-05 - closing the target-grammar gap (ADR 0004, follow-up).

``EV-SYS-003-target-grammar-gap.md`` proved, against a real running hub and a
real pi child, that a message addressed at a harness's registered agent via
the EXISTING target grammar (``direct``/``capability``/``role``/``tag``,
resolved by ``message_create`` per ADR 0001) is accepted and written to the
recipient's ordinary inbox row, but never reaches the harness connector - no
code path existed from the target-grammar resolver into
``HarnessSupervisor.send``.

This file is the failing-first repro for that gap, at the application layer
(the same layer the fix lands in), plus the fix's own regression coverage
once it exists. Uses the SAME ``FakeConnector`` as ``test_harness_supervisor``
- driving a real harness binary is the live SYS-03 re-run's job, not this
file's.

Design this file locks down (see ``application/harness_supervisor.py`` and
``application/ports.py`` for the implementation):

* A new, NOT-frozen port (``InboxDeliveryNotifier``) - symmetric to the
  existing ``HarnessSubscriberRegistry`` but keyed by recipient ``agent_id``
  and fired by ``MessageService.create_message`` alongside its EXISTING
  per-recipient inbox fan-out (ADR 0001), never a parallel delivery path.
* The forward reuses ``HarnessSupervisor.send`` itself (not a second gate),
  so it inherits the EXISTING capability guard for free - see
  ``test_harness_supervisor.test_send_only_connector_rejects_everything_but_
  send_turn`` for that guard's own direct coverage; this file's
  ``test_forward_to_a_send_only_connector_only_ever_issues_send_turn`` proves
  the forward path funnels through it rather than a bespoke check.
* Hand-off, not consumption: the ordinary inbox delivery row this feature
  rides on is created exactly as it always was, BEFORE any forward is
  attempted, and is never mutated by a forward succeeding or failing - see
  ``test_delivery_row_is_unaffected_by_forward_outcome_either_way``.
* A live harness's own D10 notable-event auto-message must never be
  re-forwarded into a (the same, or another) live harness session - see
  ``test_harness_to_harness_notable_messages_do_not_cascade``.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from okto_nexus.adapters.outbound.harness.subscribers import (
    InMemoryHarnessSubscriberRegistry,
)
from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteAgentRepo
from okto_nexus.application.harness_supervisor import HarnessSupervisor
from okto_nexus.application.messages import MessageService
from okto_nexus.domain.harness import HarnessCapabilities
from okto_nexus.errors import ErrorCode, OktoNexusError

from test_harness_supervisor import (  # noqa: E402 - shared fixtures/fakes
    FakeConnector,
    _Clock,
    make_event,
    make_factory,
    mkproj,
    wait_until,
)

#: Import guard: once the fix lands, ``InMemoryInboxDeliveryNotifier`` and
#: ``MessageService(inbox_notifier=...)`` exist; the FIRST run of this file
#: (failing-first capture) predates both, so every test below builds its own
#: ``MessageService`` with ONLY today's public constructor arguments and
#: asserts on OBSERED BEHAVIOUR (what reached ``connector.sent_commands``),
#: never on an import that would fail for the wrong reason.
try:  # pragma: no cover - exercised by whichever side of the fix is present
    from okto_nexus.adapters.outbound.inbox_notifier import (
        InMemoryInboxDeliveryNotifier,
    )
except ImportError:  # pre-fix: the adapter does not exist yet
    InMemoryInboxDeliveryNotifier = None  # type: ignore[assignment,misc]


def make_message_service(factory, clock, *, notifier: Any = None) -> MessageService:
    """Same minimal composition as ``test_harness_supervisor.make_message_
    service`` (no governance/approvals/guardrails - irrelevant to this
    file), plus the new optional ``inbox_notifier`` wiring when the fix (and
    therefore the kwarg) exists."""
    from okto_nexus.adapters.outbound.sqlite.events_repo import (
        SqliteEventEmitter,
        SqliteEventRepo,
    )
    from okto_nexus.adapters.outbound.sqlite.identity_repo import (
        SqliteSessionRepo,
        SqliteWorkspaceRepo,
    )
    from okto_nexus.adapters.outbound.sqlite.messages_repo import (
        SqliteChannelRepo,
        SqliteMessageDeliveryRepo,
        SqliteMessageRepo,
    )

    events_repo = SqliteEventRepo(clock)
    kwargs: dict[str, Any] = dict(
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
    if notifier is not None:
        kwargs["inbox_notifier"] = notifier
    return MessageService(**kwargs)


def make_supervisor(
    factory, clock, *, messages=None, notifier: Any = None, max_relay_depth: int | None = None
) -> HarnessSupervisor:
    from okto_nexus.adapters.outbound.sqlite.harness_repo import (
        SqliteHarnessEventRepo,
        SqliteHarnessSessionRepo,
    )

    kwargs: dict[str, Any] = dict(
        connection_factory=factory,
        clock=clock,
        agents=SqliteAgentRepo(clock),
        sessions=SqliteHarnessSessionRepo(clock),
        events=SqliteHarnessEventRepo(clock),
        subscribers=InMemoryHarnessSubscriberRegistry(),
        messages=messages,
        start_timeout_s=5.0,
        close_timeout_s=5.0,
    )
    if notifier is not None:
        kwargs["inbox_notifier"] = notifier
    if max_relay_depth is not None:
        kwargs["max_relay_depth"] = max_relay_depth
    return HarnessSupervisor(**kwargs)


def register_agent(factory, clock, agent_id: str, **fields: Any) -> None:
    with factory.unit_of_work() as uow:
        SqliteAgentRepo(clock).upsert(uow, agent_id=agent_id, **fields)


def wired(tmp_path, name: str = "home", *, max_relay_depth: int | None = None):
    """One factory + clock + notifier + supervisor + message service, all
    sharing the SAME notifier instance - exactly the composition-root shape
    ``tools/messages.py``/``tools/harness.py`` wire for real (one shared
    ``deps.inbox_delivery_notifier``). ``max_relay_depth`` lets a cascade
    test shrink the cap so it is reached in a small, deterministic number
    of hops instead of the production default."""
    factory = make_factory(tmp_path, name)
    clock = _Clock()
    notifier = InMemoryInboxDeliveryNotifier() if InMemoryInboxDeliveryNotifier else None
    messages = make_message_service(factory, clock, notifier=notifier)
    supervisor = make_supervisor(
        factory, clock, messages=messages, notifier=notifier, max_relay_depth=max_relay_depth
    )
    return factory, clock, supervisor, messages


def _send_turn_commands(connector: FakeConnector) -> list[Any]:
    return [c for c in connector.sent_commands if c.verb == "send_turn"]


# --------------------------------------------------------------------------- #
# The gap itself, and the fix: direct / capability targets
# --------------------------------------------------------------------------- #
def test_direct_target_reaches_the_connector(tmp_path):
    factory, clock, supervisor, messages = wired(tmp_path)
    register_agent(factory, clock, "operator-1")
    connector = FakeConnector()
    session = supervisor.open(
        kind="pi",
        connector=connector,
        owning_agent_id="harness-direct",
        project_root=mkproj(tmp_path),
    )

    messages.create_message(
        project_root=mkproj(tmp_path, "operator-proj"),
        from_agent_id="operator-1",
        subject="turn",
        body="reply with the single word: ok",
        target={"strategy": "direct", "agent_id": "harness-direct"},
    )

    assert wait_until(lambda: len(_send_turn_commands(connector)) == 1)
    command = _send_turn_commands(connector)[0]
    # Both known payload keys are set (pi/codex read "text", claude_code
    # stream reads "content") rather than switching on harness_kind - see
    # the forwarding callback's own docstring for why.
    assert command.payload.get("text") == "reply with the single word: ok"
    assert command.payload.get("content") == "reply with the single word: ok"
    assert supervisor.get(session.session_id) is not None


def test_capability_target_reaches_the_connector(tmp_path):
    factory, clock, supervisor, messages = wired(tmp_path)
    register_agent(factory, clock, "operator-2")
    connector = FakeConnector()
    supervisor.open(
        kind="pi",
        connector=connector,
        owning_agent_id="harness-cap",
        project_root=mkproj(tmp_path),
        agent_capabilities={"reviewer": True},
    )

    messages.create_message(
        project_root=mkproj(tmp_path, "operator-proj2"),
        from_agent_id="operator-2",
        subject="turn",
        body="capability-routed turn",
        target={"strategy": "capability", "capability": "reviewer"},
    )

    assert wait_until(lambda: len(_send_turn_commands(connector)) == 1)


def test_role_target_reaches_the_connector(tmp_path):
    factory, clock, supervisor, messages = wired(tmp_path)
    register_agent(factory, clock, "operator-2b")
    connector = FakeConnector()
    supervisor.open(
        kind="pi",
        connector=connector,
        owning_agent_id="harness-role",
        project_root=mkproj(tmp_path),
        role="reviewer",
    )

    messages.create_message(
        project_root=mkproj(tmp_path, "operator-proj2b"),
        from_agent_id="operator-2b",
        subject="turn",
        body="role-routed turn",
        target={"strategy": "role", "role": "reviewer"},
    )

    assert wait_until(lambda: len(_send_turn_commands(connector)) == 1)


def test_tag_target_reaches_the_connector(tmp_path):
    from okto_nexus.adapters.outbound.sqlite.identity_repo import (
        SqliteSessionRepo,
        SqliteWorkspaceRepo,
    )
    from okto_nexus.domain.base import new_id
    from okto_nexus.domain.ids import resolve_realpath, resolve_workspace_id

    factory, clock, supervisor, messages = wired(tmp_path)
    project = mkproj(tmp_path)
    register_agent(factory, clock, "operator-3")
    connector = FakeConnector()
    supervisor.open(
        kind="pi",
        connector=connector,
        owning_agent_id="harness-tag",
        project_root=project,
    )
    # harness_open has no tags parameter (D3 registers role/capabilities/
    # metadata only) - tag it directly, exactly as any other tag-catalog
    # write would, to exercise the 'tag' strategy independent of that gap.
    # 'tag' also resolves against the WORKSPACE'S PRESENT agents (ADR S1,
    # domain.inbox.requires_workspace_audience) - unlike capability/role,
    # so the harness additionally needs an active session in that same
    # workspace, exactly like any other 'tag'-routed recipient would.
    workspace_id = resolve_workspace_id(resolve_realpath(project))
    with factory.unit_of_work() as uow:
        SqliteAgentRepo(clock).set_tags(uow, agent_id="harness-tag", tags={"env": ["prod"]})
        SqliteWorkspaceRepo(clock).upsert(
            uow, workspace_id=workspace_id, root_realpath=resolve_realpath(project)
        )
        SqliteSessionRepo(clock).create(
            uow,
            session_id=new_id("ses"),
            agent_id="harness-tag",
            workspace_id=workspace_id,
            status="active",
        )

    messages.create_message(
        project_root=project,
        from_agent_id="operator-3",
        subject="turn",
        body="tag-routed turn",
        target={"strategy": "tag", "selector": {"env": ["prod"]}},
    )

    assert wait_until(lambda: len(_send_turn_commands(connector)) == 1)


# --------------------------------------------------------------------------- #
# Failure isolation (D8)
# --------------------------------------------------------------------------- #
def test_forward_failure_does_not_wedge_the_session(tmp_path):
    factory, clock, supervisor, messages = wired(tmp_path)
    register_agent(factory, clock, "operator-4")

    class _ExplodingConnector(FakeConnector):
        def send(self, session, command):
            raise RuntimeError("connector transport is down")

    connector = _ExplodingConnector()
    session = supervisor.open(
        kind="pi",
        connector=connector,
        owning_agent_id="harness-explode",
        project_root=mkproj(tmp_path),
    )

    # The send itself must not raise back into message_create - a forward
    # failure is this feature's problem, never the sender's.
    result = messages.create_message(
        project_root=mkproj(tmp_path, "operator-proj4"),
        from_agent_id="operator-4",
        subject="turn",
        body="this forward will fail",
        target={"strategy": "direct", "agent_id": "harness-explode"},
    )
    assert result["delivered_count"] == 1

    # The session is still live and tracked - one broken forward never
    # wedges the session, and a SECOND message addressed at it is fanned
    # out (ordinary inbox delivery) exactly as normally, without the
    # exploding connector's failure leaking into THIS unrelated call.
    assert supervisor.get(session.session_id) is not None
    result2 = messages.create_message(
        project_root=mkproj(tmp_path, "operator-proj4"),
        from_agent_id="operator-4",
        subject="turn 2",
        body="a second, independent message",
        target={"strategy": "direct", "agent_id": "harness-explode"},
    )
    assert result2["delivered_count"] == 1
    assert supervisor.get(session.session_id) is not None


def test_send_only_connector_still_rejects_steer_directly(tmp_path):
    """Companion to ``test_harness_supervisor.test_send_only_connector_
    rejects_everything_but_send_turn``: the forward path reuses
    ``HarnessSupervisor.send`` (not a bespoke gate), so this guard is proven
    ONCE, at the method the forward actually calls - a fabricated-capability
    regression here would break BOTH the direct-session-id HTTP/MCP path and
    the target-grammar forward path identically."""
    factory, clock, supervisor, messages = wired(tmp_path)
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
        owning_agent_id="harness-sendonly-tg",
        project_root=mkproj(tmp_path),
    )
    with pytest.raises(OktoNexusError) as excinfo:
        supervisor.send(session.session_id, "steer", {"content": "x"})
    assert excinfo.value.code == ErrorCode.VALIDATION_ERROR


def test_forward_to_a_send_only_connector_only_ever_issues_send_turn(tmp_path):
    factory, clock, supervisor, messages = wired(tmp_path)
    register_agent(factory, clock, "operator-5")
    caps = HarnessCapabilities(
        send_only=True,
        steer_timing=None,
        interrupt_requires_settle_wait=False,
        multiplexes_sessions=False,
        observes_session_end=False,
    )
    connector = FakeConnector(kind="claude_code", capabilities=caps)
    supervisor.open(
        kind="claude_code",
        connector=connector,
        owning_agent_id="harness-sendonly-fwd",
        project_root=mkproj(tmp_path),
    )

    messages.create_message(
        project_root=mkproj(tmp_path, "operator-proj5"),
        from_agent_id="operator-5",
        subject="turn",
        body="forwarded to a send_only connector",
        target={"strategy": "direct", "agent_id": "harness-sendonly-fwd"},
    )

    assert wait_until(lambda: len(connector.sent_commands) == 1)
    assert connector.sent_commands[0].verb == "send_turn"


# --------------------------------------------------------------------------- #
# Ack/consume semantics: hand-off, never consumption
# --------------------------------------------------------------------------- #
def test_delivery_row_is_unaffected_by_forward_outcome_either_way(tmp_path):
    factory, clock, supervisor, messages = wired(tmp_path)
    register_agent(factory, clock, "operator-6")
    connector = FakeConnector()
    supervisor.open(
        kind="pi",
        connector=connector,
        owning_agent_id="harness-ack",
        project_root=mkproj(tmp_path),
    )

    messages.create_message(
        project_root=mkproj(tmp_path, "operator-proj6"),
        from_agent_id="operator-6",
        subject="turn",
        body="hand-off, not consumption",
        target={"strategy": "direct", "agent_id": "harness-ack"},
    )
    assert wait_until(lambda: len(_send_turn_commands(connector)) == 1)

    # The forward is a push LAYERED OVER the ordinary, durable inbox row -
    # never a replacement for it. A successful forward never acks/consumes
    # the delivery: it stays exactly as ADR 0001 always left an unread
    # delivery, independent of whether anything downstream ever reads it.
    with factory.unit_of_work() as uow:
        row = uow.connection.execute(
            "SELECT status FROM message_deliveries WHERE recipient_agent_id = ?",
            ("harness-ack",),
        ).fetchone()
    assert row["status"] == "unread"


# --------------------------------------------------------------------------- #
# Harness-to-harness relaying (limitation 2: the blanket guard above blocked
# INTENTIONAL A->B relaying along with the runaway cascade it was meant to
# stop). Design, spelled out here because it is the part a reviewer will
# want justified rather than assumed:
#
# * ``notify_target`` pointed at another harness's agent is ALREADY the
#   operator's declared intent to relay (D10 lets any session set it to
#   anything the target grammar can resolve) - the old guard was refusing
#   to honour an intent the API already accepted, not adding real safety
#   beyond "no two harnesses may ever talk to each other at all".
# * What distinguishes a legitimate A->B relay from a runaway cascade is
#   DEPTH: a bounded number of consecutive forward-hops. A cycle-check over
#   the live session graph was considered and rejected - it would forbid a
#   deliberate, non-cyclic A->B->C chain (three harnesses handing work off
#   in sequence, each a DIFFERENT agent) for no safety reason, and it is
#   more state to keep consistent than a single integer. A depth cap
#   provably terminates in O(max_relay_depth) hops with no graph to
#   maintain; that termination guarantee is the property actually needed,
#   so it is what is built (``max_relay_depth`` / ``DEFAULT_MAX_RELAY_DEPTH``
#   in ``harness_supervisor.py``).
# * That depth cannot ride on ``HarnessEvent`` or any frozen domain type
#   (ABSOLUTE RULE 2), and this task may not touch ``MessageService`` or
#   ``ports.py`` (ABSOLUTE RULE 3 - those files belong to sibling agents).
#   So the state lives ENTIRELY supervisor-side, on the supervisor's own
#   non-frozen ``_LiveSession`` bookkeeping: the depth a forward runs at is
#   read off the SOURCE session's own ``relay_depth``/``relay_chain_id`` (0
#   / ``None`` if it was never itself the target of a forward, or if its
#   chain has aged out past ``relay_chain_max_age_s`` with no further hops
#   - see ``test_slow_paced_harness_to_harness_cascade_is_still_stopped``
#   below: continuation is keyed on CHAIN IDENTITY, never on elapsed time
#   since the source's own LAST hop, which is what let a cascade paced
#   slower than the old per-hop TTL defeat the cap entirely) and recorded
#   onto the TARGET session inside ``HarnessSupervisor.send`` itself - the
#   ONE place anything ever writes those fields, so a session receiving a
#   turn through the ORDINARY, non-relay path (a direct ``send()`` call,
#   e.g. from an MCP/HTTP tool) resets its bookkeeping to 0 / ``None``
#   instead of inheriting a stale chain from an unrelated, long-past relay.
# * The failure mode when the cap IS hit is LOUD: a ``kind="error"``
#   ``HarnessEvent`` (``native_event="nexus/relay_depth_exceeded"``) is
#   published to the target session's live subscribers AND persisted
#   (durable, replayable) - see
#   ``test_runaway_harness_to_harness_cascade_is_stopped_and_observable``,
#   which asserts on that event directly, not merely on the forward count
#   plateauing. A silently dropped message is exactly how SYS-03 hid for a
#   whole phase; this task's own brief is explicit that a fourth instance
#   of that pattern is not acceptable.
# --------------------------------------------------------------------------- #
class _AutoReplyConnector(FakeConnector):
    """A :class:`FakeConnector` whose ``send`` immediately manufactures a
    ``turn_completed`` reply on ITS OWN event stream.

    Justification against the real protocol (RES-C1): every one of the
    four connector matrix entries (H-PI, H-CX, H-CC, H-CA-as-receiver)
    eventually emits SOME turn-completion signal after being sent a turn -
    that is the one, generic, harness-agnostic fact this fake claims to
    model, nothing about any one harness's specific wire shape, ordering or
    timing beyond it. It exists ONLY to build a fast, fully-owned,
    deterministic repro of a runaway A->B->A->B... cascade - the real
    hazard the depth cap defends against - without depending on, or
    claiming to faithfully emulate, any real harness binary. Driving an
    actual cascade against real pi/codex/claude_code children is exactly
    the kind of un-bounded, non-deterministic wait this task's rule 5
    forbids for a unit-level regression test.
    """

    def send(self, session, command):
        super().send(session, command)
        if command.verb == "send_turn":
            self.push_event(
                make_event(
                    self.session.session_id,
                    kind="turn_completed",
                    native_event="agent_settled",
                )
            )


def test_harness_to_harness_relay_succeeds_for_a_single_legitimate_hop(tmp_path):
    """THE FIX (limitation 2): a message sent BY a currently-live harness's
    own owning_agent_id, addressed at ANOTHER live harness via
    ``notify_target``, now reaches that harness's connector - this
    previously asserted the opposite (``len(...) == 0`` for both sides; see
    git history for the pre-fix version of this test) because the old
    guard blocked every harness-to-harness message unconditionally, the
    exact limitation this task closes. Session B here never itself
    completes a turn in response (plain ``FakeConnector``, no auto-reply),
    so this is a clean single-hop check, independent of the cascade-cap
    mechanics exercised separately below."""
    factory, clock, supervisor, messages = wired(tmp_path)
    connector_a = FakeConnector(kind="pi")
    connector_b = FakeConnector(kind="pi")
    session_a = supervisor.open(
        kind="pi",
        connector=connector_a,
        owning_agent_id="harness-a",
        project_root=mkproj(tmp_path, "proj-a"),
        notify_target={"strategy": "direct", "agent_id": "harness-b"},
    )
    supervisor.open(
        kind="pi",
        connector=connector_b,
        owning_agent_id="harness-b",
        project_root=mkproj(tmp_path, "proj-b"),
        notify_target={"strategy": "direct", "agent_id": "harness-a"},
    )

    connector_a.push_event(
        make_event(session_a.session_id, kind="turn_completed", native_event="agent_settled")
    )

    assert wait_until(lambda: len(_send_turn_commands(connector_b)) == 1)
    # B never replied (no auto-reply connector here), so nothing relays
    # back into A - this is a single legitimate hop, not a cascade.
    time.sleep(0.2)
    assert len(_send_turn_commands(connector_a)) == 0


def test_runaway_harness_to_harness_cascade_is_stopped_and_observable(tmp_path):
    """The companion case: two live harnesses notify-targeting EACH OTHER,
    with a connector that (like every real harness, see
    ``_AutoReplyConnector``) completes whatever turn it is sent - forming
    exactly the runaway A->B->A->B... loop the relay-depth cap exists to
    stop. ``max_relay_depth=2`` makes the cap deterministic and fast to
    reach (traced by hand below) rather than depending on the TTL.

    Hand-traced expected sequence (asserted below, not merely bounded):
      hop 1: A's manually-pushed turn_completed -> message A->B -> depth 1
             (<=2, allowed) -> connector_b.send (command #1) -> B
             auto-replies its own turn_completed.
      hop 2: B's turn_completed -> message B->A -> depth 2 (<=2, allowed)
             -> connector_a.send (command #1) -> A auto-replies.
      hop 3: A's turn_completed -> message A->B -> depth 3 (>2) -> BLOCKED,
             reported, never reaches connector_b.
    """
    factory, clock, supervisor, messages = wired(tmp_path, max_relay_depth=2)
    connector_a = _AutoReplyConnector(kind="pi")
    connector_b = _AutoReplyConnector(kind="pi")
    session_a = supervisor.open(
        kind="pi",
        connector=connector_a,
        owning_agent_id="cascade-a",
        project_root=mkproj(tmp_path, "proj-cascade-a"),
        notify_target={"strategy": "direct", "agent_id": "cascade-b"},
    )
    session_b = supervisor.open(
        kind="pi",
        connector=connector_b,
        owning_agent_id="cascade-b",
        project_root=mkproj(tmp_path, "proj-cascade-b"),
        notify_target={"strategy": "direct", "agent_id": "cascade-a"},
    )

    blocked_events: list[Any] = []
    supervisor.subscribers.subscribe(session_a.session_id, blocked_events.append)
    supervisor.subscribers.subscribe(session_b.session_id, blocked_events.append)

    connector_a.push_event(
        make_event(session_a.session_id, kind="turn_completed", native_event="agent_settled")
    )

    def _cascade_was_blocked() -> bool:
        return any(
            e.kind == "error" and e.native_event == "nexus/relay_depth_exceeded"
            for e in blocked_events
        )

    # OBSERVABLE, not a silent drop: this is the assertion that actually
    # discriminates the fix from the old blanket guard (which would also
    # leave both send counts at 0 forever - see the pre-fix version of
    # this test in git history, which asserted exactly that and PASSED for
    # the wrong reason).
    assert wait_until(_cascade_was_blocked, timeout_s=5.0), (
        "expected a kind='error' native_event='nexus/relay_depth_exceeded' "
        "HarnessEvent on the blocked hop; none was published"
    )

    # Exactly two hops happened (hand-traced above), then the third was
    # refused - relaying DID work (unlike the old guard) but never ran away.
    assert len(_send_turn_commands(connector_a)) == 1
    assert len(_send_turn_commands(connector_b)) == 1
    # Stability: no further growth once the cap fires (real termination,
    # not a race that happens to look stopped at assertion time).
    time.sleep(0.3)
    assert len(_send_turn_commands(connector_a)) == 1
    assert len(_send_turn_commands(connector_b)) == 1

    # Durable too (replay_events), not only the live subscription above -
    # this is what makes the stop auditable after the fact, same standard
    # D10 already holds every other harness event to.
    blocked = next(
        e for e in blocked_events
        if e.kind == "error" and e.native_event == "nexus/relay_depth_exceeded"
    )
    replayed = supervisor.replay_events(blocked.session_id)
    assert any(
        e.kind == "error" and e.native_event == "nexus/relay_depth_exceeded"
        for e in replayed
    )


def test_slow_paced_harness_to_harness_cascade_is_still_stopped(tmp_path):
    """FAILING-FIRST REPRO, now the regression guard for the fix it drove
    (see ``harness_supervisor.py``'s module docstring, "CHAIN IDENTITY,
    not elapsed-time-since-last-hop", for the full design record): the
    pre-fix depth cap was defeated by ANY cascade paced slower than
    ``relay_depth_ttl_s``, regardless of that TTL's magnitude, because
    ``_resolve_relay_depth`` reset a source session's depth to 0 whenever
    ``now - relay_depth_updated_at > relay_depth_ttl_s`` - a per-hop-GAP
    check, which is wrong by construction: EVERY hop's own gap-since-the-
    hop-before-it exceeds the TTL once pacing does, so every hop looked
    like hop 1 of a brand new chain, forever. A real A<->B agent
    conversation is paced by model latency and tool use (routinely tens of
    seconds per hop, per the task brief) - SLOWER than the 30s production
    default is the NORMAL shape, not the exotic one.

    The captured pre-fix run of this exact scenario (8 hops, 0.15s spacing
    against a 0.05s ``relay_depth_ttl_s``, cap 2): all 8 hops forwarded, 0
    blocked. See ``scratchpad/failing_first_repro.log`` for that raw
    capture, taken before any of this fix's code changes.

    Post-fix, this drives the same 8 sequential A<->B hops, each spaced
    0.15s apart, against ``max_relay_depth=2`` AND a deliberately tight
    ``relay_chain_max_age_s=5.0`` (far bigger than any single 0.15s
    inter-hop gap, but far smaller than the 1800s production default) -
    proving the cap now holds on CHAIN IDENTITY, not on how that age bound
    compares to hop pacing. No ``_AutoReplyConnector`` (that fake replies
    with zero delay, well under any bound, which is why it alone never
    caught this) - each hop is driven by hand so the pacing is explicit.
    """
    factory, clock, supervisor, messages = wired(tmp_path, max_relay_depth=2)
    # `wired()`'s signature does not expose `relay_chain_max_age_s` (this
    # file's shared helper deliberately keeps only what every OTHER test
    # here needs). Rebuild the supervisor here, reusing the same
    # factory/clock/messages/notifier `wired()` already wired together, to
    # inject the tight age bound this test is specifically about.
    import okto_nexus.application.harness_supervisor as hs_mod

    supervisor = hs_mod.HarnessSupervisor(
        connection_factory=factory,
        clock=clock,
        agents=supervisor._agents,
        sessions=supervisor._sessions,
        events=supervisor._events,
        subscribers=InMemoryHarnessSubscriberRegistry(),
        messages=messages,
        inbox_notifier=supervisor._inbox_notifier,
        start_timeout_s=5.0,
        close_timeout_s=5.0,
        max_relay_depth=2,
        relay_chain_max_age_s=5.0,
    )

    connector_a = FakeConnector(kind="pi")
    connector_b = FakeConnector(kind="pi")
    session_a = supervisor.open(
        kind="pi",
        connector=connector_a,
        owning_agent_id="slow-cascade-a",
        project_root=mkproj(tmp_path, "proj-slow-cascade-a"),
        notify_target={"strategy": "direct", "agent_id": "slow-cascade-b"},
    )
    session_b = supervisor.open(
        kind="pi",
        connector=connector_b,
        owning_agent_id="slow-cascade-b",
        project_root=mkproj(tmp_path, "proj-slow-cascade-b"),
        notify_target={"strategy": "direct", "agent_id": "slow-cascade-a"},
    )

    blocked_events: list[Any] = []
    supervisor.subscribers.subscribe(session_a.session_id, blocked_events.append)
    supervisor.subscribers.subscribe(session_b.session_id, blocked_events.append)

    def _cascade_was_blocked() -> bool:
        return any(
            e.kind == "error" and e.native_event == "nexus/relay_depth_exceeded"
            for e in blocked_events
        )

    # Drive 8 hops by hand, alternating A -> B -> A -> B..., each spaced
    # 0.15s apart (well under relay_chain_max_age_s=5.0, so the chain
    # never ages out mid-cascade). Each hop is "session X's own agent
    # settled a turn", which the notify_target wiring forwards to the
    # OTHER session as a send_turn.
    sessions = [session_a, session_b]
    connectors = [connector_a, connector_b]
    hops_forwarded = 0
    for hop in range(8):
        time.sleep(0.15)
        if _cascade_was_blocked():
            break
        src_idx = hop % 2
        dst_idx = 1 - src_idx
        before = len(_send_turn_commands(connectors[dst_idx]))
        connectors[src_idx].push_event(
            make_event(
                sessions[src_idx].session_id,
                kind="turn_completed",
                native_event="agent_settled",
            )
        )
        delivered = wait_until(
            lambda: len(_send_turn_commands(connectors[dst_idx])) > before
            or _cascade_was_blocked(),
            timeout_s=2.0,
        )
        if not delivered:
            break
        if len(_send_turn_commands(connectors[dst_idx])) > before:
            hops_forwarded += 1

    total_forwarded = len(_send_turn_commands(connector_a)) + len(
        _send_turn_commands(connector_b)
    )
    assert _cascade_was_blocked(), (
        f"expected the depth cap (max_relay_depth=2) to refuse a hop within "
        f"8 slow-paced (0.15s per hop) hops; instead {total_forwarded} hops "
        "were forwarded and 0 were blocked - chain identity should have "
        "kept counting regardless of pacing."
    )
    assert total_forwarded <= 2, (
        f"expected at most 2 hops (max_relay_depth=2) to be forwarded "
        f"before the cascade was blocked; {total_forwarded} were forwarded"
    )


def test_new_conversation_between_same_pair_long_after_an_earlier_finished_chain_is_not_blocked(
    tmp_path,
):
    """The regression the slow-cascade fix above is most likely to
    introduce (see the task brief): a chain that reached the depth cap
    (blocked, never completed) must eventually heal, so a LATER, genuinely
    UNRELATED conversation between the same A/B pair is not permanently
    poisoned by the earlier one's leftover bookkeeping.

    Drives the SAME two-hop-then-blocked shape as
    ``test_runaway_harness_to_harness_cascade_is_stopped_and_observable``
    (``max_relay_depth=2``), confirms the third hop is refused, then fakes
    ``time.monotonic()`` jumping forward well past
    ``relay_chain_max_age_s`` (no real sleep - see
    ``HarnessSupervisor._monotonic``, injected exactly for this) with NO
    further hops in between (a genuinely idle gap, not a fast-paced
    cascade hiding behind a jump), and drives one more, brand new hop -
    which must go through, not be blocked as "hop 4" of the old chain.
    """
    factory, clock, supervisor, messages = wired(tmp_path, max_relay_depth=2)
    import okto_nexus.application.harness_supervisor as hs_mod

    fake_time = [1_000.0]

    def _fake_monotonic() -> float:
        return fake_time[0]

    supervisor = hs_mod.HarnessSupervisor(
        connection_factory=factory,
        clock=clock,
        agents=supervisor._agents,
        sessions=supervisor._sessions,
        events=supervisor._events,
        subscribers=InMemoryHarnessSubscriberRegistry(),
        messages=messages,
        inbox_notifier=supervisor._inbox_notifier,
        start_timeout_s=5.0,
        close_timeout_s=5.0,
        max_relay_depth=2,
        relay_chain_max_age_s=60.0,
    )
    supervisor._monotonic = _fake_monotonic

    connector_a = _AutoReplyConnector(kind="pi")
    connector_b = _AutoReplyConnector(kind="pi")
    session_a = supervisor.open(
        kind="pi",
        connector=connector_a,
        owning_agent_id="heal-a",
        project_root=mkproj(tmp_path, "proj-heal-a"),
        notify_target={"strategy": "direct", "agent_id": "heal-b"},
    )
    session_b = supervisor.open(
        kind="pi",
        connector=connector_b,
        owning_agent_id="heal-b",
        project_root=mkproj(tmp_path, "proj-heal-b"),
        notify_target={"strategy": "direct", "agent_id": "heal-a"},
    )

    blocked_events: list[Any] = []
    supervisor.subscribers.subscribe(session_a.session_id, blocked_events.append)
    supervisor.subscribers.subscribe(session_b.session_id, blocked_events.append)

    def _cascade_was_blocked() -> bool:
        return any(
            e.kind == "error" and e.native_event == "nexus/relay_depth_exceeded"
            for e in blocked_events
        )

    # Old chain: A -> B (depth 1) -> A (depth 2, auto-reply) -> B (depth 3,
    # BLOCKED). Same hand-traced shape as the fast-cascade test.
    connector_a.push_event(
        make_event(session_a.session_id, kind="turn_completed", native_event="agent_settled")
    )
    assert wait_until(_cascade_was_blocked, timeout_s=5.0), (
        "setup failed: expected the old chain to hit the depth cap before "
        "the healing assertion below means anything"
    )
    forwarded_before_heal = len(_send_turn_commands(connector_a)) + len(
        _send_turn_commands(connector_b)
    )
    assert forwarded_before_heal == 2  # hand-traced: exactly 2 hops, then blocked

    # No further hops for well over relay_chain_max_age_s=60.0 - a
    # genuinely idle gap between conversations, not a slow-paced
    # CONTINUATION of the same one (that shape is covered by
    # test_slow_paced_harness_to_harness_cascade_is_still_stopped above,
    # and must stay distinguishable from this one).
    fake_time[0] += 120.0

    # A brand new, independent turn from A - e.g. an operator's fresh
    # request to A, well after the earlier chain finished (blocked) and
    # went idle. This must reach B as a fresh hop 1, NOT be refused as a
    # continuation of the dead chain.
    before = len(_send_turn_commands(connector_b))
    connector_a.push_event(
        make_event(session_a.session_id, kind="turn_completed", native_event="agent_settled")
    )
    assert wait_until(lambda: len(_send_turn_commands(connector_b)) > before, timeout_s=5.0), (
        "expected a new conversation long after the earlier chain finished "
        "to reach the target harness; it was wrongly blocked as a "
        "continuation of the stale, long-idle chain"
    )


def test_relay_from_another_live_harness_into_a_send_only_connector_only_ever_issues_send_turn(
    tmp_path,
):
    """Capability rules hold under relay, not only under an operator-
    originated forward (``test_forward_to_a_send_only_connector_only_ever_
    issues_send_turn`` above already covers that case): a send_only
    connector (D7b/cc-socks) can RECEIVE a relayed ``send_turn`` from
    ANOTHER LIVE HARNESS but must never be asked to steer - exactly as it
    never could from an operator, since the relay path reuses
    ``HarnessSupervisor.send``'s existing capability guard rather than a
    relay-specific bypass."""
    factory, clock, supervisor, messages = wired(tmp_path)
    caps = HarnessCapabilities(
        send_only=True,
        steer_timing=None,
        interrupt_requires_settle_wait=False,
        multiplexes_sessions=False,
        observes_session_end=False,
    )
    source_connector = FakeConnector(kind="pi")
    source_session = supervisor.open(
        kind="pi",
        connector=source_connector,
        owning_agent_id="relay-source",
        project_root=mkproj(tmp_path, "proj-relay-source"),
        notify_target={"strategy": "direct", "agent_id": "relay-target-sendonly"},
    )
    target_connector = FakeConnector(kind="claude_code", capabilities=caps)
    supervisor.open(
        kind="claude_code",
        connector=target_connector,
        owning_agent_id="relay-target-sendonly",
        project_root=mkproj(tmp_path, "proj-relay-target"),
    )

    source_connector.push_event(
        make_event(source_session.session_id, kind="turn_completed", native_event="agent_settled")
    )

    assert wait_until(lambda: len(target_connector.sent_commands) == 1)
    assert all(c.verb == "send_turn" for c in target_connector.sent_commands)


def test_self_addressed_direct_message_does_not_loop(tmp_path):
    """A degenerate case of the same guard: a 'direct' target (unlike
    capability/role/tag/broadcast) does NOT exclude the sender itself at the
    routing layer - so a harness's own notify_target pointed at its OWN
    agent_id must not re-forward into the SAME session."""
    factory, clock, supervisor, messages = wired(tmp_path)
    connector = FakeConnector(kind="pi")
    session = supervisor.open(
        kind="pi",
        connector=connector,
        owning_agent_id="harness-self",
        project_root=mkproj(tmp_path),
        notify_target={"strategy": "direct", "agent_id": "harness-self"},
    )

    connector.push_event(
        make_event(session.session_id, kind="turn_completed", native_event="agent_settled")
    )
    time.sleep(0.3)

    assert len(_send_turn_commands(connector)) == 0


# --------------------------------------------------------------------------- #
# The REAL composition root (production wiring, not this file's own `wired`
# helper) - proves `tools/messages.py::build_service` and `tools/harness.py::
# build_service` actually share ONE InboxDeliveryNotifier instance, exactly
# as the live SYS-03 re-run needs.
# --------------------------------------------------------------------------- #
def test_real_composition_root_wires_the_shared_notifier(tmp_path):
    from okto_nexus.adapters.inbound.mcp.server import bootstrap
    from okto_nexus.adapters.inbound.mcp.tools.harness import (
        build_service as build_harness_supervisor,
    )
    from okto_nexus.adapters.inbound.mcp.tools.messages import (
        build_service as build_message_service,
    )

    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    supervisor = build_harness_supervisor(deps)
    messages = build_message_service(deps)

    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id="operator-real")

    connector = FakeConnector()
    supervisor.open(
        kind="pi",
        connector=connector,
        owning_agent_id="harness-real",
        project_root=mkproj(tmp_path, "proj"),
    )

    messages.create_message(
        project_root=mkproj(tmp_path, "operator-proj"),
        from_agent_id="operator-real",
        subject="turn",
        body="reaches through the real composition root",
        target={"strategy": "direct", "agent_id": "harness-real"},
    )

    assert wait_until(lambda: len(_send_turn_commands(connector)) == 1)
