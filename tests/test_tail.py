"""Tests for the ``okto-nexus tail`` CLI subcommand.

``tail`` wraps the public ``event_wait`` long-poll with automatic cursor
advancement and prints one JSON object per event (line-buffered). These tests
inject the service (so no real sleeping/IO) and capture an in-memory sink, plus
one end-to-end check that ``main(["tail", ...])`` dispatches through the real
fail-closed bootstrap. Coverage:

* line-delimited JSON output, one valid object per event, ascending;
* ``--from 0`` (beginning), explicit ``event_id``, and ``latest`` (skips
  existing events by walking the stream to its end via ``event_get``);
* cursor advancement across poll windows in the follow loop;
* ``--once`` exits after a single window; ``Ctrl+C`` exits cleanly (code 0);
* canonical errors (bad workspace, malformed ``--from``) -> exit 1 + stderr;
* the ``main`` dispatcher routes ``tail`` to ``run_tail``.
"""

from __future__ import annotations

import io
import json
import os

import pytest

from okto_nexus.adapters.inbound.cli.tail import run_tail, stream_events
from okto_nexus.adapters.inbound.mcp.server import main
from okto_nexus.adapters.outbound.sqlite.events_repo import SqliteEventRepo
from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteWorkspaceRepo
from okto_nexus.application.events import EventService
from okto_nexus.config import NexusConfig
from okto_nexus.domain.ids import resolve_workspace_id
from okto_nexus.errors import ErrorCode, OktoNexusError


# --------------------------------------------------------------------------- #
# Test doubles & helpers
# --------------------------------------------------------------------------- #
class StubClock:
    def now_iso(self) -> str:
        return "2026-06-07T00:00:00Z"

    def now_epoch(self) -> float:
        return 1_780_000_000.0


class ManualSleeper:
    def __init__(self) -> None:
        self.calls: list[float] = []
        self.t = 0.0

    def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.t += seconds

    def monotonic(self) -> float:
        return self.t


class ScriptedService:
    """Stand-in EventService returning canned pages, recording call cursors."""

    def __init__(self, *, wait_pages=(), get_pages=()) -> None:
        self._wait = list(wait_pages)
        self._get = list(get_pages)
        self.wait_calls: list[dict] = []
        self.get_calls: list[dict] = []

    def event_wait(self, **kwargs):
        self.wait_calls.append(kwargs)
        item = self._wait.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def event_get(self, **kwargs):
        self.get_calls.append(kwargs)
        return self._get.pop(0)


def cfg(tmp_path, **overrides) -> NexusConfig:
    base = dict(home_dir=tmp_path / "okto_home")
    base.update(overrides)
    return NexusConfig(**base)


def make_ws(factory, tmp_path, name="P"):
    d = tmp_path / name
    d.mkdir()
    ws = resolve_workspace_id(str(d))
    with factory.unit_of_work() as uow:
        SqliteWorkspaceRepo(StubClock()).upsert(
            uow, workspace_id=ws, root_realpath=os.path.realpath(str(d))
        )
    return str(d), ws


def emit(factory, ws, *, stream="workspace", type="evt", payload=None):
    with factory.unit_of_work() as uow:
        return SqliteEventRepo().append(
            uow, workspace_id=ws, stream=stream, type=type, payload=payload
        )


def real_service_factory(factory, config, *, sleeper=None, monotonic=None):
    def _factory(env, extra):
        clock = StubClock()
        return EventService(
            connection_factory=factory,
            events=SqliteEventRepo(clock),
            clock=clock,
            config=config,
            sleeper=sleeper,
            monotonic=monotonic,
        )

    return _factory


def page(events, next_cursor, *, has_more=False, timed_out=False):
    return {
        "events": list(events),
        "next_cursor": next_cursor,
        "has_more": has_more,
        "timed_out": timed_out,
    }


# --------------------------------------------------------------------------- #
# Line-delimited JSON output
# --------------------------------------------------------------------------- #
def test_tail_from_zero_emits_json_lines(migrated_factory, tmp_path):
    config = cfg(tmp_path)
    pr, ws = make_ws(migrated_factory, tmp_path)
    ids = [emit(migrated_factory, ws, type=f"e{i}") for i in range(3)]
    assert ids == [1, 2, 3]

    out = io.StringIO()
    code = run_tail(
        [
            "--project-root", pr,
            "--agent-id", "a",
            "--from", "0",
            "--timeout-seconds", "0",
            "--once",
        ],
        out=out,
        service_factory=real_service_factory(migrated_factory, config),
    )
    assert code == 0
    lines = out.getvalue().splitlines()
    assert len(lines) == 3
    parsed = [json.loads(ln) for ln in lines]
    assert [e["event_id"] for e in parsed] == [1, 2, 3]
    assert [e["type"] for e in parsed] == ["e0", "e1", "e2"]
    assert all(e["stream"] == "workspace" for e in parsed)


