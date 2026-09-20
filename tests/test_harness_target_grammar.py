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


def make_supervisor(factory, clock, *, messages=None, notifier: Any = None) -> HarnessSupervisor:
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
    return HarnessSupervisor(**kwargs)


def register_agent(factory, clock, agent_id: str, **fields: Any) -> None:
    with factory.unit_of_work() as uow:
        SqliteAgentRepo(clock).upsert(uow, agent_id=agent_id, **fields)


def wired(tmp_path, name: str = "home"):
    """One factory + clock + notifier + supervisor + message service, all
    sharing the SAME notifier instance - exactly the composition-root shape
    ``tools/messages.py``/``tools/harness.py`` wire for real (one shared
    ``deps.inbox_delivery_notifier``)."""
    factory = make_factory(tmp_path, name)
    clock = _Clock()
    notifier = InMemoryInboxDeliveryNotifier() if InMemoryInboxDeliveryNotifier else None
    messages = make_message_service(factory, clock, notifier=notifier)
    supervisor = make_supervisor(factory, clock, messages=messages, notifier=notifier)
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
# Harness-to-harness feedback loop (D8 failure isolation, cascade class)
# --------------------------------------------------------------------------- #
def test_harness_to_harness_notable_messages_do_not_cascade(tmp_path):
    """D10 already delivers a harness's OWN notable event (turn_completed)
    as an ordinary message from its owning_agent_id. Without a guard, two
    live harnesses notify-targeting each other's registered agent would
    ping-pong forever: A's turn_completed -> forwarded into B as a turn ->
    B's own turn_completed -> forwarded back into A -> ... SYS-09 already
    proves 3 harnesses live concurrently in the same workspace, so this is
    live-reachable, not theoretical. The forward path must never re-inject
    a message sent BY a currently-live harness's own owning_agent_id back
    into ANY live harness session."""
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

    # Give the pump + D10 delivery + (if unguarded) the cascading forward
    # every chance to run.
    time.sleep(0.3)

    assert len(_send_turn_commands(connector_b)) == 0
    assert len(_send_turn_commands(connector_a)) == 0


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
