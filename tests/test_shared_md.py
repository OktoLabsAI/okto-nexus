"""Tests for the shared.md rendering slice (``shared_md_render``).

Hexagonal unit tests: the application service is exercised over the REAL
filesystem renderer adapter, while every repository port is a fake (the sibling
Task / Handoff / Event / Identity slices are imported as contracts, not
concrete implementations). One integration test also drives the real
``SqliteWorkspaceRepo`` over ``migrated_factory`` to confirm the committed-state
read path.

Coverage: happy path + envelope shape, deterministic byte-identical overwrite,
fixed four-section order, newest-first event cap (60 -> 50) and default cap,
the explicit relevance predicate (active sessions, open tasks, open/claimed
non-expired handoffs, workspace-bound agents), empty workspace, strict
cross-workspace isolation, atomic temp-file + os.replace under concurrent
renders, the full canonical error catalog (WORKSPACE_REQUIRED / VALIDATION_ERROR
/ NOT_FOUND / RENDER_ERROR / DB_ERROR) with NO file written on error, the
derived-view (never-read-back) invariant, and the MCP tool registration +
envelope.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.mcp.tools.shared_md import build_service, register
from okto_nexus.adapters.outbound.sharedmd import renderer as renderer_module
from okto_nexus.adapters.outbound.sharedmd.renderer import (
    SHARED_MD_FILENAME,
    WORKSPACES_DIRNAME,
    FileSystemSharedMdRenderer,
)
from okto_nexus.adapters.outbound.sqlite.events_repo import SqliteEventRepo
from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteWorkspaceRepo
from okto_nexus.application.ports import Repos
from okto_nexus.application.shared_md import (
    DEFAULT_LIMIT_EVENTS,
    DEFAULT_MAX_LIMIT_EVENTS,
    SECTION_COUNT,
    SharedMdService,
    SharedMdView,
)
from okto_nexus.domain.base import iso_to_epoch
from okto_nexus.domain.models import Agent, Event, Handoff, Session, Task, Workspace
from okto_nexus.errors import ErrorCode, OktoNexusError

WS_A = "a" * 64
WS_B = "b" * 64
WS_UNKNOWN = "c" * 64

SECTION_HEADINGS = (
    "## Agents & Sessions",
    "## Open Tasks",
    "## Open Handoffs",
    "## Recent Events",
)


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #
class StubClock:
    def __init__(self, iso: str = "2026-06-07T00:00:00Z") -> None:
        self._iso = iso

    def now_iso(self) -> str:
        return self._iso

    def now_epoch(self) -> float:
        return iso_to_epoch(self._iso)

    def set(self, iso: str) -> None:
        self._iso = iso


class FakeUoW:
    connection = None

    def __enter__(self) -> "FakeUoW":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def commit(self) -> None:  # pragma: no cover - no-op
        pass

    def rollback(self) -> None:  # pragma: no cover - no-op
        pass


class FakeConnectionFactory:
    def unit_of_work(self) -> FakeUoW:
        return FakeUoW()

    def get_connection(self):  # pragma: no cover - not used by fakes
        raise NotImplementedError


class FakeWorkspaceRepo:
    def __init__(self, existing: set[str] | None = None, raises: bool = False) -> None:
        self._existing = set(existing or set())
        self._raises = raises

    def get(self, uow, workspace_id: str):
        if self._raises:
            raise OktoNexusError(
                ErrorCode.DB_ERROR, "boom", {"workspace_id": workspace_id}
            )
        if workspace_id in self._existing:
            return Workspace(workspace_id=workspace_id, created_at="2026-06-07T00:00:00Z")
        return None

    def upsert(self, uow, *, workspace_id, **kw):  # pragma: no cover - unused
        self._existing.add(workspace_id)
        return Workspace(workspace_id=workspace_id, created_at="2026-06-07T00:00:00Z")


class FakeAgentRepo:
    def __init__(self, agents: list[Agent] | None = None) -> None:
        self._by_id = {a.agent_id: a for a in (agents or [])}

    def get(self, uow, agent_id: str):
        return self._by_id.get(agent_id)

    def upsert(self, uow, *, agent_id, **kw):  # pragma: no cover - unused
        raise NotImplementedError


class FakeSessionRepo:
    def __init__(self, sessions: list[Session] | None = None) -> None:
        self._sessions = list(sessions or [])

    def list(self, uow, *, workspace_id: str, status: str | None = None):
        rows = [s for s in self._sessions if s.workspace_id == workspace_id]
        if status is not None:
            rows = [s for s in rows if s.status == status]
        return rows


class FakeTaskRepo:
    def __init__(self, tasks: list[Task] | None = None) -> None:
        self._tasks = list(tasks or [])

    def list(self, uow, *, workspace_id: str, status: str | None = None):
        rows = [t for t in self._tasks if t.workspace_id == workspace_id]
        if status is not None:
            rows = [t for t in rows if t.status == status]
        return rows


class FakeHandoffRepo:
    def __init__(self, handoffs: list[Handoff] | None = None) -> None:
        self._handoffs = list(handoffs or [])

    def list(self, uow, *, workspace_id: str, status: str | None = None, target=None):
        rows = [h for h in self._handoffs if h.workspace_id == workspace_id]
        if status is not None:
            rows = [h for h in rows if h.status == status]
        if target is not None:
            rows = [h for h in rows if h.target == target]
        return rows


class FakeEventRepo:
    """Mimics the canonical EventRepo CONTRACT (kept honest by
    ``tests/test_ports_contract.py``, which runs the same scenarios against
    this fake and the real SQLite adapter): oldest-first, cursor + limit,
    all-streams when ``stream is None``, and the fail-closed emit-vocabulary
    gate on ``append`` (same domain validator as the adapter)."""

    def __init__(self, events: list[Event] | None = None) -> None:
        self._events = list(events or [])

    def append(
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
        from okto_nexus.domain.events import validate_emit_vocabulary

        validate_emit_vocabulary(stream=stream, type=type, visibility=visibility)
        event_id = max((e.event_id or 0 for e in self._events), default=0) + 1
        self._events.append(
            Event(
                workspace_id=workspace_id,
                stream=stream,
                type=type,
                created_at="2026-06-07T00:00:00Z",
                event_id=event_id,
                actor_agent_id=actor_agent_id,
                payload=dict(payload) if payload else None,
                visibility=visibility,
                target=target,
            )
        )
        return event_id

    def list_after(
        self, uow, *, workspace_id, stream=None, cursor=0, limit=100, filters=None
    ):
        rows = [
            e
            for e in self._events
            if e.workspace_id == workspace_id
            and (stream is None or e.stream == stream)
            and (e.event_id or 0) > cursor
        ]
        rows.sort(key=lambda e: e.event_id)
        return rows[:limit]


class FakeServer:
    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #
def make_event(eid: int, ws: str = WS_A, stream: str = "workspace", typ: str = "x") -> Event:
    return Event(
        workspace_id=ws,
        stream=stream,
        type=typ,
        created_at="2026-06-07T00:00:00Z",
        event_id=eid,
        actor_agent_id="agent-1",
    )


def make_service(
    home_dir,
    *,
    existing=(WS_A,),
    workspaces=None,
    agents=None,
    sessions=None,
    tasks=None,
    handoffs=None,
    events=None,
    clock=None,
    max_limit_events=DEFAULT_MAX_LIMIT_EVENTS,
) -> SharedMdService:
    return SharedMdService(
        connection_factory=FakeConnectionFactory(),
        workspaces=workspaces or FakeWorkspaceRepo(set(existing)),
        renderer=FileSystemSharedMdRenderer(home_dir=home_dir),
        clock=clock or StubClock(),
        agents=FakeAgentRepo(agents) if agents is not None else FakeAgentRepo([]),
        sessions=FakeSessionRepo(sessions) if sessions is not None else FakeSessionRepo([]),
        tasks=FakeTaskRepo(tasks) if tasks is not None else FakeTaskRepo([]),
        handoffs=FakeHandoffRepo(handoffs) if handoffs is not None else FakeHandoffRepo([]),
        events=FakeEventRepo(events) if events is not None else FakeEventRepo([]),
        max_limit_events=max_limit_events,
    )


def shared_md_path(home_dir, ws: str) -> Path:
    return Path(home_dir) / WORKSPACES_DIRNAME / ws / SHARED_MD_FILENAME


def populated(ws: str = WS_A):
    agents = [Agent(agent_id="agent-1", created_at="t", role="builder")]
    sessions = [
        Session("ses-1", "agent-1", ws, "active", "2026-06-07T00:00:00Z"),
        Session("ses-closed", "agent-1", ws, "closed", "2026-06-07T00:00:00Z"),
    ]
    tasks = [
        Task("task-open", ws, "Do it", "in_progress", "2026-06-07T00:00:00Z"),
        Task("task-done", ws, "Finished", "done", "2026-06-07T00:00:00Z"),
    ]
    handoffs = [
        Handoff("ho-open", ws, "open", "2026-06-07T00:00:00Z", target="agent-2"),
        Handoff(
            "ho-claimed",
            ws,
            "claimed",
            "2026-06-07T00:00:00Z",
            claimed_by="agent-3",
            lease_expires_at="2026-06-07T01:00:00Z",
        ),
    ]
    events = [make_event(i, ws=ws) for i in range(1, 6)]
    return agents, sessions, tasks, handoffs, events


# --------------------------------------------------------------------------- #
# Happy path + envelope shape
# --------------------------------------------------------------------------- #
def test_happy_path_returns_canonical_data(tmp_path):
    agents, sessions, tasks, handoffs, events = populated()
    svc = make_service(
        tmp_path / "home",
        agents=agents,
        sessions=sessions,
        tasks=tasks,
        handoffs=handoffs,
        events=events,
        clock=StubClock("2026-06-07T12:00:00Z"),
    )
    data = svc.shared_md_render(workspace_id=WS_A)

    target = shared_md_path(tmp_path / "home", WS_A)
    assert data["path"] == str(target)
    assert data["workspace_id"] == WS_A
    assert data["bytes_written"] > 0
    assert data["sections_rendered"] == SECTION_COUNT == 4
    assert data["limit_events"] == 50
    # generated_at parses as UTC ISO-8601.
    parsed = datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00"))
    assert parsed.tzinfo is not None

    on_disk = target.read_bytes()
    assert len(on_disk) == data["bytes_written"]
    assert target.is_file()


def test_default_limit_events_is_50(tmp_path):
    svc = make_service(tmp_path / "home")
    data = svc.shared_md_render(workspace_id=WS_A)
    assert data["limit_events"] == DEFAULT_LIMIT_EVENTS == 50


# --------------------------------------------------------------------------- #
# Deterministic full overwrite
# --------------------------------------------------------------------------- #
def test_two_renders_are_byte_identical_no_append(tmp_path):
    agents, sessions, tasks, handoffs, events = populated()
    svc = make_service(
        tmp_path / "home",
        agents=agents,
        sessions=sessions,
        tasks=tasks,
        handoffs=handoffs,
        events=events,
    )
    d1 = svc.shared_md_render(workspace_id=WS_A)
    bytes1 = shared_md_path(tmp_path / "home", WS_A).read_bytes()
    d2 = svc.shared_md_render(workspace_id=WS_A)
    bytes2 = shared_md_path(tmp_path / "home", WS_A).read_bytes()

    assert bytes1 == bytes2  # byte-identical, full overwrite (never appended)
    assert d1["bytes_written"] == d2["bytes_written"] == len(bytes2)


# --------------------------------------------------------------------------- #
# Fixed four-section order
# --------------------------------------------------------------------------- #
def test_four_sections_in_fixed_order(tmp_path):
    agents, sessions, tasks, handoffs, events = populated()
    svc = make_service(
        tmp_path / "home",
        agents=agents,
        sessions=sessions,
        tasks=tasks,
        handoffs=handoffs,
        events=events,
    )
    svc.shared_md_render(workspace_id=WS_A)
    text = shared_md_path(tmp_path / "home", WS_A).read_text(encoding="utf-8")

    indices = [text.index(h) for h in SECTION_HEADINGS]
    assert indices == sorted(indices)  # exact fixed order
    assert len(indices) == 4


# --------------------------------------------------------------------------- #
# Newest-first event cap
# --------------------------------------------------------------------------- #
def _event_ids_in_order(text: str) -> list[int]:
    ids: list[int] = []
    for line in text.splitlines():
        if line.startswith("- #"):
            ids.append(int(line[3:].split(" ", 1)[0]))
    return ids


def test_event_cap_newest_first_60_events_limit_50(tmp_path):
    events = [make_event(i) for i in range(1, 61)]  # 60 events, ids 1..60
    svc = make_service(tmp_path / "home", events=events)
    svc.shared_md_render(workspace_id=WS_A, limit_events=50)
    text = shared_md_path(tmp_path / "home", WS_A).read_text(encoding="utf-8")

    ids = _event_ids_in_order(text)
    assert len(ids) == 50
    assert ids == list(range(60, 10, -1))  # 60,59,...,11 newest-first
    assert ids[0] == 60
    assert 10 not in ids and 11 in ids


def test_event_cap_default_is_50(tmp_path):
    events = [make_event(i) for i in range(1, 61)]
    svc = make_service(tmp_path / "home", events=events)
    svc.shared_md_render(workspace_id=WS_A)  # omitted -> default 50
    text = shared_md_path(tmp_path / "home", WS_A).read_text(encoding="utf-8")
    assert len(_event_ids_in_order(text)) == 50


def test_event_paging_across_page_boundary(tmp_path, monkeypatch):
    # Force tiny pages to exercise the cursor-paging drain logic.
    monkeypatch.setattr(
        "okto_nexus.application.shared_md._EVENT_PAGE_SIZE", 7, raising=True
    )
    events = [make_event(i) for i in range(1, 41)]  # 40 events across many pages
    svc = make_service(tmp_path / "home", events=events)
    svc.shared_md_render(workspace_id=WS_A, limit_events=10)
    text = shared_md_path(tmp_path / "home", WS_A).read_text(encoding="utf-8")
    assert _event_ids_in_order(text) == list(range(40, 30, -1))


# --------------------------------------------------------------------------- #
# Explicit relevance predicate
# --------------------------------------------------------------------------- #
def test_relevance_predicate_filters(tmp_path):
    agents, sessions, tasks, handoffs, events = populated()
    svc = make_service(
        tmp_path / "home",
        agents=agents,
        sessions=sessions,
        tasks=tasks,
        handoffs=handoffs,
        events=events,
        clock=StubClock("2026-06-07T00:30:00Z"),  # before the claimed lease expiry
    )
    svc.shared_md_render(workspace_id=WS_A)
    text = shared_md_path(tmp_path / "home", WS_A).read_text(encoding="utf-8")

    # Sessions: only active.
    assert "ses-1" in text
    assert "ses-closed" not in text
    # Tasks: not in {done, cancelled}.
    assert "task-open" in text
    assert "task-done" not in text
    # Handoffs: open + claimed (non-expired) shown.
    assert "ho-open" in text
    assert "ho-claimed" in text
    # Agent bound via a session is present.
    assert "agent-1" in text


def test_expired_claimed_handoff_excluded(tmp_path):
    handoffs = [
        Handoff(
            "ho-expired",
            WS_A,
            "claimed",
            "2026-06-07T00:00:00Z",
            claimed_by="agent-9",
            lease_expires_at="2026-06-07T00:00:10Z",
        ),
        Handoff("ho-live", WS_A, "open", "2026-06-07T00:00:00Z"),
        Handoff("ho-done", WS_A, "done", "2026-06-07T00:00:00Z"),
    ]
    svc = make_service(
        tmp_path / "home",
        handoffs=handoffs,
        clock=StubClock("2026-06-07T01:00:00Z"),  # well past the lease
    )
    svc.shared_md_render(workspace_id=WS_A)
    text = shared_md_path(tmp_path / "home", WS_A).read_text(encoding="utf-8")
    assert "ho-expired" not in text  # claimed but expired
    assert "ho-done" not in text  # not an open status
    assert "ho-live" in text


# --------------------------------------------------------------------------- #
# Empty workspace
# --------------------------------------------------------------------------- #
def test_empty_workspace_renders_four_empty_sections(tmp_path):
    svc = make_service(tmp_path / "home")
    data = svc.shared_md_render(workspace_id=WS_A)
    assert data["sections_rendered"] == 4
    assert data["bytes_written"] > 0
    text = shared_md_path(tmp_path / "home", WS_A).read_text(encoding="utf-8")
    for heading in SECTION_HEADINGS:
        assert heading in text
    # Each list section rendered an explicit empty placeholder.
    assert text.count("_(none)_") >= 4


# --------------------------------------------------------------------------- #
# Cross-workspace isolation
# --------------------------------------------------------------------------- #
def test_cross_workspace_isolation(tmp_path):
    a_sessions = [Session("ses-A", "agent-A", WS_A, "active", "2026-06-07T00:00:00Z")]
    b_sessions = [Session("ses-B", "agent-B", WS_B, "active", "2026-06-07T00:00:00Z")]
    a_tasks = [Task("task-A", WS_A, "A task", "open", "2026-06-07T00:00:00Z")]
    b_tasks = [Task("task-B", WS_B, "B task", "open", "2026-06-07T00:00:00Z")]
    a_events = [make_event(1, ws=WS_A, typ="a.evt")]
    b_events = [make_event(2, ws=WS_B, typ="b.evt")]

    svc = make_service(
        tmp_path / "home",
        existing=(WS_A, WS_B),
        agents=[
            Agent(agent_id="agent-A", created_at="t"),
            Agent(agent_id="agent-B", created_at="t"),
        ],
        sessions=a_sessions + b_sessions,
        tasks=a_tasks + b_tasks,
        events=a_events + b_events,
    )
    svc.shared_md_render(workspace_id=WS_A)
    svc.shared_md_render(workspace_id=WS_B)

    text_a = shared_md_path(tmp_path / "home", WS_A).read_text(encoding="utf-8")
    text_b = shared_md_path(tmp_path / "home", WS_B).read_text(encoding="utf-8")

    for b_token in ("ses-B", "agent-B", "task-B", "b.evt", WS_B):
        assert b_token not in text_a
    for a_token in ("ses-A", "agent-A", "task-A", "a.evt", WS_A):
        assert a_token not in text_b


# --------------------------------------------------------------------------- #
# Agent-controlled values cannot corrupt the markdown structure
# --------------------------------------------------------------------------- #
def test_format_sanitizes_agent_controlled_fields_no_structural_injection(tmp_path):
    """Newlines/control chars and backticks inside agent-controlled values are
    a PRESENTATION hazard: a raw interpolation would let an id/title start a
    heading at column 0, split an entry across lines, or close the wrapping
    code-span. format() must keep every entry on ONE logical line with the
    payload rendered inline (values are stored verbatim; only the view is
    sanitised)."""
    renderer = FileSystemSharedMdRenderer(home_dir=tmp_path / "home")
    inj = "\n## Injected"
    view = SharedMdView(
        workspace_id=WS_A,
        limit_events=50,
        agents=[
            Agent(agent_id=f"agent-`pwn`{inj}", created_at="t", role=f"role `r`{inj}")
        ],
        sessions=[
            Session(f"ses{inj}", f"agent-`pwn`{inj}", WS_A, f"active{inj}", "t")
        ],
        tasks=[Task(f"task{inj}", WS_A, f"Title `code`{inj}", f"open{inj}", "t")],
        handoffs=[
            Handoff(
                f"ho{inj}",
                WS_A,
                f"open{inj}",
                "t",
                task_id=f"tid{inj}",
                target=f"tgt `t`{inj}",
                visibility="public",
                claimed_by=f"cb{inj}",
            )
        ],
        events=[
            Event(
                workspace_id=WS_A,
                stream=f"workspace{inj}",
                type=f"x.y`z`{inj}",
                created_at="t",
                event_id=1,
                actor_agent_id=f"actor{inj}",
            )
        ],
    )
    text = renderer.format(view)
    lines = text.splitlines()

    # No injected heading ever lands at column 0...
    assert not any(line.startswith("## Injected") for line in lines)
    # ...the only headings are the renderer's own fixed skeleton.
    assert [line for line in lines if line.startswith("#")] == [
        "# Okto Nexus — shared.md",
        "## Agents & Sessions",
        "### Agents",
        "### Active Sessions",
        "## Open Tasks",
        "## Open Handoffs",
        "## Recent Events",
    ]

    # Each of the 5 seeded entries renders as exactly ONE logical line, with
    # the would-be heading flattened inline into its own entry.
    entries = [line for line in lines if line.startswith("- ")]
    assert len(entries) == 5
    assert all("## Injected" in line for line in entries)

    # Backticks inside values are neutralised, so the values' code-spans
    # cannot escape (the wrapper backticks are the renderer's own).
    for evil in ("`pwn`", "`code`", "`r`", "`t`", "`z`"):
        assert evil not in text
        assert evil.replace("`", "'") in text


def test_format_clean_values_render_byte_identical_after_sanitization(tmp_path):
    """Sanitisation is a no-op for ordinary ids/titles: two formats of the same
    clean view stay byte-identical (the determinism contract survives)."""
    renderer = FileSystemSharedMdRenderer(home_dir=tmp_path / "home")
    agents, sessions, tasks, handoffs, events = populated()
    view = SharedMdView(
        workspace_id=WS_A,
        limit_events=50,
        agents=agents,
        sessions=sessions,
        tasks=tasks,
        handoffs=handoffs,
        events=events,
    )
    text = renderer.format(view)
    assert renderer.format(view) == text
    assert "agent-1" in text and "Do it" in text  # values pass through verbatim


# --------------------------------------------------------------------------- #
# Atomic write under concurrency
# --------------------------------------------------------------------------- #
def test_concurrent_renders_atomic_no_partial(tmp_path):
    agents, sessions, tasks, handoffs, events = populated()

    def build():
        return make_service(
            tmp_path / "home",
            agents=agents,
            sessions=sessions,
            tasks=tasks,
            handoffs=handoffs,
            events=events,
        )

    expected = build().shared_md_render(workspace_id=WS_A)
    expected_bytes = shared_md_path(tmp_path / "home", WS_A).read_bytes()

    n = 16
    barrier = threading.Barrier(n)
    errors: list[Exception] = []
    lock = threading.Lock()

    def worker():
        svc = build()
        try:
            barrier.wait()
            for _ in range(5):
                svc.shared_md_render(workspace_id=WS_A)
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    with ThreadPoolExecutor(max_workers=n) as ex:
        futures = [ex.submit(worker) for _ in range(n)]
        for f in futures:
            f.result()

    assert not errors, errors
    # Final file is a complete, valid render (identical content for all renders).
    final = shared_md_path(tmp_path / "home", WS_A).read_bytes()
    assert final == expected_bytes
    assert len(final) == expected["bytes_written"]
    # No leftover temp files from the temp-file + rename swap.
    ws_dir = Path(tmp_path / "home") / WORKSPACES_DIRNAME / WS_A
    leftovers = [p.name for p in ws_dir.iterdir() if p.name != SHARED_MD_FILENAME]
    assert leftovers == []


# --------------------------------------------------------------------------- #
# Error catalog - no file written on error
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", [None, "", "   "])
def test_workspace_required(tmp_path, bad):
    svc = make_service(tmp_path / "home")
    with pytest.raises(OktoNexusError) as ei:
        svc.shared_md_render(workspace_id=bad)
    assert ei.value.code == ErrorCode.WORKSPACE_REQUIRED.value
    assert not (Path(tmp_path / "home") / WORKSPACES_DIRNAME).exists()


@pytest.mark.parametrize(
    "bad",
    [
        "A" * 64,  # uppercase not allowed
        "a" * 63,  # too short
        "a" * 65,  # too long
        "g" * 64,  # non-hex char
        "not-hex",
        "deadbeef",
    ],
)
def test_malformed_workspace_id_is_validation_error(tmp_path, bad):
    svc = make_service(tmp_path / "home", existing=(WS_A,))
    with pytest.raises(OktoNexusError) as ei:
        svc.shared_md_render(workspace_id=bad)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert not (Path(tmp_path / "home") / WORKSPACES_DIRNAME).exists()


@pytest.mark.parametrize("bad", [0, -1, 1.5, "5", True, False, DEFAULT_MAX_LIMIT_EVENTS + 1])
def test_invalid_limit_events_is_validation_error(tmp_path, bad):
    svc = make_service(tmp_path / "home")
    with pytest.raises(OktoNexusError) as ei:
        svc.shared_md_render(workspace_id=WS_A, limit_events=bad)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert not shared_md_path(tmp_path / "home", WS_A).exists()


def test_limit_events_at_max_is_accepted(tmp_path):
    svc = make_service(tmp_path / "home", max_limit_events=100)
    data = svc.shared_md_render(workspace_id=WS_A, limit_events=100)
    assert data["limit_events"] == 100


def test_unknown_workspace_is_not_found(tmp_path):
    svc = make_service(tmp_path / "home", existing=(WS_A,))
    with pytest.raises(OktoNexusError) as ei:
        svc.shared_md_render(workspace_id=WS_UNKNOWN)
    assert ei.value.code == ErrorCode.NOT_FOUND.value
    assert not shared_md_path(tmp_path / "home", WS_UNKNOWN).exists()


def test_db_error_propagates_no_file(tmp_path):
    svc = make_service(
        tmp_path / "home", workspaces=FakeWorkspaceRepo(raises=True)
    )
    with pytest.raises(OktoNexusError) as ei:
        svc.shared_md_render(workspace_id=WS_A)
    assert ei.value.code == ErrorCode.DB_ERROR.value
    assert not shared_md_path(tmp_path / "home", WS_A).exists()


def test_render_error_on_replace_failure_leaves_prior_file_unchanged(
    tmp_path, monkeypatch
):
    svc = make_service(tmp_path / "home")
    # First successful render establishes a baseline file.
    svc.shared_md_render(workspace_id=WS_A)
    target = shared_md_path(tmp_path / "home", WS_A)
    baseline = target.read_bytes()

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(renderer_module.os, "replace", boom)
    with pytest.raises(OktoNexusError) as ei:
        svc.shared_md_render(workspace_id=WS_A)
    assert ei.value.code == ErrorCode.RENDER_ERROR.value

    # Prior file is untouched and no temp file leaked.
    assert target.read_bytes() == baseline
    ws_dir = Path(tmp_path / "home") / WORKSPACES_DIRNAME / WS_A
    leftovers = [p.name for p in ws_dir.iterdir() if p.name != SHARED_MD_FILENAME]
    assert leftovers == []


def test_render_error_when_dir_cannot_be_created(tmp_path):
    # Make ``workspaces`` a FILE so makedirs of the per-workspace dir fails.
    home = Path(tmp_path / "home")
    home.mkdir(parents=True)
    (home / WORKSPACES_DIRNAME).write_text("i am a file", encoding="utf-8")
    svc = make_service(home)
    with pytest.raises(OktoNexusError) as ei:
        svc.shared_md_render(workspace_id=WS_A)
    assert ei.value.code == ErrorCode.RENDER_ERROR.value


# --------------------------------------------------------------------------- #
# Derived view: shared.md is never read back as source of truth
# --------------------------------------------------------------------------- #
def test_shared_md_is_never_read_back():
    import okto_nexus.application.shared_md as app_mod
    import okto_nexus.adapters.outbound.sharedmd.renderer as rnd_mod

    for mod in (app_mod, rnd_mod):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        # No read of the rendered file: no read_text / open(..., "r") of shared.md.
        assert ".read_text(" not in src
        assert "open(" not in src or '"r"' not in src


# --------------------------------------------------------------------------- #
# MCP tool registration + canonical envelope
# --------------------------------------------------------------------------- #
def make_deps(tmp_path, *, repos: Repos, clock=None, max_shared_md_events=1000):
    home = Path(tmp_path / "home")
    config = SimpleNamespace(
        home_dir=home,
        max_inline_bytes=65536,
        max_shared_md_events=max_shared_md_events,
    )
    return SimpleNamespace(
        config=config,
        connection_factory=FakeConnectionFactory(),
        clock=clock or StubClock(),
        repos=repos,
        event_emitter=None,
    )


def test_register_tool_and_envelope(tmp_path):
    agents, sessions, tasks, handoffs, events = populated()
    repos = Repos(
        workspaces=FakeWorkspaceRepo({WS_A}),
        agents=FakeAgentRepo(agents),
        sessions=FakeSessionRepo(sessions),
        tasks=FakeTaskRepo(tasks),
        handoffs=FakeHandoffRepo(handoffs),
        events=FakeEventRepo(events),
    )
    deps = make_deps(tmp_path, repos=repos)
    server = FakeServer()
    register(server, deps)

    assert set(server.tools) == {"shared_md_render"}

    ok = server.tools["shared_md_render"](workspace_id=WS_A)
    assert ok["ok"] is True
    assert ok["data"]["sections_rendered"] == 4
    assert ok["data"]["limit_events"] == 50
    assert shared_md_path(tmp_path / "home", WS_A).is_file()

    # Failures surface as envelopes, never raised.
    missing = server.tools["shared_md_render"](workspace_id="")
    assert missing["ok"] is False
    assert missing["error"]["code"] == "WORKSPACE_REQUIRED"

    bad = server.tools["shared_md_render"](workspace_id="not-hex")
    assert bad["ok"] is False
    assert bad["error"]["code"] == "VALIDATION_ERROR"

    unknown = server.tools["shared_md_render"](workspace_id=WS_UNKNOWN)
    assert unknown["ok"] is False
    assert unknown["error"]["code"] == "NOT_FOUND"


def test_build_service_wires_foundational_repos(tmp_path):
    repos = Repos()  # all None
    # The ceiling moved into NexusConfig (fail-closed parse at load_config
    # time); the adapter must read the configured value, not os.environ.
    deps = make_deps(tmp_path, repos=repos, max_shared_md_events=77)
    svc = build_service(deps)
    # Foundational identity repos filled in (sibling repos stay None / optional).
    assert deps.repos.workspaces is not None
    assert deps.repos.agents is not None
    assert deps.repos.sessions is not None
    assert isinstance(svc, SharedMdService)
    assert svc._max_limit == 77


# --------------------------------------------------------------------------- #
# Integration over the real SQLite workspace repo (committed-state read path)
# --------------------------------------------------------------------------- #
def test_integration_real_workspace_repo(migrated_factory, tmp_config):
    clock = StubClock("2026-06-07T00:00:00Z")
    ws_repo = SqliteWorkspaceRepo(clock)
    # Seed a committed workspaces row.
    with migrated_factory.unit_of_work() as uow:
        ws_repo.upsert(uow, workspace_id=WS_A, root_realpath="/tmp/proj")

    svc = SharedMdService(
        connection_factory=migrated_factory,
        workspaces=ws_repo,
        renderer=FileSystemSharedMdRenderer(home_dir=tmp_config.home_dir),
        clock=clock,
        sessions=FakeSessionRepo([]),
        agents=FakeAgentRepo([]),
        tasks=FakeTaskRepo([]),
        handoffs=FakeHandoffRepo([]),
        events=FakeEventRepo([]),
    )
    data = svc.shared_md_render(workspace_id=WS_A)
    assert data["workspace_id"] == WS_A
    assert data["bytes_written"] > 0
    assert (Path(tmp_config.home_dir) / WORKSPACES_DIRNAME / WS_A / SHARED_MD_FILENAME).is_file()

    # Unknown but well-formed id -> NOT_FOUND against the real DB.
    with pytest.raises(OktoNexusError) as ei:
        svc.shared_md_render(workspace_id=WS_UNKNOWN)
    assert ei.value.code == ErrorCode.NOT_FOUND.value


def test_recent_events_rendered_from_real_sqlite_event_repo(
    migrated_factory, tmp_config
):
    """REGRESSION (M2): Recent Events over the REAL adapter, across ALL streams.

    The service drains the log with ``stream=None`` (= all streams). The old
    adapter compiled that to ``WHERE stream = NULL`` - which matches nothing -
    so Recent Events was ALWAYS empty in production while the fake-backed unit
    tests stayed green. This test seeds committed events on several streams via
    the real ``SqliteEventRepo`` and asserts they all reach the rendered file.
    """
    clock = StubClock("2026-06-07T00:00:00Z")
    ws_repo = SqliteWorkspaceRepo(clock)
    event_repo = SqliteEventRepo(clock)
    with migrated_factory.unit_of_work() as uow:
        ws_repo.upsert(uow, workspace_id=WS_A, root_realpath="/tmp/proj")
        for stream, typ in (
            ("workspace", "session.opened"),
            ("handoff", "handoff.created"),
            ("agent", "agent.registered"),
            ("workspace", "message.created"),
        ):
            event_repo.append(
                uow,
                workspace_id=WS_A,
                stream=stream,
                type=typ,
                actor_agent_id="agent-1",
            )

    svc = SharedMdService(
        connection_factory=migrated_factory,
        workspaces=ws_repo,
        renderer=FileSystemSharedMdRenderer(home_dir=tmp_config.home_dir),
        clock=clock,
        events=event_repo,
    )
    svc.shared_md_render(workspace_id=WS_A)
    text = (
        Path(tmp_config.home_dir) / WORKSPACES_DIRNAME / WS_A / SHARED_MD_FILENAME
    ).read_text(encoding="utf-8")

    # All four committed events appear (newest-first by event_id), regardless
    # of stream - Recent Events is never empty when committed events exist.
    assert _event_ids_in_order(text) == [4, 3, 2, 1]
    for typ in ("session.opened", "handoff.created", "agent.registered", "message.created"):
        assert typ in text