def test_tail_non_ascii_event_is_ascii_escaped_and_round_trips():
    # Regression: an event carrying UTF-8 (emoji/accents) must not abort the
    # stream under a non-UTF-8 stdout (e.g. Windows cp1252). Output is pure
    # ASCII (\uXXXX escapes) and decodes back losslessly.
    svc = ScriptedService(
        wait_pages=[page([{"event_id": 1, "type": "msg", "subject": "olá 👋"}], 1)]
    )
    out = io.StringIO()
    code = run_tail(
        ["--project-root", "/p", "--agent-id", "a", "--from", "0", "--once"],
        out=out,
        service_factory=lambda env, extra: svc,
    )
    assert code == 0
    raw = out.getvalue()
    assert all(ord(c) < 128 for c in raw)  # pure ASCII -> encodes under any locale
    assert "👋" not in raw  # the raw emoji never reaches the sink
    assert json.loads(raw)["subject"] == "olá 👋"  # lossless round-trip


def test_tail_from_explicit_cursor(migrated_factory, tmp_path):
    config = cfg(tmp_path)
    pr, ws = make_ws(migrated_factory, tmp_path)
    for i in range(5):
        emit(migrated_factory, ws, type=f"e{i}")

    out = io.StringIO()
    code = run_tail(
        [
            "--project-root", pr,
            "--agent-id", "a",
            "--from", "2",
            "--timeout-seconds", "0",
            "--once",
        ],
        out=out,
        service_factory=real_service_factory(migrated_factory, config),
    )
    assert code == 0
    parsed = [json.loads(ln) for ln in out.getvalue().splitlines()]
    assert [e["event_id"] for e in parsed] == [3, 4, 5]


def test_tail_from_latest_skips_existing_events(migrated_factory, tmp_path):
    config = cfg(tmp_path)
    pr, ws = make_ws(migrated_factory, tmp_path)
    for i in range(4):
        emit(migrated_factory, ws, type=f"e{i}")

    out = io.StringIO()
    sleeper = ManualSleeper()
    code = run_tail(
        [
            "--project-root", pr,
            "--agent-id", "a",
            "--from", "latest",
            "--timeout-seconds", "0",
            "--once",
        ],
        out=out,
        service_factory=real_service_factory(
            migrated_factory, config, sleeper=sleeper.sleep, monotonic=sleeper.monotonic
        ),
    )
    assert code == 0
    # 'latest' starts at the current end -> no pre-existing event is emitted.
    assert out.getvalue() == ""


def test_tail_latest_then_new_event_is_followed(migrated_factory, tmp_path):
    config = cfg(tmp_path)
    pr, ws = make_ws(migrated_factory, tmp_path)
    emit(migrated_factory, ws, type="old")

    # Inject a service whose first poll appends a NEW event during the sleep.
    def append_new():
        emit(migrated_factory, ws, type="new")

    class TriggerSleeper(ManualSleeper):
        def sleep(self, seconds):
            super().sleep(seconds)
            if len(self.calls) == 1:
                append_new()

    sleeper = TriggerSleeper()
    out = io.StringIO()
    code = run_tail(
        [
            "--project-root", pr,
            "--agent-id", "a",
            "--from", "latest",
            "--timeout-seconds", "10",
            "--once",
        ],
        out=out,
        service_factory=real_service_factory(
            migrated_factory, config, sleeper=sleeper.sleep, monotonic=sleeper.monotonic
        ),
    )
    assert code == 0
    parsed = [json.loads(ln) for ln in out.getvalue().splitlines()]
    assert [e["type"] for e in parsed] == ["new"]  # only the post-start event


# --------------------------------------------------------------------------- #
# Follow loop: cursor advancement & interruption
# --------------------------------------------------------------------------- #
def test_stream_events_advances_cursor_until_interrupt():
    svc = ScriptedService(
        wait_pages=[
            page([{"event_id": 1, "type": "a"}], 1),
            page([{"event_id": 2, "type": "b"}], 2),
            KeyboardInterrupt(),
        ]
    )
    ns = _ns(project_root="/p", agent_id="a", stream="workspace", once=False)
    out = io.StringIO()
    code = stream_events(svc, ns, out, start_cursor=0)
    assert code == 0
    parsed = [json.loads(ln) for ln in out.getvalue().splitlines()]
    assert [e["event_id"] for e in parsed] == [1, 2]
    # Each window advanced the cursor for the next poll.
    assert [c["cursor"] for c in svc.wait_calls] == [0, 1, 2]


