"""Crash boundaries use actual files/fsync/SQLite with disposable stores."""
import json
import os
from pathlib import Path

import pytest

from okto_nexus.adapters.outbound.harness.event_journal import FileRuntimeEventJournal
from okto_nexus.domain.harness import HarnessEvent
from test_pr34_remediation import runtime as runtime_fixture, open_rest

runtime = runtime_fixture


def event(session="fixture", **payload):
    return HarnessEvent(session_id=session, harness_kind="codex", kind="turn_completed",
        native_event="turn/completed", occurred_at="2026-09-22T00:00:00Z", payload=payload)


def test_reopen_preserves_distinct_equal_text_and_stable_cursors(tmp_path):
    journal = FileRuntimeEventJournal(tmp_path, segment_bytes=900)
    journal.start(initial_sequences={"fixture": 4})
    records = [journal.append(event(text="same"), connection_id="connection-fixture") for _ in range(5)]
    assert [record["event"]["sequence"] for record in records] == [5, 6, 7, 8, 9]
    assert len({record["event"]["event_id"] for record in records}) == 5
    assert journal.read_after(0) == records
    journal.close()
    reopened = FileRuntimeEventJournal(tmp_path)
    try:
        reopened.start()
        assert reopened.read_after(0) == records
        assert reopened.append(event(text="next"))["event"]["sequence"] == 10
    finally:
        reopened.close()


def test_exclusive_owner_lock(tmp_path):
    one, two = FileRuntimeEventJournal(tmp_path), FileRuntimeEventJournal(tmp_path)
    one.start()
    try:
        with pytest.raises(OSError):
            two.start()
        one.append(event(text="owned"))
    finally:
        one.close()
    two.start()
    assert two.watermark == 1
    two.close()


def test_normalized_output_is_redacted_before_durable_capture(tmp_path):
    from dataclasses import replace
    journal = FileRuntimeEventJournal(tmp_path)
    journal.start()
    secret = "nxs_" + "f" * 32
    try:
        record = journal.append(replace(event(), output_text="fixture " + secret))
        assert record["event"]["output_text"] == "fixture [REDACTED]"
        assert secret.encode() not in b"".join(path.read_bytes() for path in journal.root.glob("segment-*.bin"))
    finally:
        journal.close()


def test_incomplete_tail_recovers_but_complete_corruption_fails_closed(tmp_path):
    journal = FileRuntimeEventJournal(tmp_path)
    journal.start()
    expected = journal.append(event(text="durable"))
    journal.close()
    segment = next((tmp_path / "runtime-journal-v1").glob("segment-*.bin"))
    with segment.open("ab") as stream:
        stream.write(b"NJR")
    journal.start()
    assert journal._tail_repairs == 1
    assert journal.read_after(0) == [expected]
    journal.close()
    data = bytearray(segment.read_bytes())
    data[15] ^= 1
    segment.write_bytes(data)
    with pytest.raises(OSError, match="checksum"):
        journal.start()
    with pytest.raises(OSError, match="unavailable"):
        journal.append(event())


def test_quota_and_fsync_failure_stop_admission(tmp_path, monkeypatch):
    journal = FileRuntimeEventJournal(tmp_path, quota_bytes=1000)
    journal.start()
    journal.append(event(text="one"))
    with pytest.raises(OSError, match="quota"):
        journal.append(event(text="x" * 1000))
    with pytest.raises(OSError, match="unavailable"):
        journal.check_admission()
    journal.close()
    journal = FileRuntimeEventJournal(tmp_path)
    journal.start()
    def fail(_):
        raise OSError("fixture disk full")
    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError, match="disk full"):
        journal.append(event(text="unconfirmed fsync"))
    assert journal.watermark == 1
    with pytest.raises(OSError, match="unavailable"):
        journal.check_admission()
    journal.close()


def test_credentials_redacted_before_bytes_are_written(tmp_path):
    journal = FileRuntimeEventJournal(tmp_path)
    journal.start()
    record = journal.append(event(authorization="private", nested={"api_key": "private"},
        text="Bearer private and nxs_fixture-secret and sk-fixturelongcredential", input_tokens=10))
    journal.close()
    raw = b"".join(path.read_bytes() for path in (tmp_path / "runtime-journal-v1").glob("segment-*"))
    assert b"private" not in raw and b"fixture-secret" not in raw and b"fixturelongcredential" not in raw
    assert record["event"]["payload"]["input_tokens"] == 10


