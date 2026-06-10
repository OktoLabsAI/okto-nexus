"""Tests for the Channels & Messages slice.

Hexagonal unit/integration tests: the application service is exercised over the
real SQLite adapters (via ``migrated_factory``), while the Event Log
``EventEmitter`` port (owned by another slice) is supplied either as a fake (to
inspect emissions) or as the real ``SqliteEventEmitter`` (to assert true,
monotonic ``event_id`` assignment and atomic same-commit coupling). Covers the
happy paths, the canonical error catalogue (WORKSPACE_REQUIRED /
WORKSPACE_UNRESOLVED / VALIDATION_ERROR / CONTENT_TOO_LARGE / NOT_FOUND), the
64KB inclusive inline boundary, channel seeding, parent/reply linkage, imported
routing visibility (directed vs broadcast), recipient resolution + inbox fan-out,
the MCP tool envelope, cross-workspace isolation, atomic rollback when the event
append fails, and concurrency (parallel writers with strictly increasing
event_ids and no cross-workspace leakage).
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.mcp.tools.messages import build_service, register
from okto_nexus.adapters.outbound.sqlite.events_repo import (
    SqliteEventEmitter,
    SqliteEventRepo,
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
from okto_nexus.application.events import EventService
from okto_nexus.application.messages import MessageService
from okto_nexus.application.ports import Repos
from okto_nexus.domain.ids import resolve_workspace_id
from okto_nexus.domain.models import Channel
from okto_nexus.errors import ErrorCode, OktoNexusError


# --------------------------------------------------------------------------- #
# Test doubles & helpers
# --------------------------------------------------------------------------- #
class StubClock:
    """Deterministic Clock implementing the port (mutable ISO instant)."""

    def __init__(self, iso: str = "2026-06-07T00:00:00Z") -> None:
        self._iso = iso

    def now_iso(self) -> str:
        return self._iso

    def now_epoch(self) -> float:
        return 1_780_000_000.0

    def set(self, iso: str) -> None:
        self._iso = iso


class FakeEmitter:
    """Fake EventEmitter recording emissions and assigning monotonic ids."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self._next = 0

    def emit(
        self,
        uow,
        *,
        workspace_id,
        stream,
        type,
        payload=None,
        actor_agent_id=None,
        visibility=None,
        target=None,
    ) -> int:
        self._next += 1
        self.events.append(
            {
                "event_id": self._next,
                "workspace_id": workspace_id,
                "stream": stream,
                "type": type,
                "payload": payload,
                "actor_agent_id": actor_agent_id,
                "visibility": visibility,
                "target": target,
            }
        )
        return self._next


class RaisingEmitter:
    """EventEmitter whose append fails, to drive atomic rollback."""

    def emit(self, uow, **kwargs) -> int:
        raise OktoNexusError(ErrorCode.DB_ERROR, "simulated event append failure.")


