"""Projected-only retention, crash boundaries and real authenticated surfaces."""
import os

import pytest

from okto_nexus.adapters.outbound.harness.event_journal import FileRuntimeEventJournal
from test_runtime_event_journal import event
from test_pr34_remediation import runtime as runtime_fixture, open_rest, tool

runtime = runtime_fixture


def filled(tmp_path):
    journal = FileRuntimeEventJournal(tmp_path, segment_bytes=900)
    journal.start()
    records = [journal.append(event(text=str(i))) for i in range(5)]
    return journal, records


def test_compaction_keeps_unprojected_records_and_original_ordinals(tmp_path):
    journal, records = filled(tmp_path)
    result = journal.compact(3)
    assert result["removed_segments"] == 3
    assert result["retained_after"] == 3
    assert journal.watermark == 5
    assert journal.read_after(3) == records[3:]
    with pytest.raises(OSError, match="cursor expired"):
        journal.read_after(2)
    journal.close()
    journal.start()
    assert journal.read_after(3) == records[3:]
    assert journal.append(event(text="next"))["ordinal"] == 6
    assert journal.read_after(5)[0]["event"]["sequence"] == 6
    journal.close()


def test_quota_can_recover_without_discarding_sqlite_projection(tmp_path):
    journal, records = filled(tmp_path)
    journal.quota = journal._total + 1
    with pytest.raises(OSError, match="quota"):
        journal.append(event(text="full"))
    compacted = journal.compact(5)
    assert compacted["healthy"]
    assert compacted["retained_after"] == 4
    assert journal.read_after(4) == records[4:]
    assert journal.append(event(text="resumed"))["ordinal"] == 6
    journal.close()


def test_partial_segment_and_invalid_checkpoint_never_drop_events(tmp_path):
    journal = FileRuntimeEventJournal(tmp_path, segment_bytes=2000)
    journal.start()
    records = [journal.append(event(text=str(i))) for i in range(5)]
    assert journal.compact(1)["removed_segments"] == 0
    assert journal.read_after(0) == records
    with pytest.raises(OSError, match="checkpoint"):
        journal.compact(6)
    assert journal.read_after(0) == records
    journal.close()


def test_compaction_cannot_clear_unknown_write_failure(tmp_path, monkeypatch):
    journal, _ = filled(tmp_path)
    with monkeypatch.context() as patch:
        def fail(*args):
            raise OSError("fixture uncertain write")
        patch.setattr(os, "fsync", fail)
        with pytest.raises(OSError, match="uncertain"):
            journal.append(event(text="uncertain"))
    with pytest.raises(OSError, match="validated writer"):
        journal.compact(5)
    journal.close()


@pytest.mark.parametrize("cut", ["before_manifest", "after_manifest"])
def test_crash_during_retention_keeps_a_valid_recovery_boundary(tmp_path, monkeypatch, cut):
    journal, records = filled(tmp_path)
    with monkeypatch.context() as patch:
        if cut == "before_manifest":
            def fail(*args):
                raise OSError("fixture rename cut")
            patch.setattr(os, "replace", fail)
        else:
            def fail(*args, **kwargs):
                raise OSError("fixture deletion cut")
            patch.setattr(type(journal.root), "unlink", fail)
        with pytest.raises(OSError, match="fixture"):
            journal.compact(3)
    journal.close()
    journal.start()
    if cut == "before_manifest":
        assert journal.read_after(0) == records
    else:
        assert journal.read_after(3) == records[3:]
        assert journal.compact(3)["removed_segments"] == 3
    journal.close()


def test_retention_surfaces_preserve_database_results_and_reject_foreign_actor(runtime):
    deps, client, _, _, operator, caller = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    ingress = deps.harness_supervisor.event_ingress
    ingress.journal.segment_bytes = 900
    for i in range(5):
        deps.harness_supervisor._handle_event(sid, event(sid, text=str(i)))
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = uow.connection.execute("SELECT count(*) FROM runtime_results").fetchone()[0]
    assert before == 5
    forbidden = client.post("/api/v1/harness/journal", headers={"x-api-key": caller}, json={"compact": True})
    assert forbidden.status_code == 403
    assert not tool(client, caller, "harness_list", {"view": "journal", "compact": True})["ok"]
    compact = tool(client, operator, "harness_list", {"view": "journal", "compact": True})
    assert compact["ok"], compact
    assert compact["data"]["removed_segments"] >= 1
    status = client.post("/api/v1/harness/journal", headers={"x-api-key": operator}, json={})
    assert status.status_code == 200
    assert status.json()["data"]["watermark"] == compact["data"]["watermark"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_results").fetchone()[0] == before
    assert ingress.recover() == 0
    # Restoring an older DB independently must be refused, not silently skip
    # captured records whose journal segments have been compacted.
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_journal_checkpoint SET ordinal=0")
    try:
        with pytest.raises(OSError, match="cursor expired"):
            ingress.recover()
    finally:
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE runtime_journal_checkpoint SET ordinal=?", (status.json()["data"]["watermark"],))
