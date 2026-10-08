"""P03 integration: additive upgrade, approved profiles, canonical presence."""
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from okto_nexus.adapters.outbound.harness.environment import child_environment, profile_environment
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from okto_nexus.config import NexusConfig
from okto_nexus.errors import OktoNexusError
from test_pr34_remediation import open_rest, tool, send_message, wait_sent
from test_pr34_remediation import runtime as runtime_fixture

runtime = runtime_fixture


@pytest.mark.parametrize("last_version", [28, 29])
def test_p03_additive_upgrade_preserves_agent_and_legacy_history(tmp_path, last_version):
    factory = ConnectionFactory(NexusConfig(home_dir=tmp_path / "store"))
    migration_source = Path(__file__).resolve().parents[1] / "src/okto_nexus/migrations"
    historical = tmp_path / "migrations"
    historical.mkdir()
    for migration in migration_source.glob("*.sql"):
        if int(migration.name.split("_")[0]) <= last_version:
            shutil.copy2(migration, historical / migration.name)
    MigrationRunner(factory, historical).apply()
    with factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO agents(agent_id,role,capabilities,metadata,created_at) VALUES(?,?,?,?,?)",
            ("legacy", "reviewer", '{"review":true}', '{"keep":"original"}', "2026-01-01T00:00:00.000000Z"))
        before = dict(uow.connection.execute("SELECT * FROM agents WHERE agent_id='legacy'").fetchone())
        if last_version == 29:
            from okto_nexus.domain.ids import resolve_workspace_id
            project = tmp_path / "historical-project"
            project.mkdir()
            workspace = resolve_workspace_id(str(project))
            uow.connection.execute("INSERT INTO workspaces(workspace_id,root_realpath,created_at) VALUES(?,?,?)",
                (workspace, str(project), "old"))
            for sid, status, metadata in (("legacy-linked-hint", "RUNNING",
                    json.dumps({"workspace_id": workspace, "project_root": str(project)})),
                    ("legacy-unknown", "INTERRUPTING", None)):
                uow.connection.execute("INSERT INTO harness_sessions(session_id,kind,owning_agent_id,status,capabilities,"
                    "metadata,started_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (sid, "pi", "legacy", status, "{}", metadata, "old", "old", "old"))
                for sequence in (3, 7):
                    uow.connection.execute("INSERT INTO harness_events(event_id,session_id,harness_kind,kind,native_event,"
                        "payload,thread_id,turn_id,occurred_at,sequence,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (f"{sid}-{sequence}", sid, "pi", "output_delta", "message_update",
                         json.dumps({"text": "historical preserved"}), "old-thread", "old-turn", "old", sequence, "old"))
            old_sessions = [dict(row) for row in uow.connection.execute("SELECT * FROM harness_sessions ORDER BY session_id")]
            old_events = [dict(row) for row in uow.connection.execute("SELECT * FROM harness_events ORDER BY event_id")]
    assert 30 in MigrationRunner(factory).apply()
    assert MigrationRunner(factory).apply() == []
    with factory.unit_of_work(write=False) as uow:
        after = dict(uow.connection.execute("SELECT * FROM agents WHERE agent_id='legacy'").fetchone())
        assert {key: after[key] for key in before} == before
        assert after["deleted_at"] is None
        assert not uow.connection.execute("SELECT * FROM agent_endpoints").fetchall()
        assert not uow.connection.execute("SELECT * FROM delivery_outbox").fetchall()
        if last_version == 29:
            sessions = [dict(row) for row in uow.connection.execute("SELECT * FROM harness_sessions ORDER BY session_id")]
            events = [dict(row) for row in uow.connection.execute("SELECT * FROM harness_events ORDER BY event_id")]
            assert len(sessions) == 2 and len(events) == 4
            for row, old in zip(sessions, old_sessions, strict=True):
                assert all(row[key] == value for key, value in old.items())
                # Even a workspace hint does not prove approved profile or
                # authenticated ownership; do not infer those or current cwd.
                assert row["lifecycle_state"] == "legacy_unlinked"
                assert row["endpoint_id"] is None and row["workspace_id"] is None
                assert row["ended_at"] is None
            for row, old in zip(events, old_events, strict=True):
                assert all(row[key] == value for key, value in old.items())
                assert row["operation_id"] is None and row["attempt_id"] is None
        assert not uow.connection.execute("PRAGMA foreign_key_check").fetchall()
    with pytest.raises(OktoNexusError, match="newer|ahead|unknown"):
        MigrationRunner(factory, historical).apply()
    # Online SQLite backup, followed by independent restore verification.
    with factory.unit_of_work(write=False) as uow:
        with sqlite3.connect(tmp_path / "backup.sqlite") as destination:
            uow.connection.backup(destination)
    with sqlite3.connect(tmp_path / "backup.sqlite") as restored:
        assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert restored.execute("SELECT metadata FROM agents WHERE agent_id='legacy'").fetchone()[0] == before["metadata"]




