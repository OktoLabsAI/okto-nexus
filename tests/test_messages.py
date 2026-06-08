"""Tests for the Channels & Messages slice.

Hexagonal unit/integration tests: the application service is exercised over the
real SQLite adapters (via ``migrated_factory``), while the Event Log
``EventEmitter`` port (owned by another slice) is supplied either as a fake (to
inspect emissions) or as the real ``SqliteEventEmitter`` (to assert true,
monotonic ``event_id`` assignment and atomic same-commit coupling). Covers the
happy paths, the canonical error catalogue (WORKSPACE_REQUIRED /
WORKSPACE_UNRESOLVED / VALIDATION_ERROR / CONTENT_TOO_LARGE / NOT_FOUND), the
64KB inclusive inline boundary, channel seeding, parent/reply linkage, imported
routing visibility (directed vs broadcast), cursor pagination, the MCP tool
envelope, cross-workspace isolation, atomic rollback when the event append
fails, and concurrency (parallel writers with strictly increasing event_ids and
no cross-workspace leakage).
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
    SqliteWorkspaceRepo,
)
from okto_nexus.adapters.outbound.sqlite.messages_repo import (
    SqliteChannelRepo,
    SqliteMessageRepo,
)
from okto_nexus.application.messages import MessageService
from okto_nexus.application.ports import Repos
from okto_nexus.domain.ids import resolve_workspace_id
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
def test_channel_list_seeds_three_channels(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock("2026-06-07T00:00:00Z"))
    proj = mkdir(tmp_path, "P")

    out = svc.list_channels(project_root=str(proj))
    channels = out["channels"]
    assert {c["name"] for c in channels} == {"general", "architecture", "code-review"}
    ws = resolve_workspace_id(str(proj))
    for c in channels:
        assert c["channel_id"]
        assert c["workspace_id"] == ws
        assert c["created_at"] == "2026-06-07T00:00:00Z"

    # Idempotent: a second call does not duplicate the seeded channels.
    again = svc.list_channels(project_root=str(proj))
    assert {c["channel_id"] for c in again["channels"]} == {
        c["channel_id"] for c in channels
    }
    assert count(migrated_factory, "channels") == 3


def test_channel_list_requires_workspace(migrated_factory, tmp_config):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    with pytest.raises(OktoNexusError) as ei:
        svc.list_channels(project_root=None)
    assert ei.value.code == ErrorCode.WORKSPACE_REQUIRED.value
    assert count(migrated_factory, "channels") == 0


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
    assert ev["workspace_id"] == data["workspace_id"]
    assert ev["payload"]["message_id"] == data["message_id"]
    assert "body" not in ev["payload"]

    # The persisted row corresponds to the returned fields.
    got = svc.get_message(project_root=str(proj), message_id=data["message_id"])
    assert got == {k: v for k, v in data.items() if k != "event_id"}
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
# message_get - workspace scoping
# --------------------------------------------------------------------------- #
def test_message_get_is_workspace_scoped(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=real_emitter(clock))
    proj_a = mkdir(tmp_path, "A")
    proj_b = mkdir(tmp_path, "B")

    created = svc.create_message(
        project_root=str(proj_a), from_agent_id="a", subject="s", body="b"
    )
    mid = created["message_id"]

    assert svc.get_message(project_root=str(proj_a), message_id=mid)["message_id"] == mid

    # The same message_id under a different workspace is NOT_FOUND.
    with pytest.raises(OktoNexusError) as ei:
        svc.get_message(project_root=str(proj_b), message_id=mid)
    assert ei.value.code == ErrorCode.NOT_FOUND.value


def test_message_get_missing_is_not_found(migrated_factory, tmp_config, tmp_path):
    svc = make_service(migrated_factory, tmp_config, StubClock())
    proj = mkdir(tmp_path, "P")
    with pytest.raises(OktoNexusError) as ei:
        svc.get_message(project_root=str(proj), message_id="ghost")
    assert ei.value.code == ErrorCode.NOT_FOUND.value


# --------------------------------------------------------------------------- #
# message_list - pagination & ordering
# --------------------------------------------------------------------------- #
def test_message_list_cursor_pagination_ordered(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=real_emitter(clock))
    proj = mkdir(tmp_path, "P")

    created_ids = [
        svc.create_message(
            project_root=str(proj), from_agent_id="a", subject=f"s{i}", body=f"b{i}"
        )["message_id"]
        for i in range(5)
    ]

    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        page = svc.list_messages(project_root=str(proj), cursor=cursor, limit=2)
        seen.extend(m["message_id"] for m in page["messages"])
        pages += 1
        if not page["has_more"]:
            assert page["next_cursor"] is None
            break
        assert page["next_cursor"] is not None
        cursor = page["next_cursor"]
        assert pages < 10  # guard against runaway loops

    # Strictly ascending creation (== event_id) order, no dups, no gaps.
    assert seen == created_ids
    assert len(seen) == len(set(seen))


# --------------------------------------------------------------------------- #
# Imported routing visibility (directed vs broadcast)
# --------------------------------------------------------------------------- #
def test_directed_visibility_in_list_and_get(migrated_factory, tmp_config, tmp_path):
    clock = StubClock()
    svc = make_service(migrated_factory, tmp_config, clock, emitter=real_emitter(clock))
    proj = mkdir(tmp_path, "P")

    bcast = svc.create_message(
        project_root=str(proj), from_agent_id="a", subject="hi", body="all"
    )["message_id"]
    directed = svc.create_message(
        project_root=str(proj),
        from_agent_id="a",
        subject="psst",
        body="for B",
        target={"strategy": "direct", "agent_id": "agentB"},
    )["message_id"]

    # agentB sees both; agentC sees only the broadcast.
    for_b = svc.list_messages(project_root=str(proj), viewer_agent_id="agentB")
    for_c = svc.list_messages(project_root=str(proj), viewer_agent_id="agentC")
    assert {m["message_id"] for m in for_b["messages"]} == {bcast, directed}
    assert {m["message_id"] for m in for_c["messages"]} == {bcast}

    # message_get honours the same predicate.
    assert (
        svc.get_message(
            project_root=str(proj), message_id=directed, viewer_agent_id="agentB"
        )["message_id"]
        == directed
    )
    with pytest.raises(OktoNexusError) as ei:
        svc.get_message(
            project_root=str(proj), message_id=directed, viewer_agent_id="agentC"
        )
    assert ei.value.code == ErrorCode.NOT_FOUND.value
    # The broadcast remains visible to agentC.
    assert (
        svc.get_message(
            project_root=str(proj), message_id=bcast, viewer_agent_id="agentC"
        )["message_id"]
        == bcast
    )


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
    got = svc.get_message(project_root=str(proj), message_id=created["message_id"])
    assert got["artifacts"] == ["art-1", "art-2"]

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
    listed = svc.list_messages(project_root=str(proj), channel_id=general)
    ids = [m["message_id"] for m in listed["messages"]]
    assert ids == [parent, reply["message_id"]]  # both present, event-ordered

    # A reply whose parent lives in a different channel is rejected.
    architecture = next(c for c in channels if c["name"] == "architecture")[
        "channel_id"
    ]
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

    assert set(server.tools) == {
        "message_create",
        "message_get",
        "message_list",
        "channel_list",
    }
    assert deps.repos.channels is not None
    assert deps.repos.messages is not None
    assert deps.event_emitter is not None  # event append path wired

    proj = mkdir(tmp_path, "P")
    chans = server.tools["channel_list"](project_root=str(proj))
    assert chans["ok"] is True
    assert {c["name"] for c in chans["data"]["channels"]} == {
        "general",
        "architecture",
        "code-review",
    }

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
    mid = created["data"]["message_id"]
    assert isinstance(created["data"]["event_id"], int)

    got = server.tools["message_get"](project_root=str(proj), message_id=mid)
    assert got["ok"] is True and got["data"]["message_id"] == mid

    missing = server.tools["message_get"](project_root=str(proj), message_id="ghost")
    assert missing["ok"] is False and missing["error"]["code"] == "NOT_FOUND"

    listed = server.tools["message_list"](project_root=str(proj))
    assert listed["ok"] is True
    assert [m["message_id"] for m in listed["data"]["messages"]] == [mid]


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

    list_a = svc.list_messages(project_root=str(proj_a), limit=200)["messages"]
    list_b = svc.list_messages(project_root=str(proj_b), limit=200)["messages"]
    assert len(list_a) == per
    assert len(list_b) == per
    assert all(m["workspace_id"] == ws_a for m in list_a)  # zero leakage A
    assert all(m["workspace_id"] == ws_b for m in list_b)  # zero leakage B
    assert count(migrated_factory, "messages") == 2 * per