def test_run_tail_keyboard_interrupt_exits_zero():
    svc = ScriptedService(wait_pages=[KeyboardInterrupt()])
    out = io.StringIO()
    code = run_tail(
        ["--project-root", "/p", "--agent-id", "a", "--from", "0"],
        out=out,
        service_factory=lambda env, extra: svc,
    )
    assert code == 0
    assert out.getvalue() == ""


def test_run_tail_once_returns_after_one_window():
    svc = ScriptedService(
        wait_pages=[page([{"event_id": 1, "type": "a"}], 1, has_more=True)]
    )
    out = io.StringIO()
    code = run_tail(
        ["--project-root", "/p", "--agent-id", "a", "--from", "0", "--once"],
        out=out,
        service_factory=lambda env, extra: svc,
    )
    assert code == 0
    assert len(svc.wait_calls) == 1  # exactly one poll window
    assert [json.loads(ln)["event_id"] for ln in out.getvalue().splitlines()] == [1]


# --------------------------------------------------------------------------- #
# Error handling
# --------------------------------------------------------------------------- #
def test_tail_bad_workspace_exits_one(migrated_factory, tmp_path, capsys):
    config = cfg(tmp_path)
    missing = str(tmp_path / "does_not_exist" / "child")
    code = run_tail(
        [
            "--project-root", missing,
            "--agent-id", "a",
            "--from", "0",
            "--timeout-seconds", "0",
            "--once",
        ],
        out=io.StringIO(),
        service_factory=real_service_factory(migrated_factory, config),
    )
    assert code == 1
    err = capsys.readouterr().err
    assert "WORKSPACE_UNRESOLVED" in err


def test_tail_malformed_from_exits_one(migrated_factory, tmp_path, capsys):
    config = cfg(tmp_path)
    pr, _ws = make_ws(migrated_factory, tmp_path)
    code = run_tail(
        ["--project-root", pr, "--agent-id", "a", "--from", "not-a-cursor", "--once"],
        out=io.StringIO(),
        service_factory=real_service_factory(migrated_factory, config),
    )
    assert code == 1
    assert "CONFIG_ERROR" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# main() dispatch (end-to-end through real bootstrap)
# --------------------------------------------------------------------------- #
def test_main_dispatches_tail_subcommand(tmp_path, capsys):
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    proj.mkdir()
    code = main(
        [
            "tail",
            "--project-root", str(proj),
            "--agent-id", "a",
            "--home", str(home),
            "--from", "0",
            "--timeout-seconds", "0",
            "--once",
        ]
    )
    assert code == 0
    assert capsys.readouterr().out == ""  # no events yet


def test_main_dispatches_tail_with_real_event_end_to_end(tmp_path, capsys):
    # Production path through the real bootstrap WITH an event present: proves
    # the wire from build_service to NDJSON serialisation, not just dispatch.
    from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
    from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner

    home = tmp_path / "home"
    proj = tmp_path / "proj"
    proj.mkdir()
    config = NexusConfig(home_dir=home)
    factory = ConnectionFactory(config)
    MigrationRunner(factory).apply()
    ws = resolve_workspace_id(str(proj))
    with factory.unit_of_work() as uow:
        SqliteWorkspaceRepo(StubClock()).upsert(
            uow, workspace_id=ws, root_realpath=os.path.realpath(str(proj))
        )
        SqliteEventRepo(StubClock()).append(
            uow, workspace_id=ws, stream="workspace", type="hello", payload={"k": "v"}
        )

    code = main(
        [
            "tail",
            "--project-root", str(proj),
            "--agent-id", "a",
            "--home", str(home),
            "--from", "0",
            "--timeout-seconds", "0",
            "--once",
        ]
    )
    assert code == 0
    parsed = [json.loads(ln) for ln in capsys.readouterr().out.splitlines()]
    assert [e["type"] for e in parsed] == ["hello"]
    assert parsed[0]["payload"] == {"k": "v"}