def test_p03_diagnostics_are_operator_only_and_do_not_infer_liveness(runtime):
    _, client, _, _, key, caller_key = runtime
    response = client.get("/api/v1/harness/diagnostics", headers={"x-api-key": key})
    assert response.status_code == 200
    assert response.json()["data"]["live"] is False
    assert response.json()["data"]["legacy_sessions"] == []
    assert client.get("/api/v1/harness/diagnostics", headers={"x-api-key": caller_key}).status_code == 403








def test_p03_profile_environment_isolated_and_operator_key_never_inherited(tmp_path, monkeypatch):
    monkeypatch.setenv("OKTO_NEXUS_API_KEY", "nxs_fixture_operator")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-ambient-model-key")
    monkeypatch.setenv("UNRELATED_ALIAS", "nxs_fixture_operator")
    monkeypatch.setenv("PREFIX_ALIAS", "Bearer nxs_fixture_operator")
    profile = {"profile_id": "test", "inherit_ambient": False, "config": {}, "secret_refs": {}}
    env = child_environment(profile_environment(profile, tmp_path))
    assert "OPENAI_API_KEY" not in env
    assert "OKTO_NEXUS_API_KEY" not in env
    assert "UNRELATED_ALIAS" not in env
    assert str(tmp_path) in env["CODEX_HOME"]
    profile["inherit_ambient"] = True
    env = child_environment(profile_environment(profile, tmp_path))
    assert env["OPENAI_API_KEY"] == "fixture-ambient-model-key"
    assert "nxs_fixture_operator" not in json.dumps(env)


@pytest.mark.parametrize("config", [{"sandbox": "danger-full-access"}, {"approval_policy": "never"},
    {"env": {"API_TOKEN": "fixture-secret"}}, {"env": []},
    {"command": ["C:/fixture/codex.exe", "app-server", "-c", "approval_policy=never"]}])
def test_p03_profile_rejects_unsafe_defaults_and_plain_secrets(runtime, config):
    _, client, _, peers, key, _ = runtime
    response = client.post("/api/v1/harness/profiles", headers={"x-api-key": key}, json={
        "profile_id": "rejected-profile", "adapter_id": "codex", "config": config, "enabled": True})
    assert response.status_code == 422, response.text
    assert peers == []
    assert "fixture-secret" not in response.text
@pytest.mark.parametrize("adapter", ["pi", "claude_code.stream"])
def test_profile_cannot_claim_unimplemented_sandbox_controls(runtime, adapter):
    _, client, _, _, operator_key, _ = runtime
    response = client.post("/api/v1/harness/profiles", headers={"x-api-key": operator_key},
        json={"profile_id": "unsupported-controls", "adapter_id": adapter,
              "config": {"sandbox": "read-only", "approval_policy": "on-request"}})
    assert response.status_code == 422, response.text