def test_projection_rollback_and_restart_recover_exactly_once(runtime, monkeypatch):
    deps, _, _, _, _, _ = runtime
    session_id = open_rest(runtime).json()["data"]["session_id"]
    ingress = deps.harness_supervisor.event_ingress
    original = ingress.repo.project
    def fail_after_result(uow, **kwargs):
        original(uow, **kwargs)
        raise OSError("fixture crash before transaction commit")
    monkeypatch.setattr(ingress.repo, "project", fail_after_result)
    captured = deps.harness_supervisor._handle_event(session_id, event(session_id, text="result"))
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ("harness_events", "runtime_results", "runtime_journal_checkpoint"):
            assert uow.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    ingress.close()
    monkeypatch.undo()
    ingress.journal = FileRuntimeEventJournal(deps.config.home_dir)
    ingress.start()
    assert ingress.recover() == 0
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT * FROM runtime_results").fetchone()
        assert row["event_id"] == captured.event_id
        assert json.loads(row["payload"])["text"] == "result"
        assert row["publication_state"] == "PENDING_AUTHORIZATION"
        assert uow.connection.execute("SELECT count(*) FROM runtime_results").fetchone()[0] == 1


def test_journal_io_outside_write_uow_and_full_sync(runtime, monkeypatch):
    deps, _, _, _, _, _ = runtime
    session_id = open_rest(runtime).json()["data"]["session_id"]
    from okto_nexus.adapters.outbound.sqlite.connection import SqliteUnitOfWork
    import threading
    active = threading.local()
    enter, leave = SqliteUnitOfWork.__enter__, SqliteUnitOfWork.__exit__
    def checked_enter(uow):
        result = enter(uow)
        active.write = uow._write
        return result
    def checked_exit(uow, *args):
        try:
            return leave(uow, *args)
        finally:
            active.write = False
    fsync = os.fsync
    calls = []
    def checked_fsync(fd):
        assert not getattr(active, "write", False)
        calls.append(fd)
        return fsync(fd)
    monkeypatch.setattr(SqliteUnitOfWork, "__enter__", checked_enter)
    monkeypatch.setattr(SqliteUnitOfWork, "__exit__", checked_exit)
    monkeypatch.setattr(os, "fsync", checked_fsync)
    deps.harness_supervisor._handle_event(session_id, event(session_id, text="durable"))
    assert calls
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("PRAGMA synchronous").fetchone()[0] >= 2


def test_projection_batch_rolls_back_before_publication(runtime, monkeypatch):
    deps, _, _, _, _, _ = runtime
    session_id = open_rest(runtime).json()["data"]["session_id"]
    ingress = deps.harness_supervisor.event_ingress
    original = ingress.repo.project
    published = []

    def fail_second(uow, **kwargs):
        original(uow, **kwargs)
        if kwargs["record"]["ordinal"] == 2:
            raise OSError("fixture second record failure")
        return True

    monkeypatch.setattr(ingress.repo, "project", fail_second)
    monkeypatch.setattr(ingress, "publish", published.append)
    with ingress._project_lock:
        for text in ("first", "second"):
            ingress.journal.append(event(session_id, text=text))
    with pytest.raises(OSError, match="second record"):
        ingress.recover()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ("harness_events", "runtime_results", "runtime_journal_checkpoint"):
            assert uow.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    assert not published
    monkeypatch.setattr(ingress.repo, "project", original)
    ingress.recover()
    assert [item.payload["text"] for item in published] == ["first", "second"]
    assert ingress.recover() == 0


def test_hardlink_replacement_is_refused(tmp_path):
    journal = FileRuntimeEventJournal(tmp_path)
    journal.start()
    journal.append(event(text="safe"))
    journal.close()
    segment = next(journal.root.glob("segment-*"))
    os.link(segment, Path(tmp_path) / "external-alias")
    with pytest.raises(OSError, match="regular"):
        journal.start()


def test_replay_after_checkpoint_loss_does_not_duplicate_result(runtime):
    deps, _, _, _, _, _ = runtime
    session_id = open_rest(runtime).json()["data"]["session_id"]
    ingress = deps.harness_supervisor.event_ingress
    ingress.capture(event(session_id, text="same result"))
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("DELETE FROM runtime_journal_checkpoint")
    assert ingress.recover() == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM harness_events").fetchone()[0] == 1
        assert uow.connection.execute("SELECT count(*) FROM runtime_results").fetchone()[0] == 1


def test_replay_cursors_cover_append_and_reject_unbounded_limits(runtime):
    deps, _, _, _, _, _ = runtime
    session_id = open_rest(runtime).json()["data"]["session_id"]
    supervisor = deps.harness_supervisor
    for index in range(4):
        supervisor._handle_event(session_id, event(session_id, text=str(index)))
    first = supervisor.replay_events(session_id, limit=2)
    supervisor._handle_event(session_id, event(session_id, text="appended"))
    second = supervisor.replay_events(session_id, after_sequence=first[-1].sequence, limit=2)
    third = supervisor.replay_events(session_id, after_sequence=second[-1].sequence, limit=2)
    assert [item.sequence for item in first + second + third] == [1, 2, 3, 4, 5]
    from okto_nexus.errors import OktoNexusError
    for arguments in ({"limit": -1}, {"limit": 0}, {"limit": 1001}, {"after_sequence": -1}):
        with pytest.raises(OktoNexusError):
            supervisor.replay_events(session_id, **arguments)
