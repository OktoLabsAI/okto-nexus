"""Exercise the operator's combined offline procedure on production runtime data."""
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.application.runtime_shutdown import shutdown_runtime
from test_pr34_remediation import runtime as runtime_fixture, send_message, open_rest
from test_runtime_artifact_durability import large_output_session
from test_runtime_result_publication import result

runtime = runtime_fixture
spec = importlib.util.spec_from_file_location("offline_runtime_backup",
    Path(__file__).parents[1] / "plans/pr34-remediation/offline_runtime_backup.py")
procedure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(procedure)


def quiesced_snapshot(runtime, tmp_path):
    deps = runtime[0]
    large_output_session(runtime)
    source = send_message(runtime, body="backup fixture")
    published = result(runtime, source["runtime_operations"][0], "PUBLISHED")
    assert published["output_artifact_id"]
    assert shutdown_runtime(deps.runtime_dispatcher, deps.harness_supervisor)["state"] == "drained"
    snapshot = tmp_path / "snapshot"
    report = procedure.backup(deps.config.home_dir, snapshot, stopped=True)
    return snapshot, report, source, published


def test_combined_snapshot_restores_identity_history_journal_and_artifact_without_native_replay(runtime, tmp_path):
    snapshot, report, source, published = quiesced_snapshot(runtime, tmp_path)
    restored_home = procedure.restore(snapshot, tmp_path / "restored", stopped=True)
    assert procedure.validate(restored_home) == report
    restored = bootstrap({}, ["--home", str(restored_home), "--feature-harness-integrations", "true"])
    launches = []
    def forbidden(**kwargs):
        launches.append(kwargs)
        raise AssertionError("Restoring history must not replay native work")
    restored.harness_connector_factories = {kind: forbidden for kind in ("pi", "codex", "claude_code")}
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
        assert restored.repos.artifact_store.read_bytes(artifact.storage_path) == b"L" * 70000
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


def test_backup_refuses_active_owner_and_requires_explicit_quiescence(runtime, tmp_path):
    deps = runtime[0]
    destination = tmp_path / "refused"
    with pytest.raises(ValueError, match="acknowledgement"):
        procedure.backup(deps.config.home_dir, destination)
    with pytest.raises((OSError, ValueError)):
        procedure.backup(deps.config.home_dir, destination, stopped=True)
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


def test_restore_preserves_uncertain_delivery_fence_with_admission_initially_off(runtime, tmp_path):
    from test_runtime_outbox import wait_status
    deps = runtime[0]
    assert open_rest(runtime).status_code == 200
    operation_id = send_message(runtime)["runtime_operations"][0]
    original = wait_status(runtime, operation_id, "SENT_UNCONFIRMED")
    assert shutdown_runtime(deps.runtime_dispatcher, deps.harness_supervisor)["state"] == "drained"
    snapshot = tmp_path / "uncertain-snapshot"
    procedure.backup(deps.config.home_dir, snapshot, stopped=True)
    restored_home = procedure.restore(snapshot, tmp_path / "uncertain-restored", stopped=True)
    restored = bootstrap({}, ["--home", str(restored_home), "--feature-harness-integrations", "false"])
    assert not restored.config.feature_harness_integrations
    launches = []
    def forbidden(**kwargs):
        launches.append(kwargs)
        raise AssertionError("Uncertain operation must never replay on restore")
    restored.harness_connector_factories = {kind: forbidden for kind in ("pi", "codex", "claude_code")}
    with TestClient(build_app(restored)) as client:
        inspected = client.get("/api/v1/harness/outbox", headers={"x-api-key": runtime[4]},
            params={"operation_id": operation_id})
        assert inspected.status_code == 200, inspected.text
        with restored.connection_factory.unit_of_work(write=False) as uow:
            row = restored.runtime_dispatcher.repo.get(uow, operation_id)
            assert row["status"] == "OUTCOME_UNKNOWN" and row["terminal_event_id"] is None
            assert row["attempt_id"] == original["attempt_id"]
            delivery = uow.connection.execute("SELECT consumer_kind,consumer_operation_id,status FROM message_deliveries WHERE delivery_id=?", (row["delivery_id"],)).fetchone()
            assert tuple(delivery) == ("push", operation_id, "unread")
        assert not launches


def test_offline_backup_still_refuses_an_unexpired_owner_lease(runtime, tmp_path):
    from okto_nexus.domain.base import iso_plus
    deps = runtime[0]
    assert shutdown_runtime(deps.runtime_dispatcher, deps.harness_supervisor)["state"] == "drained"
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_dispatcher_owner SET lease_expires_at=?",
            (iso_plus(deps.clock.now_iso(), 300),))
    with pytest.raises(ValueError, match="lease is still live"):
        procedure.backup(deps.config.home_dir, tmp_path / "refused", stopped=True)
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