# --------------------------------------------------------------------------- #
# Robustness: busy-spin guard, broken pipe, SIGINT during resolution, flush
# --------------------------------------------------------------------------- #
class RecordingSink:
    """A text sink that records each write and counts flushes."""

    def __init__(self) -> None:
        self.writes: list[str] = []
        self.flushes = 0

    def write(self, s: str) -> int:
        self.writes.append(s)
        return len(s)

    def flush(self) -> None:
        self.flushes += 1


def test_tail_timeout_zero_without_once_is_config_error(capsys):
    # --timeout-seconds <= 0 without --once would busy-spin the follow loop;
    # reject it fail-closed BEFORE any poll happens.
    svc = ScriptedService(wait_pages=[page([], 0, timed_out=True)])
    code = run_tail(
        ["--project-root", "/p", "--agent-id", "a", "--from", "0", "--timeout-seconds", "0"],
        out=io.StringIO(),
        service_factory=lambda env, extra: svc,
    )
    assert code == 1
    assert "CONFIG_ERROR" in capsys.readouterr().err
    assert svc.wait_calls == []  # rejected before polling


def test_tail_negative_timeout_without_once_is_config_error(capsys):
    svc = ScriptedService(wait_pages=[page([], 0, timed_out=True)])
    code = run_tail(
        ["--project-root", "/p", "--agent-id", "a", "--from", "0", "--timeout-seconds", "-5"],
        out=io.StringIO(),
        service_factory=lambda env, extra: svc,
    )
    assert code == 1
    assert "CONFIG_ERROR" in capsys.readouterr().err


def test_tail_broken_pipe_exits_zero():
    class BrokenSink:
        def write(self, s):
            raise BrokenPipeError("downstream closed the pipe")

        def flush(self):
            pass

    svc = ScriptedService(wait_pages=[page([{"event_id": 1, "type": "a"}], 1)])
    code = run_tail(
        ["--project-root", "/p", "--agent-id", "a", "--from", "0", "--once"],
        out=BrokenSink(),
        service_factory=lambda env, extra: svc,
    )
    assert code == 0  # SIGPIPE-like clean exit, no traceback


def test_tail_sigint_during_latest_resolution_exits_zero():
    class InterruptingService:
        def event_get(self, **kwargs):
            raise KeyboardInterrupt()

    code = run_tail(
        ["--project-root", "/p", "--agent-id", "a", "--from", "latest"],
        out=io.StringIO(),
        service_factory=lambda env, extra: InterruptingService(),
    )
    assert code == 0  # Ctrl+C during the walk still exits cleanly


def test_tail_flushes_after_each_line():
    # Gate item 3: line-buffered. One flush per emitted event so `tail -f`
    # streams incrementally; a regression dropping out.flush() must fail here.
    svc = ScriptedService(
        wait_pages=[page([{"event_id": 1, "type": "a"}, {"event_id": 2, "type": "b"}], 2)]
    )
    sink = RecordingSink()
    code = run_tail(
        ["--project-root", "/p", "--agent-id", "a", "--from", "0", "--once"],
        out=sink,
        service_factory=lambda env, extra: svc,
    )
    assert code == 0
    assert sink.flushes >= 2  # flushed after each of the two events
    assert len([w for w in sink.writes if w.endswith("\n")]) == 2


# --------------------------------------------------------------------------- #
# Author filtering (own-echo) — ressalva 1
# --------------------------------------------------------------------------- #
def test_tail_exclude_agent_drops_own_echo():
    svc = ScriptedService(
        wait_pages=[
            page(
                [
                    {"event_id": 1, "type": "a", "actor_agent_id": "me"},
                    {"event_id": 2, "type": "b", "actor_agent_id": "other"},
                    {"event_id": 3, "type": "c", "actor_agent_id": "me"},
                ],
                3,
            )
        ]
    )
    out = io.StringIO()
    code = run_tail(
        [
            "--project-root", "/p", "--agent-id", "me",
            "--from", "0", "--once", "--exclude-agent", "me",
        ],
        out=out,
        service_factory=lambda env, extra: svc,
    )
    assert code == 0
    parsed = [json.loads(ln) for ln in out.getvalue().splitlines()]
    assert [e["event_id"] for e in parsed] == [2]  # own (me) echo dropped
    assert all(e["actor_agent_id"] != "me" for e in parsed)


def test_tail_from_agent_pushes_server_side_filter():
    svc = ScriptedService(wait_pages=[page([{"event_id": 1, "actor_agent_id": "x"}], 1)])
    code = run_tail(
        [
            "--project-root", "/p", "--agent-id", "a",
            "--from", "0", "--once", "--from-agent", "x",
        ],
        out=io.StringIO(),
        service_factory=lambda env, extra: svc,
    )
    assert code == 0
    assert svc.wait_calls[0]["filters"] == {"agent_id": "x"}  # pushed down server-side


