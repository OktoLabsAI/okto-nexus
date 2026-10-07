"""Offline snapshots preserve canonical output and retained legacy journals."""
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.domain.harness import HarnessEvent
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract
from test_canonical_delivery import connected_local
from test_canonical_result_artifact import large_result
from test_canonical_result_publication import wait_result, workspace

spec = importlib.util.spec_from_file_location("canonical_offline_backup",
    Path(__file__).parents[2] / "tools/offline_runtime_backup.py")
procedure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(procedure)


@pytest.fixture
def runtime(tmp_path, monkeypatch, request):
    with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, request) as setup:
        connected = connected_local.__wrapped__(setup)
        deps, _, _, headers, *_ = setup
        large_result(connected, monkeypatch)
        published = wait_result(setup, "PUBLISHED")
        source = dict(workspace_id=workspace(setup), runtime_operations=[published["operation_id"]])
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("INSERT INTO harness_sessions(session_id,kind,owning_agent_id,status,"
                "capabilities,started_at,ended_at,created_at,updated_at) VALUES "
                "('retained-backup','codex','subject','ENDED','{}','2026-09-22','2026-09-22',"
                "'2026-09-22','2026-09-22')")
        deps.harness_supervisor.event_ingress.capture(HarnessEvent(session_id="retained-backup",
            harness_kind="codex", kind="turn_completed", native_event="retained/complete",
            occurred_at="2026-09-22T00:00:00Z", payload=dict(text="Retained journal evidence")))
        operator = headers["operator"]["Authorization"].removeprefix("Bearer ")
    assert connected[2].native.stopped and len(connected[2].native.sent) == 1
    return deps, source, published, None, operator


def quiesced_snapshot(runtime, tmp_path):
    deps, source, published, *_ = runtime
    snapshot = tmp_path / "snapshot"
    report = procedure.backup(deps.config.home_dir, snapshot, stopped=True)
    assert any(name.startswith("core-runtime/session-") for name in report["files"])
    assert any(name.startswith("runtime-journal-v1/") for name in report["files"])
    return snapshot, report, source, published


def test_combined_snapshot_restores_identity_history_journal_and_artifact_without_native_replay(runtime, tmp_path, monkeypatch):
    snapshot, report, source, published = quiesced_snapshot(runtime, tmp_path)
    restored_home = procedure.restore(snapshot, tmp_path / "restored", stopped=True)
    assert procedure.validate(restored_home) == report
    restored = bootstrap({}, ["--home", str(restored_home), "--feature-harness-integrations", "true"])
    launches = []
    def forbidden(**kwargs):
        launches.append(kwargs)
        raise AssertionError("Restoring history must not replay native work")
    restored.harness_connector_factories = {kind: forbidden for kind in ("pi", "codex", "claude_code")}
    from nexus_connector_core.native.runtime_bridge import CopiedAdapterFactory
    async def forbidden_core(*args, **kwargs):
        launches.append("Core native launch")
        raise AssertionError("Restoring history must not replay Core native work")
    monkeypatch.setattr(CopiedAdapterFactory, "open", forbidden_core)
    with TestClient(build_app(restored)) as client:
        with restored.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT * FROM runtime_results WHERE operation_id=?", (source["runtime_operations"][0],)).fetchone()
            assert row["output_artifact_id"] == published["output_artifact_id"]
            artifact = restored.repos.artifacts.get(uow, workspace_id=source["workspace_id"], artifact_id=row["output_artifact_id"])
            assert procedure.database_report(uow.connection)["agent_profile_sha256"] == report["database"]["agent_profile_sha256"]
        # Authentication legitimately touches last_seen_at. Compare restored
        # rows before making the first authenticated request, not after it.
        inspected = client.get("/api/v1/harness/outbox", headers={"x-api-key": runtime[4]},
            params={"operation_id": source["runtime_operations"][0]})
        assert inspected.status_code == 200, inspected.text
        assert restored.repos.artifact_store.read_bytes(artifact.storage_path) == b"L" * 90000
        assert not launches


@pytest.mark.parametrize("damage", ["artifact", "journal", "database"])
def test_restore_refuses_incomplete_or_corrupted_combined_snapshot(runtime, tmp_path, damage):
    snapshot, _, _, _ = quiesced_snapshot(runtime, tmp_path)
    if damage == "artifact":
        next((snapshot / "artifacts").rglob("runtime-result.txt")).unlink()
    elif damage == "journal":
        next((snapshot / "runtime-journal-v1").glob("segment-*.bin")).write_bytes(b"broken")
    else:
        with (snapshot / "nexus.db").open("ab") as stream:
            stream.write(b"changed")
    destination = tmp_path / "refused"
    with pytest.raises(ValueError, match="checksum"):
        procedure.restore(snapshot, destination, stopped=True)
    assert not destination.exists()


@pytest.mark.parametrize("damage", ["missing_reference", "partial_tail", "checkpoint_ahead"])
def test_semantic_validation_checks_references_and_watermarks_even_with_matching_file_hashes(runtime, tmp_path, damage):
    snapshot, manifest, _, _ = quiesced_snapshot(runtime, tmp_path)
    if damage == "missing_reference":
        next((snapshot / "artifacts").rglob("runtime-result.txt")).unlink()
    elif damage == "partial_tail":
        tail = sorted((snapshot / "runtime-journal-v1").glob("segment-*.bin"))[-1]
        with tail.open("ab") as stream:
            stream.write(b"NJR")
    else:
        import sqlite3
        with sqlite3.connect(snapshot / "nexus.db") as db:
            db.execute("UPDATE runtime_journal_checkpoint SET ordinal=ordinal+10000")
            db.commit()
            manifest["database"] = procedure.database_report(db)
    manifest["files"] = procedure.inventory(snapshot)
    (snapshot / "backup-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    before = procedure.inventory(snapshot)
    with pytest.raises((ValueError, OSError), match="artifact|tail|checkpoint"):
        procedure.restore(snapshot, tmp_path / "refused", stopped=True)
    assert procedure.inventory(snapshot) == before, "validation silently repaired or changed backup bytes"
    assert not (tmp_path / "refused").exists()


def test_explicit_database_override_and_no_overwrite(runtime, tmp_path):
    import sqlite3
    snapshot, report, _, _ = quiesced_snapshot(runtime, tmp_path)
    custom = tmp_path / "custom.sqlite"
    with sqlite3.connect(snapshot / "nexus.db") as db, sqlite3.connect(custom) as target:
        db.backup(target)
    alternate = tmp_path / "alternate-backup"
    saved = procedure.backup(runtime[0].config.home_dir, alternate, stopped=True, db_path=custom)
    assert saved["database"] == report["database"]
    before = procedure.inventory(alternate)
    with pytest.raises(FileExistsError):
        procedure.backup(runtime[0].config.home_dir, alternate, stopped=True, db_path=custom)
    with pytest.raises(FileExistsError):
        procedure.restore(snapshot, alternate, stopped=True)
    with pytest.raises(ValueError, match="Confirm"):
        procedure.restore(snapshot, tmp_path / "unapproved")
    assert procedure.inventory(alternate) == before