class FakeServer:
    """Captures FastMCP-style ``@server.tool()`` registrations by name."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def real_emitter(clock) -> SqliteEventEmitter:
    return SqliteEventEmitter(SqliteEventRepo(clock))


def make_service(factory, config, clock, emitter=None, agents=None) -> MessageService:
    return MessageService(
        connection_factory=factory,
        channels=SqliteChannelRepo(clock),
        messages=SqliteMessageRepo(clock),
        workspaces=SqliteWorkspaceRepo(clock),
        agents=agents if agents is not None else SqliteAgentRepo(clock),
        sessions=SqliteSessionRepo(clock),
        deliveries=SqliteMessageDeliveryRepo(clock),
        event_emitter=emitter if emitter is not None else FakeEmitter(),
        clock=clock,
        max_inline_bytes=config.max_inline_bytes,
    )


def make_deps(factory, config, clock, emitter=None):
    return SimpleNamespace(
        config=config,
        connection_factory=factory,
        clock=clock,
        repos=Repos(),
        event_emitter=emitter,
    )


def count(factory, table: str) -> int:
    conn = factory.get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def retry_db(fn, attempts: int = 40, delay: float = 0.02):
    """Retry on transient DB_ERROR (WAL busy/snapshot under contention)."""
    last = None
    for _ in range(attempts):
        try:
            return fn()
        except OktoNexusError as exc:
            if exc.code != ErrorCode.DB_ERROR.value:
                raise
            last = exc
            time.sleep(delay)
    raise last  # pragma: no cover


def mkdir(tmp_path, name):
    p = tmp_path / name
    p.mkdir()
    return p


# --------------------------------------------------------------------------- #
# channel_list / seeding
# --------------------------------------------------------------------------- #
def test_channel_list_seeds_only_general(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock("2026-06-07T00:00:00Z"))
    proj = mkdir(tmp_path, "P")

    out = svc.list_channels(project_root=str(proj))
    channels = out["channels"]
    assert {c["name"] for c in channels} == {"general"}
    ws = resolve_workspace_id(str(proj))
    for c in channels:
        assert c["channel_id"]
        assert c["workspace_id"] == ws
        assert c["created_at"] == "2026-06-07T00:00:00Z"

    # Idempotent: a second call does not duplicate the seeded channel.
    again = svc.list_channels(project_root=str(proj))
    assert {c["channel_id"] for c in again["channels"]} == {
        c["channel_id"] for c in channels
    }
    assert count(migrated_factory, "channels") == 1


def test_channel_list_requires_workspace(migrated_factory, tmp_config):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    with pytest.raises(OktoNexusError) as ei:
        svc.list_channels(project_root=None)
    assert ei.value.code == ErrorCode.WORKSPACE_REQUIRED.value
    assert count(migrated_factory, "channels") == 0


# --------------------------------------------------------------------------- #
# channel_create - agent-created channels (idempotent by name)
# --------------------------------------------------------------------------- #
def test_create_channel_idempotent_and_listable(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    proj = mkdir(tmp_path, "P")

    first = svc.create_channel(project_root=str(proj), name="planning")
    assert first["created"] is True
    assert first["channel"]["name"] == "planning"
    chan_id = first["channel"]["channel_id"]

    # Same name again -> existing channel, created=False, identical id.
    second = svc.create_channel(project_root=str(proj), name="planning")
    assert second["created"] is False
    assert second["channel"]["channel_id"] == chan_id
    assert count(migrated_factory, "channels") == 1  # not duplicated

    # The agent-created channel is listable alongside the seeded 'general'...
    names = {c["name"] for c in svc.list_channels(project_root=str(proj))["channels"]}
    assert names == {"general", "planning"}

    # ...and a message can be posted to it (it now references a real channel).
    msg = svc.create_message(
        project_root=str(proj),
        from_agent_id="a",
        subject="s",
        body="b",
        channel_id=chan_id,
    )
    assert msg["channel_id"] == chan_id


def test_create_channel_trims_name(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    proj = mkdir(tmp_path, "P")

    created = svc.create_channel(project_root=str(proj), name="  planning  ")
    assert created["channel"]["name"] == "planning"
    # The trimmed name collides with the existing one (idempotent, not a dup).
    again = svc.create_channel(project_root=str(proj), name="planning")
    assert again["created"] is False
    assert again["channel"]["channel_id"] == created["channel"]["channel_id"]


def test_create_channel_rejects_blank_name(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    proj = mkdir(tmp_path, "P")
    for bad in (None, "", "   "):
        with pytest.raises(OktoNexusError) as ei:
            svc.create_channel(project_root=str(proj), name=bad)
        assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert count(migrated_factory, "channels") == 0  # nothing created


def test_create_channel_name_length_boundary(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    proj = mkdir(tmp_path, "P")
    # Exactly MAX_CHANNEL_NAME_LEN (64) is accepted (boundary-accept side)...
    ok = svc.create_channel(project_root=str(proj), name="x" * 64)
    assert ok["created"] is True
    assert ok["channel"]["name"] == "x" * 64
    # ...the length check is applied AFTER trimming, so padding does not overflow...
    padded = svc.create_channel(project_root=str(proj), name="  " + "y" * 64 + "  ")
    assert padded["created"] is True
    assert padded["channel"]["name"] == "y" * 64
    # ...but 65 real characters is rejected (boundary-reject side).
    with pytest.raises(OktoNexusError) as ei:
        svc.create_channel(project_root=str(proj), name="z" * 65)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


def test_create_channel_rejects_control_characters(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    proj = mkdir(tmp_path, "P")
    # Interior control chars (so .strip() does not remove them): C0, NUL, DEL, C1.
    for bad in ("bad\nname", "a\tb", "x\x00y", "x\x7fy", "x\x85y"):
        with pytest.raises(OktoNexusError) as ei:
            svc.create_channel(project_root=str(proj), name=bad)
        assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert count(migrated_factory, "channels") == 0  # nothing created


def test_create_channel_idempotent_under_concurrent_race(
    migrated_factory, tmp_config, tmp_path
):
    """A peer winning the UNIQUE(workspace,name) race yields created=False, not DB_ERROR."""
    svc = make_service(migrated_factory, tmp_config, StubClock())
    proj = mkdir(tmp_path, "P")
    ws = resolve_workspace_id(str(proj))
    winner = Channel(
        channel_id="chan_winner",
        workspace_id=ws,
        name="planning",
        created_at="2026-06-07T00:00:00Z",
    )

    class RacingChannels:
        """First read misses (pre-insert); the insert loses; the re-read finds the peer."""

        def __init__(self) -> None:
            self._reads = 0

        def get_by_name(self, uow, *, workspace_id, name):
            self._reads += 1
            return None if self._reads == 1 else winner

        def create(self, uow, **kwargs):
            raise OktoNexusError(ErrorCode.DB_ERROR, "UNIQUE constraint failed: channels")

        def get(self, uow, **kwargs):  # pragma: no cover - unused on this path
            return None

        def list(self, uow, **kwargs):  # pragma: no cover - unused on this path
            return []

    svc._channels = RacingChannels()
    out = svc.create_channel(project_root=str(proj), name="planning")
    assert out["created"] is False
    assert out["channel"]["channel_id"] == "chan_winner"
    assert out["channel"]["name"] == "planning"


def test_create_channel_reraises_unrelated_db_error(
    migrated_factory, tmp_config, tmp_path
):
    """A create failure with no pre-existing row re-raises (not silently swallowed)."""
    svc = make_service(migrated_factory, tmp_config, StubClock())
    proj = mkdir(tmp_path, "P")

    class FailingChannels:
        """No row ever exists, so the create error is NOT an idempotency race."""

        def get_by_name(self, uow, *, workspace_id, name):
            return None

        def create(self, uow, **kwargs):
            raise OktoNexusError(ErrorCode.DB_ERROR, "disk I/O error")

        def get(self, uow, **kwargs):  # pragma: no cover - unused on this path
            return None

        def list(self, uow, **kwargs):  # pragma: no cover - unused on this path
            return []

    svc._channels = FailingChannels()
    with pytest.raises(OktoNexusError) as ei:
        svc.create_channel(project_root=str(proj), name="planning")
    assert ei.value.code == ErrorCode.DB_ERROR.value


def test_create_channel_requires_workspace(migrated_factory, tmp_config):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    with pytest.raises(OktoNexusError) as ei:
        svc.create_channel(project_root=None, name="planning")
    assert ei.value.code == ErrorCode.WORKSPACE_REQUIRED.value


# --------------------------------------------------------------------------- #
# message_create - happy path & persistence fidelity
# --------------------------------------------------------------------------- #
def test_message_create_happy_path_and_round_trip(
    migrated_factory, tmp_config, tmp_path
):
    emitter = FakeEmitter()
    clock = StubClock("2026-06-07T00:00:00Z")
    svc = make_service(migrated_factory, tmp_config, clock, emitter=emitter)
    proj = mkdir(tmp_path, "P")

    data = svc.create_message(
        project_root=str(proj),
        from_agent_id="agentA",
        subject="hello",
        body="a body",
        artifacts=["art-1"],
    )
    assert data["message_id"]
    assert data["workspace_id"] == resolve_workspace_id(str(proj))
    assert isinstance(data["event_id"], int) and data["event_id"] >= 1
    assert data["created_at"] == "2026-06-07T00:00:00Z"
    assert data["artifacts"] == ["art-1"]

    # Exactly one event emitted, carrying the message reference but no body.
    assert len(emitter.events) == 1
    ev = emitter.events[0]
    assert ev["type"] == "message.created"
    # Published on the observable ``workspace`` stream (one of VALID_STREAMS),
    # never the unconsultable legacy ``messages`` stream.
    assert ev["stream"] == "workspace"
    assert ev["workspace_id"] == data["workspace_id"]
    assert ev["payload"]["message_id"] == data["message_id"]
    assert "body" not in ev["payload"]

    # No active-session participants -> a broadcast reaches nobody (a warning),
    # but the message row is still persisted (observable via the event log).
    assert data["recipients"] == [] and data["delivered_count"] == 0
    assert "warning" in data
    assert count(migrated_factory, "messages") == 1


def test_message_create_atomic_single_event_same_commit(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=real_emitter(clock))
    proj = mkdir(tmp_path, "P")

    res = svc.create_message(
        project_root=str(proj),
        from_agent_id="agentA",
        subject="subj",
        body="the body",
    )
    assert count(migrated_factory, "messages") == 1
    assert count(migrated_factory, "events") == 1

    conn = migrated_factory.get_connection()
    try:
        row = conn.execute(
            "SELECT event_id, type, payload FROM events"
        ).fetchone()
    finally:
        conn.close()
    assert row["type"] == "message.created"
    assert int(row["event_id"]) == res["event_id"]
    payload = json.loads(row["payload"])
    assert payload["message_id"] == res["message_id"]
    assert "body" not in payload


def _event_service(factory, config, clock) -> EventService:
    """Wire a real EventService over the same store to consume the log."""
    return EventService(
        connection_factory=factory,
        events=SqliteEventRepo(clock),
        clock=clock,
        config=config,
        agents=SqliteAgentRepo(clock),
    )


def test_message_created_observable_via_event_get_and_wait(
    migrated_factory, tmp_config, tmp_path
):
    # The Channels spec requires message.created to be PUBLISHED on the
    # ``workspace`` stream so consumers of event_get/event_wait observe it
    # WITHOUT widening VALID_STREAMS.
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=real_emitter(clock))
    proj = mkdir(tmp_path, "P")

    created = svc.create_message(
        project_root=str(proj), from_agent_id="agentA", subject="hello", body="b"
    )

    events = _event_service(migrated_factory, tmp_config, clock)

    # event_get on the workspace stream observes the broadcast message.created.
    page = events.event_get(
        project_root=str(proj), agent_id="viewer", stream="workspace"
    )
    msg_events = [e for e in page["events"] if e["type"] == "message.created"]
    assert len(msg_events) == 1
    assert msg_events[0]["event_id"] == created["event_id"]
    assert msg_events[0]["payload"]["message_id"] == created["message_id"]

    # event_wait returns it immediately (event already exists -> not timed out).
    waited = events.event_wait(
        project_root=str(proj), agent_id="viewer", stream="workspace", timeout_seconds=2
    )
    assert waited["timed_out"] is False
    assert any(e["type"] == "message.created" for e in waited["events"])


def test_directed_message_created_visibility_preserved_on_workspace_stream(
    migrated_factory, tmp_config, tmp_path
):
    # Moving to the workspace stream must NOT break visibility: a directed
    # message.created is observable only by the eligible target (can_agent_see_event).
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=real_emitter(clock))
    proj = mkdir(tmp_path, "P")

    # agentB must be a registered identity for a direct target to resolve.
    with migrated_factory.unit_of_work() as uow:
        SqliteAgentRepo(clock).upsert(uow, agent_id="agentB")

    directed = svc.create_message(
        project_root=str(proj),
        from_agent_id="agentA",
        subject="psst",
        body="for B",
        target={"strategy": "direct", "agent_id": "agentB"},
    )
    assert directed["recipients"] == ["agentB"]
    events = _event_service(migrated_factory, tmp_config, clock)

    for_b = events.event_get(project_root=str(proj), agent_id="agentB", stream="workspace")
    assert any(e["event_id"] == directed["event_id"] for e in for_b["events"])

    for_c = events.event_get(project_root=str(proj), agent_id="agentC", stream="workspace")
    assert all(e["event_id"] != directed["event_id"] for e in for_c["events"])


def test_sender_sees_own_directed_message_created_event(
    migrated_factory, tmp_config, tmp_path
):
    """REGRESSION (M2 defect 4 / ADR 0001 "or you are the sender").

    A directed message.created event is ``visibility='eligible'`` with a
    ``direct`` target naming the RECIPIENT - which used to exclude the SENDER
    from observing its own send on the log. The actor carve-out makes the
    sender's own event visible end to end via ``event_get``.
    """
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=real_emitter(clock))
    proj = mkdir(tmp_path, "P")
    with migrated_factory.unit_of_work() as uow:
        SqliteAgentRepo(clock).upsert(uow, agent_id="agentB")

    directed = svc.create_message(
        project_root=str(proj),
        from_agent_id="agentA",
        subject="psst",
        body="for B",
        target={"strategy": "direct", "agent_id": "agentB"},
    )
    events = _event_service(migrated_factory, tmp_config, clock)

    # The SENDER observes its own directed message.created on the log.
    for_sender = events.event_get(
        project_root=str(proj), agent_id="agentA", stream="workspace"
    )
    mine = [e for e in for_sender["events"] if e["event_id"] == directed["event_id"]]
    assert len(mine) == 1
    assert mine[0]["payload"]["message_id"] == directed["message_id"]
    # The carve-out never widens to a third party.
    for_c = events.event_get(
        project_root=str(proj), agent_id="agentC", stream="workspace"
    )
    assert all(e["event_id"] != directed["event_id"] for e in for_c["events"])


def test_message_create_rolls_back_when_event_append_fails(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_service(
        migrated_factory, tmp_config, clock, emitter=RaisingEmitter()
    )
    proj = mkdir(tmp_path, "P")

    with pytest.raises(OktoNexusError) as ei:
        svc.create_message(
            project_root=str(proj),
            from_agent_id="agentA",
            subject="subj",
            body="body",
        )
    assert ei.value.code == ErrorCode.DB_ERROR.value
    # Neither the message row nor anything written in the same uow survives.
    assert count(migrated_factory, "messages") == 0
    assert count(migrated_factory, "events") == 0


# --------------------------------------------------------------------------- #
# message_create - error catalogue
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", [None, "", "   "])
def test_message_create_workspace_required(migrated_factory, tmp_config, bad):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    with pytest.raises(OktoNexusError) as ei:
        svc.create_message(
            project_root=bad, from_agent_id="a", subject="s", body="b"
        )
    assert ei.value.code == ErrorCode.WORKSPACE_REQUIRED.value
    assert count(migrated_factory, "messages") == 0


def test_message_create_workspace_unresolved(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    missing = tmp_path / "does_not_exist" / "child"  # absolute, nonexistent
    with pytest.raises(OktoNexusError) as ei:
        svc.create_message(
            project_root=str(missing), from_agent_id="a", subject="s", body="b"
        )
    assert ei.value.code == ErrorCode.WORKSPACE_UNRESOLVED.value
    assert count(migrated_factory, "messages") == 0


def test_message_create_unknown_channel_not_found(
    migrated_factory, tmp_config, tmp_path
):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    proj = mkdir(tmp_path, "P")
    with pytest.raises(OktoNexusError) as ei:
        svc.create_message(
            project_root=str(proj),
            from_agent_id="a",
            subject="s",
            body="b",
            channel_id="ghost-channel",
        )
    assert ei.value.code == ErrorCode.NOT_FOUND.value
    assert count(migrated_factory, "messages") == 0


def test_message_create_unknown_parent_not_found(
    migrated_factory, tmp_config, tmp_path
):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    proj = mkdir(tmp_path, "P")
    with pytest.raises(OktoNexusError) as ei:
        svc.create_message(
            project_root=str(proj),
            from_agent_id="a",
            subject="s",
            body="b",
            parent_message_id="ghost-parent",
        )
    assert ei.value.code == ErrorCode.NOT_FOUND.value
    assert count(migrated_factory, "messages") == 0


def test_message_create_parent_in_other_workspace_is_not_found(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=real_emitter(clock))
    proj_a = mkdir(tmp_path, "A")
    proj_b = mkdir(tmp_path, "B")

    parent = svc.create_message(
        project_root=str(proj_b), from_agent_id="a", subject="s", body="b"
    )
    # A parent that exists only in workspace B is indistinguishable from absent.
    with pytest.raises(OktoNexusError) as ei:
        svc.create_message(
            project_root=str(proj_a),
            from_agent_id="a",
            subject="s",
            body="b",
            parent_message_id=parent["message_id"],
        )
    assert ei.value.code == ErrorCode.NOT_FOUND.value


def test_message_create_content_too_large_boundary(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=real_emitter(clock))
    proj = mkdir(tmp_path, "P")
    limit = tmp_config.max_inline_bytes  # 65536, inclusive

    # Exactly the limit is accepted.
    ok = svc.create_message(
        project_root=str(proj),
        from_agent_id="a",
        subject="s",
        body="x" * limit,
    )
    assert ok["message_id"]
    assert count(migrated_factory, "messages") == 1

    # One byte over -> CONTENT_TOO_LARGE, nothing more written.
    with pytest.raises(OktoNexusError) as ei:
        svc.create_message(
            project_root=str(proj),
            from_agent_id="a",
            subject="s",
            body="x" * (limit + 1),
        )
    assert ei.value.code == ErrorCode.CONTENT_TOO_LARGE.value
    assert count(migrated_factory, "messages") == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"from_agent_id": "", "subject": "s", "body": "b"},
        {"from_agent_id": "a", "subject": "", "body": "b"},
        {"from_agent_id": "a", "subject": "s", "body": ""},
        {"from_agent_id": "a", "subject": "s", "body": "b", "target": {"strategy": "nope"}},
        {"from_agent_id": "a", "subject": "s", "body": "b", "target": "not-json"},
        {"from_agent_id": "a", "subject": "s", "body": "b", "artifacts": [123]},
    ],
)
def test_message_create_validation_error(migrated_factory, tmp_config, tmp_path, kwargs):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    proj = mkdir(tmp_path, "P")
    with pytest.raises(OktoNexusError) as ei:
        svc.create_message(project_root=str(proj), **kwargs)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert count(migrated_factory, "messages") == 0


# --------------------------------------------------------------------------- #
# Artifacts as references; reply linkage
# --------------------------------------------------------------------------- #
def test_artifacts_stored_as_references_no_inline_blob(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=real_emitter(clock))
    proj = mkdir(tmp_path, "P")

    created = svc.create_message(
        project_root=str(proj),
        from_agent_id="a",
        subject="s",
        body="b",
        artifacts=["art-1", "art-2"],
    )
    assert created["artifacts"] == ["art-1", "art-2"]

    # The message row stores references (a JSON list of ids), never inline bytes.
    conn = migrated_factory.get_connection()
    try:
        row = conn.execute(
            "SELECT artifacts FROM messages WHERE message_id = ?",
            (created["message_id"],),
        ).fetchone()
    finally:
        conn.close()
    assert json.loads(row["artifacts"]) == ["art-1", "art-2"]


def test_reply_linked_to_parent_in_channel(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=real_emitter(clock))
    proj = mkdir(tmp_path, "P")

    channels = svc.list_channels(project_root=str(proj))["channels"]
    general = next(c for c in channels if c["name"] == "general")["channel_id"]

    parent = svc.create_message(
        project_root=str(proj),
        from_agent_id="a",
        subject="topic",
        body="parent",
        channel_id=general,
    )["message_id"]
    reply = svc.create_message(
        project_root=str(proj),
        from_agent_id="b",
        subject="re: topic",
        body="reply",
        channel_id=general,
        parent_message_id=parent,
    )

    assert reply["parent_message_id"] == parent
    # Both rows persisted in the channel, in insertion (== event_id) order.
    ws = resolve_workspace_id(str(proj))
    conn = migrated_factory.get_connection()
    try:
        ids = [
            r["message_id"]
            for r in conn.execute(
                "SELECT message_id FROM messages "
                "WHERE workspace_id = ? AND channel_id = ? ORDER BY rowid ASC",
                (ws, general),
            ).fetchall()
        ]
    finally:
        conn.close()
    assert ids == [parent, reply["message_id"]]

    # A reply whose parent lives in a different channel is rejected.
    architecture = svc.create_channel(
        project_root=str(proj), name="architecture"
    )["channel"]["channel_id"]
    with pytest.raises(OktoNexusError) as ei:
        svc.create_message(
            project_root=str(proj),
            from_agent_id="b",
            subject="re",
            body="x",
            channel_id=architecture,
            parent_message_id=parent,
        )
    assert ei.value.code == ErrorCode.NOT_FOUND.value


# --------------------------------------------------------------------------- #
# MCP tool registration + canonical envelope
# --------------------------------------------------------------------------- #
def test_register_tools_and_envelope(migrated_factory, tmp_config, tmp_path):
    deps = make_deps(migrated_factory, tmp_config, StubClock())
    server = FakeServer()
    register(server, deps)

    # Core slice surface + the S3 clean-break migration shims (message_get/
    # message_list/message_wait answer with a prescriptive MIGRATED envelope).
    # Exact set: the shims are a permanent, deliberate surface — any tool
    # added/removed here must update this assertion (integration-gate decision).
    assert set(server.tools) == {
        "message_create",
        "channel_create",
        "channel_list",
        "message_get",
        "message_list",
        "message_wait",
    }
    assert deps.repos.channels is not None
    assert deps.repos.messages is not None
    assert deps.repos.deliveries is not None  # inbox fan-out store wired
    assert deps.event_emitter is not None  # event append path wired

    proj = mkdir(tmp_path, "P")
    chans = server.tools["channel_list"](project_root=str(proj))
    assert chans["ok"] is True
    assert {c["name"] for c in chans["data"]["channels"]} == {"general"}

    # channel_create through the envelope: success shape + idempotent created flag.
    made = server.tools["channel_create"](project_root=str(proj), name="planning")
    assert made["ok"] is True
    assert made["data"]["created"] is True
    chan_id = made["data"]["channel"]["channel_id"]
    again = server.tools["channel_create"](project_root=str(proj), name="planning")
    assert again["ok"] is True
    assert again["data"]["created"] is False
    assert again["data"]["channel"]["channel_id"] == chan_id
    # A bad name surfaces as an envelope, never raised.
    bad = server.tools["channel_create"](project_root=str(proj), name="  ")
    assert bad["ok"] is False
    assert bad["error"]["code"] == "VALIDATION_ERROR"

    # Failures surface as envelopes, never raised.
    missing_ws = server.tools["message_create"](
        project_root="", from_agent_id="a", subject="s", body="b"
    )
    assert missing_ws["ok"] is False
    assert missing_ws["error"]["code"] == "WORKSPACE_REQUIRED"

    created = server.tools["message_create"](
        project_root=str(proj), from_agent_id="a", subject="s", body="b"
    )
    assert created["ok"] is True
    assert isinstance(created["data"]["event_id"], int)
    # No active-session participants -> broadcast reaches nobody (warning),
    # surfaced in the envelope's data (reading is the inbox slice's job).
    assert created["data"]["recipients"] == []
    assert created["data"]["delivered_count"] == 0

    # A direct target to an UNKNOWN agent surfaces as a NOT_FOUND envelope.
    unknown = server.tools["message_create"](
        project_root=str(proj),
        from_agent_id="a",
        subject="s",
        body="b",
        target={"strategy": "direct", "agent_id": "ghost"},
    )
    assert unknown["ok"] is False and unknown["error"]["code"] == "NOT_FOUND"


def test_build_service_reuses_existing_repos(migrated_factory, tmp_config):
    clock = StubClock()
    deps = make_deps(migrated_factory, tmp_config, clock)
    existing = SqliteChannelRepo(clock)
    deps.repos.channels = existing
    build_service(deps)
    assert deps.repos.channels is existing  # not overwritten
    assert deps.repos.messages is not None  # filled in
    assert deps.event_emitter is not None


# --------------------------------------------------------------------------- #
# Concurrency
# --------------------------------------------------------------------------- #
def test_concurrent_message_create_strictly_increasing_event_ids(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=real_emitter(clock))
    proj = mkdir(tmp_path, "P")
    n = 10
    msg_ids: list[str] = []
    event_ids: list[int] = []
    lock = threading.Lock()
    barrier = threading.Barrier(n)

    def worker(i: int) -> None:
        barrier.wait()
        out = retry_db(
            lambda: svc.create_message(
                project_root=str(proj),
                from_agent_id=f"a{i}",
                subject=f"s{i}",
                body=f"b{i}",
            )
        )
        with lock:
            msg_ids.append(out["message_id"])
            event_ids.append(out["event_id"])

    with ThreadPoolExecutor(max_workers=n) as ex:
        for f in [ex.submit(worker, i) for i in range(n)]:
            f.result()

    assert len(msg_ids) == n
    assert len(set(msg_ids)) == n  # distinct message ids
    assert len(set(event_ids)) == n  # distinct, never reused
    assert min(event_ids) >= 1
    assert sorted(event_ids) == sorted(set(event_ids))  # strictly increasing set
    assert count(migrated_factory, "messages") == n
    assert count(migrated_factory, "events") == n


def test_concurrent_writers_distinct_workspaces_no_leak(
    migrated_factory, tmp_config, tmp_path
):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=real_emitter(clock))
    proj_a = mkdir(tmp_path, "A")
    proj_b = mkdir(tmp_path, "B")
    ws_a = resolve_workspace_id(str(proj_a))
    ws_b = resolve_workspace_id(str(proj_b))
    per = 6
    roots = [str(proj_a)] * per + [str(proj_b)] * per
    barrier = threading.Barrier(len(roots))

    def worker(idx: int, root: str) -> None:
        barrier.wait()
        retry_db(
            lambda: svc.create_message(
                project_root=root, from_agent_id=f"a{idx}", subject="s", body="b"
            )
        )

    with ThreadPoolExecutor(max_workers=len(roots)) as ex:
        for f in [ex.submit(worker, i, r) for i, r in enumerate(roots)]:
            f.result()

    # Each workspace holds exactly its own messages - zero cross-workspace leak.
    conn = migrated_factory.get_connection()
    try:
        rows_a = conn.execute(
            "SELECT message_id FROM messages WHERE workspace_id = ?", (ws_a,)
        ).fetchall()
        rows_b = conn.execute(
            "SELECT message_id FROM messages WHERE workspace_id = ?", (ws_b,)
        ).fetchall()
    finally:
        conn.close()
    assert len(rows_a) == per
    assert len(rows_b) == per
    assert count(migrated_factory, "messages") == 2 * per


def test_message_create_surfaces_implicit_workspace_creation(
    migrated_factory, tmp_config, tmp_path
):
    """M2 extra: the first send into a never-seen project_root flags the upsert.

    A mistyped path used to materialise a phantom workspace SILENTLY. The first
    ``message_create`` that creates the workspace row reports
    ``workspace_created: true``; sends into an already-known workspace carry no
    such key.
    """
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=real_emitter(clock))
    proj = mkdir(tmp_path, "P")

    first = svc.create_message(
        project_root=str(proj), from_agent_id="a", subject="s", body="b"
    )
    assert first["workspace_created"] is True  # the row did not exist before

    second = svc.create_message(
        project_root=str(proj), from_agent_id="a", subject="s2", body="b2"
    )
    assert "workspace_created" not in second  # known workspace -> no flag
    assert count(migrated_factory, "workspaces") == 1


def test_message_create_no_workspace_created_flag_after_explicit_resolve(
    migrated_factory, tmp_config, tmp_path
):
    """A workspace pre-created by another use case is never re-flagged."""
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=real_emitter(clock))
    proj = mkdir(tmp_path, "P")
    # channel_list upserts the workspace row first (any prior touch counts).
    svc.list_channels(project_root=str(proj))

    sent = svc.create_message(
        project_root=str(proj), from_agent_id="a", subject="s", body="b"
    )
    assert "workspace_created" not in sent


def test_message_create_touches_author_last_seen(
    migrated_factory, tmp_config, tmp_path
):
    # Sending a message stamps the author's agents.last_seen_at (best-effort:
    # only for a registered author).
    clock = StubClock("2026-06-07T00:00:00Z")
    agents = SqliteAgentRepo(clock)
    svc = make_service(migrated_factory, tmp_config, clock, agents=agents)
    proj = mkdir(tmp_path, "P")
    with migrated_factory.unit_of_work() as uow:
        agents.upsert(uow, agent_id="author")

    clock.set("2026-06-07T00:05:00Z")
    svc.create_message(
        project_root=str(proj), from_agent_id="author", subject="s", body="b"
    )
    with migrated_factory.unit_of_work() as uow:
        assert agents.get(uow, "author").last_seen_at == "2026-06-07T00:05:00Z"
