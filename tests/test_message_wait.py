"""Tests for ``message_wait`` (Channels & Messages slice long-poll).

``message_wait`` REUSES the Event Log slice's ``event_wait`` (injected via the
``EventWaiter`` port) and materialises each ``message.created`` into a full,
visibility-filtered message WITH body. These hexagonal tests run the real
``MessageService`` + ``EventService`` over the SQLite adapters (``migrated_factory``)
and inject a deterministic ``Sleeper``/monotonic clock so the poll/timeout paths
run instantly. Coverage:

* immediate materialisation with body (the event payload carries no body);
* timeout -> empty page, ENTRY cursor unchanged, ``timed_out=True``, no real sleep;
* cursor advancement: a second wait from ``next_cursor`` only sees newer messages;
* observing a message created concurrently within one poll interval;
* imported routing visibility (directed message only surfaces to the eligible viewer);
* ``channel_id`` filtering of the materialised page;
* non-``message.created`` events on the workspace stream are filtered out;
* the canonical error catalogue (agent_id/cursor/timeout VALIDATION_ERROR,
  WORKSPACE_REQUIRED) surfaces from the underlying wait;
* INTERNAL_ERROR when no EventWaiter is wired; and the MCP tool envelope.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.mcp.tools.messages import register
from okto_nexus.adapters.outbound.sqlite.events_repo import (
    SqliteEventEmitter,
    SqliteEventRepo,
)
from okto_nexus.adapters.outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteWorkspaceRepo,
)
from okto_nexus.adapters.outbound.sqlite.messages_repo import (
    SqliteChannelRepo,
    SqliteMessageRepo,
)
from okto_nexus.application.events import EventService
from okto_nexus.application.messages import MessageService
from okto_nexus.application.ports import Repos
from okto_nexus.domain.ids import resolve_workspace_id
from okto_nexus.errors import ErrorCode, OktoNexusError


# --------------------------------------------------------------------------- #
# Test doubles & helpers
# --------------------------------------------------------------------------- #
class StubClock:
    """Deterministic Clock implementing the port (now_iso/now_epoch)."""

    def __init__(self, iso: str = "2026-06-07T00:00:00Z") -> None:
        self._iso = iso

    def now_iso(self) -> str:
        return self._iso

    def now_epoch(self) -> float:
        return 1_780_000_000.0


class ManualSleeper:
    """Fake Sleeper + monotonic clock: records sleeps, advances a virtual time."""

    def __init__(self) -> None:
        self.calls: list[float] = []
        self.t = 0.0

    def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.t += seconds

    def monotonic(self) -> float:
        return self.t


class TriggerSleeper(ManualSleeper):
    """Like ManualSleeper but fires ``trigger`` on the Nth sleep call."""

    def __init__(self, trigger, at_call: int = 1) -> None:
        super().__init__()
        self._trigger = trigger
        self._at = at_call

    def sleep(self, seconds: float) -> None:
        super().sleep(seconds)
        if len(self.calls) == self._at:
            self._trigger()


class FakeServer:
    """Captures FastMCP-style ``@server.tool()`` registrations by name."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def make_waiter(factory, config, clock, *, sleeper=None, monotonic=None, agents=None):
    """A real EventService over the same store, used as the EventWaiter port."""
    return EventService(
        connection_factory=factory,
        events=SqliteEventRepo(clock),
        clock=clock,
        config=config,
        agents=agents if agents is not None else SqliteAgentRepo(clock),
        sleeper=sleeper,
        monotonic=monotonic,
    )


def make_service(factory, config, clock, *, waiter=None, agents=None):
    """A real MessageService writing through the real SqliteEventEmitter."""
    return MessageService(
        connection_factory=factory,
        channels=SqliteChannelRepo(clock),
        messages=SqliteMessageRepo(clock),
        workspaces=SqliteWorkspaceRepo(clock),
        agents=agents if agents is not None else SqliteAgentRepo(clock),
        event_emitter=SqliteEventEmitter(SqliteEventRepo(clock)),
        clock=clock,
        max_inline_bytes=config.max_inline_bytes,
        event_waiter=waiter,
    )


def make_deps(factory, config, clock):
    return SimpleNamespace(
        config=config,
        connection_factory=factory,
        clock=clock,
        repos=Repos(),
        event_emitter=None,
    )


def mkdir(tmp_path, name="P"):
    p = tmp_path / name
    p.mkdir()
    return p


def emit_raw(factory, ws, *, stream="workspace", type="evt", payload=None):
    """Append a non-message event directly (to prove the type filter works)."""
    with factory.unit_of_work() as uow:
        return SqliteEventRepo().append(
            uow, workspace_id=ws, stream=stream, type=type, payload=payload
        )


# --------------------------------------------------------------------------- #
# Immediate materialisation (with body)
# --------------------------------------------------------------------------- #
def test_wait_returns_materialised_message_with_body(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    waiter = make_waiter(migrated_factory, tmp_config, clock)
    svc = make_service(migrated_factory, tmp_config, clock, waiter=waiter)
    proj = mkdir(tmp_path)

    created = svc.create_message(
        project_root=str(proj),
        from_agent_id="alice",
        subject="hi",
        body="the full body",
        artifacts=["art-1"],
    )

    page = svc.wait_messages(
        project_root=str(proj), agent_id="bob", cursor=0, timeout_seconds=0
    )
    assert page["timed_out"] is False
    assert len(page["messages"]) == 1
    msg = page["messages"][0]
    assert msg["message_id"] == created["message_id"]
    assert msg["body"] == "the full body"  # body materialised (event payload had none)
    assert msg["subject"] == "hi"
    assert msg["artifacts"] == ["art-1"]
    assert page["next_cursor"] == created["event_id"]
    assert page["has_more"] is False


def test_wait_timeout_empty_entry_cursor_unchanged_no_real_sleep(
    migrated_factory, tmp_config, tmp_path
):
    config = tmp_config
    clock = StubClock()
    sleeper = ManualSleeper()
    waiter = make_waiter(
        migrated_factory, config, clock, sleeper=sleeper.sleep, monotonic=sleeper.monotonic
    )
    svc = make_service(migrated_factory, config, clock, waiter=waiter)
    proj = mkdir(tmp_path)
    # Seed a workspace row via a channel listing (no messages yet).
    svc.list_channels(project_root=str(proj))

    page = svc.wait_messages(
        project_root=str(proj), agent_id="bob", cursor=0, timeout_seconds=1
    )
    assert page["messages"] == []
    assert page["timed_out"] is True
    assert page["next_cursor"] == 0  # entry cursor unchanged
    assert page["has_more"] is False
    assert sleeper.calls  # polled, but never slept for real


def test_wait_cursor_advances_only_new_messages(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    waiter = make_waiter(migrated_factory, tmp_config, clock)
    svc = make_service(migrated_factory, tmp_config, clock, waiter=waiter)
    proj = mkdir(tmp_path)

    first = svc.create_message(
        project_root=str(proj), from_agent_id="a", subject="m1", body="b1"
    )
    page1 = svc.wait_messages(
        project_root=str(proj), agent_id="v", cursor=0, timeout_seconds=0
    )
    assert [m["message_id"] for m in page1["messages"]] == [first["message_id"]]

    # A second message; waiting from the prior next_cursor yields ONLY the new one.
    second = svc.create_message(
        project_root=str(proj), from_agent_id="a", subject="m2", body="b2"
    )
    page2 = svc.wait_messages(
        project_root=str(proj),
        agent_id="v",
        cursor=page1["next_cursor"],
        timeout_seconds=0,
    )
    assert [m["message_id"] for m in page2["messages"]] == [second["message_id"]]
    assert page2["messages"][0]["body"] == "b2"


def test_wait_observes_message_created_within_one_interval(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    proj = mkdir(tmp_path)
    holder: dict = {}

    def create_during_sleep():
        holder["svc"].create_message(
            project_root=str(proj), from_agent_id="x", subject="late", body="late-body"
        )

    sleeper = TriggerSleeper(create_during_sleep, at_call=1)
    waiter = make_waiter(
        migrated_factory, tmp_config, clock, sleeper=sleeper.sleep, monotonic=sleeper.monotonic
    )
    svc = make_service(migrated_factory, tmp_config, clock, waiter=waiter)
    holder["svc"] = svc
    svc.list_channels(project_root=str(proj))  # ensure workspace row exists

    page = svc.wait_messages(
        project_root=str(proj), agent_id="a", cursor=0, timeout_seconds=10
    )
    assert page["timed_out"] is False
    assert [m["subject"] for m in page["messages"]] == ["late"]
    assert page["messages"][0]["body"] == "late-body"
    assert len(sleeper.calls) == 1  # observed after exactly one poll interval


# --------------------------------------------------------------------------- #
# Visibility & filtering
# --------------------------------------------------------------------------- #
def test_wait_directed_message_only_visible_to_eligible_viewer(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        waiter=make_waiter(migrated_factory, tmp_config, clock),
    )
    proj = mkdir(tmp_path)

    directed = svc.create_message(
        project_root=str(proj),
        from_agent_id="a",
        subject="psst",
        body="for B",
        target={"strategy": "direct", "agent_id": "agentB"},
    )

    seen = svc.wait_messages(
        project_root=str(proj), agent_id="agentB", cursor=0, timeout_seconds=0
    )
    assert [m["message_id"] for m in seen["messages"]] == [directed["message_id"]]
    assert seen["next_cursor"] == directed["event_id"]  # non-empty page advances

    # agentC is not eligible: the directed message is filtered out. The page is
    # ALL-hidden, so event_wait TIMES OUT and returns the ENTRY cursor unchanged
    # (the hidden event is re-scanned on the next poll until a visible one
    # appears - event_wait's canonical timeout contract, inherited verbatim).
    not_seen = svc.wait_messages(
        project_root=str(proj), agent_id="agentC", cursor=0, timeout_seconds=0
    )
    assert not_seen["messages"] == []
    assert not_seen["next_cursor"] == 0  # ENTRY cursor, NOT advanced (all-hidden)
    assert not_seen["timed_out"] is True


def test_wait_mixed_page_advances_cursor_past_hidden_event(
    migrated_factory, tmp_config, tmp_path
):
    # A NON-EMPTY page (hidden event followed by a visible one): event_wait
    # returns the visible event and next_cursor advances past BOTH; a second wait
    # from that cursor never re-scans the hidden event.
    clock = StubClock()
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        waiter=make_waiter(migrated_factory, tmp_config, clock),
    )
    proj = mkdir(tmp_path)

    hidden = svc.create_message(
        project_root=str(proj),
        from_agent_id="a",
        subject="psst",
        body="for B",
        target={"strategy": "direct", "agent_id": "agentB"},
    )
    visible = svc.create_message(
        project_root=str(proj), from_agent_id="a", subject="hi", body="all"
    )

    page = svc.wait_messages(
        project_root=str(proj), agent_id="agentC", cursor=0, timeout_seconds=0
    )
    assert [m["message_id"] for m in page["messages"]] == [visible["message_id"]]
    assert page["next_cursor"] == visible["event_id"]
    assert page["next_cursor"] > hidden["event_id"]  # advanced PAST the hidden one

    # A second wait from that cursor does not re-scan the hidden event.
    again = svc.wait_messages(
        project_root=str(proj),
        agent_id="agentC",
        cursor=page["next_cursor"],
        timeout_seconds=0,
    )
    assert again["messages"] == []
    assert again["next_cursor"] == page["next_cursor"]


def test_wait_author_of_directed_message_is_filtered(
    migrated_factory, tmp_config, tmp_path
):
    # Gate item 5: a message the author DIRECTED to another agent is filtered
    # back out for the author (can_view_message -> is_agent_eligible: author !=
    # target). A broadcast the author sends remains visible to the author.
    clock = StubClock()
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        waiter=make_waiter(migrated_factory, tmp_config, clock),
    )
    proj = mkdir(tmp_path)

    svc.create_message(
        project_root=str(proj),
        from_agent_id="a",
        subject="psst",
        body="for B",
        target={"strategy": "direct", "agent_id": "agentB"},
    )
    own_directed = svc.wait_messages(
        project_root=str(proj), agent_id="a", cursor=0, timeout_seconds=0
    )
    assert own_directed["messages"] == []  # author is not the target -> filtered

    bcast = svc.create_message(
        project_root=str(proj), from_agent_id="a", subject="hello", body="all"
    )
    own_bcast = svc.wait_messages(
        project_root=str(proj), agent_id="a", cursor=0, timeout_seconds=0
    )
    assert [m["message_id"] for m in own_bcast["messages"]] == [bcast["message_id"]]


def test_wait_channel_filter(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        waiter=make_waiter(migrated_factory, tmp_config, clock),
    )
    proj = mkdir(tmp_path)
    channels = svc.list_channels(project_root=str(proj))["channels"]
    general = next(c for c in channels if c["name"] == "general")["channel_id"]
    architecture = svc.create_channel(
        project_root=str(proj), name="architecture"
    )["channel"]["channel_id"]

    svc.create_message(
        project_root=str(proj), from_agent_id="a", subject="g", body="g", channel_id=general
    )
    in_arch = svc.create_message(
        project_root=str(proj),
        from_agent_id="a",
        subject="arch",
        body="arch",
        channel_id=architecture,
    )

    page = svc.wait_messages(
        project_root=str(proj),
        agent_id="v",
        channel_id=architecture,
        cursor=0,
        timeout_seconds=0,
    )
    assert [m["message_id"] for m in page["messages"]] == [in_arch["message_id"]]


def test_wait_filters_out_non_message_events(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        waiter=make_waiter(migrated_factory, tmp_config, clock),
    )
    proj = mkdir(tmp_path)
    ws = resolve_workspace_id(str(proj))
    svc.list_channels(project_root=str(proj))  # workspace row

    emit_raw(migrated_factory, ws, type="artifact.created", payload={"artifact_id": "x"})
    created = svc.create_message(
        project_root=str(proj), from_agent_id="a", subject="m", body="b"
    )
    emit_raw(migrated_factory, ws, type="custom.thing", payload={})

    page = svc.wait_messages(
        project_root=str(proj), agent_id="v", cursor=0, timeout_seconds=0
    )
    # Only the message.created event materialises into a message.
    assert [m["message_id"] for m in page["messages"]] == [created["message_id"]]


# --------------------------------------------------------------------------- #
# Error catalogue (propagated from the underlying event_wait)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad_agent", [None, "", "  "])
def test_wait_agent_id_required(migrated_factory, tmp_config, tmp_path, bad_agent):
    clock = StubClock()
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        waiter=make_waiter(migrated_factory, tmp_config, clock),
    )
    proj = mkdir(tmp_path)
    with pytest.raises(OktoNexusError) as ei:
        svc.wait_messages(
            project_root=str(proj), agent_id=bad_agent, cursor=0, timeout_seconds=0
        )
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


@pytest.mark.parametrize("bad", [None, "", "   "])
def test_wait_workspace_required(migrated_factory, tmp_config, bad):
    clock = StubClock()
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        waiter=make_waiter(migrated_factory, tmp_config, clock),
    )
    with pytest.raises(OktoNexusError) as ei:
        svc.wait_messages(project_root=bad, agent_id="a", timeout_seconds=0)
    assert ei.value.code == ErrorCode.WORKSPACE_REQUIRED.value


@pytest.mark.parametrize("bad_cursor", [-1, "5", 1.0, True])
def test_wait_invalid_cursor(migrated_factory, tmp_config, tmp_path, bad_cursor):
    clock = StubClock()
    svc = make_service(
        migrated_factory,
        tmp_config,
        clock,
        waiter=make_waiter(migrated_factory, tmp_config, clock),
    )
    proj = mkdir(tmp_path)
    with pytest.raises(OktoNexusError) as ei:
        svc.wait_messages(
            project_root=str(proj), agent_id="a", cursor=bad_cursor, timeout_seconds=0
        )
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


def test_wait_without_event_waiter_is_internal_error(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock, waiter=None)
    proj = mkdir(tmp_path)
    with pytest.raises(OktoNexusError) as ei:
        svc.wait_messages(project_root=str(proj), agent_id="a", timeout_seconds=0)
    assert ei.value.code == ErrorCode.INTERNAL_ERROR.value


# --------------------------------------------------------------------------- #
# MCP tool envelope
# --------------------------------------------------------------------------- #
def test_message_wait_tool_envelope(migrated_factory, tmp_config, tmp_path):
    deps = make_deps(migrated_factory, tmp_config, StubClock())
    server = FakeServer()
    register(server, deps)
    assert "message_wait" in server.tools

    proj = mkdir(tmp_path)
    created = server.tools["message_create"](
        project_root=str(proj), from_agent_id="a", subject="s", body="the-body"
    )
    assert created["ok"] is True

    waited = server.tools["message_wait"](
        project_root=str(proj), agent_id="v", cursor=0, timeout_seconds=0
    )
    assert waited["ok"] is True
    assert waited["data"]["timed_out"] is False
    bodies = [m["body"] for m in waited["data"]["messages"]]
    assert bodies == ["the-body"]

    # Failures surface as envelopes, never raised.
    missing_ws = server.tools["message_wait"](
        project_root="", agent_id="v", timeout_seconds=0
    )
    assert missing_ws["ok"] is False
    assert missing_ws["error"]["code"] == "WORKSPACE_REQUIRED"