def test_tail_default_has_no_author_filter():
    svc = ScriptedService(wait_pages=[page([{"event_id": 1}], 1)])
    run_tail(
        ["--project-root", "/p", "--agent-id", "a", "--from", "0", "--once"],
        out=io.StringIO(),
        service_factory=lambda env, extra: svc,
    )
    assert svc.wait_calls[0]["filters"] is None


# --------------------------------------------------------------------------- #
# Transient retry vs terminal fail-fast — ressalva 2
# --------------------------------------------------------------------------- #
def test_stream_events_retries_transient_db_error_then_succeeds():
    svc = ScriptedService(
        wait_pages=[
            OktoNexusError(ErrorCode.DB_ERROR, "wal busy"),
            OktoNexusError(ErrorCode.DB_ERROR, "wal busy"),
            page([{"event_id": 1, "type": "a"}], 1),
        ]
    )
    sleeps: list[float] = []
    ns = _ns(project_root="/p", agent_id="a", stream="workspace", once=True)
    out = io.StringIO()
    code = stream_events(svc, ns, out, start_cursor=0, sleeper=sleeps.append)
    assert code == 0
    assert [json.loads(ln)["event_id"] for ln in out.getvalue().splitlines()] == [1]
    assert len(sleeps) == 2  # backed off twice before the successful poll
    # The SAME cursor is retried, so the failed window is never skipped.
    assert [c["cursor"] for c in svc.wait_calls] == [0, 0, 0]


def test_stream_events_resets_retry_budget_after_success():
    # A transient, a success, then a transient again, then a terminal sentinel to
    # end the loop: the counter resets on each success, so sporadic locks over a
    # long follow never accumulate toward the budget.
    svc = ScriptedService(
        wait_pages=[
            OktoNexusError(ErrorCode.DB_ERROR, "lock"),
            page([{"event_id": 1}], 1),
            OktoNexusError(ErrorCode.DB_ERROR, "lock"),
            page([{"event_id": 2}], 2),
            OktoNexusError(ErrorCode.WORKSPACE_UNRESOLVED, "stop"),
        ]
    )
    sleeps: list[float] = []
    ns = _ns(project_root="/p", agent_id="a", stream="workspace", once=False)
    out = io.StringIO()
    with pytest.raises(OktoNexusError):
        stream_events(svc, ns, out, start_cursor=0, sleeper=sleeps.append)
    assert [json.loads(ln)["event_id"] for ln in out.getvalue().splitlines()] == [1, 2]
    assert len(sleeps) == 2  # one backoff per transient, never accumulating


def test_stream_events_persistent_transient_surfaces():
    svc = ScriptedService(
        wait_pages=[OktoNexusError(ErrorCode.DB_ERROR, "wal busy") for _ in range(10)]
    )
    sleeps: list[float] = []
    ns = _ns(project_root="/p", agent_id="a", stream="workspace", once=False)
    with pytest.raises(OktoNexusError) as ei:
        stream_events(svc, ns, io.StringIO(), start_cursor=0, sleeper=sleeps.append)
    assert ei.value.code == ErrorCode.DB_ERROR.value  # surfaced, not silenced
    assert len(sleeps) == 6  # exactly the retry budget, then re-raised
    assert len(svc.wait_calls) == 7  # 6 retries + the surfacing call


def test_stream_events_terminal_error_fails_fast_no_retry():
    svc = ScriptedService(
        wait_pages=[OktoNexusError(ErrorCode.WORKSPACE_UNRESOLVED, "bad path")]
    )
    sleeps: list[float] = []
    ns = _ns(project_root="/p", agent_id="a", stream="workspace", once=False)
    with pytest.raises(OktoNexusError) as ei:
        stream_events(svc, ns, io.StringIO(), start_cursor=0, sleeper=sleeps.append)
    assert ei.value.code == ErrorCode.WORKSPACE_UNRESOLVED.value
    assert sleeps == []  # no backoff for terminal errors
    assert len(svc.wait_calls) == 1  # failed fast


# --------------------------------------------------------------------------- #
# Local helpers
# --------------------------------------------------------------------------- #
def _ns(**kwargs):
    import argparse

    ns = argparse.Namespace(
        limit=None, timeout_seconds=None, from_agent=None, exclude_agent=None
    )
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns
