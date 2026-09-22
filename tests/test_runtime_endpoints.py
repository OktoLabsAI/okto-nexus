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
            uow.connection.execute("INSERT INTO harness_sessions(session_id,kind,owning_agent_id,status,capabilities,started_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                ("legacy-session", "pi", "legacy", "RUNNING", "{}", "old", "old", "old"))
    assert 30 in MigrationRunner(factory).apply()
    assert MigrationRunner(factory).apply() == []
    with factory.unit_of_work(write=False) as uow:
        after = dict(uow.connection.execute("SELECT * FROM agents WHERE agent_id='legacy'").fetchone())
        assert after == before
        assert not uow.connection.execute("SELECT * FROM agent_endpoints").fetchall()
        if last_version == 29:
            row = uow.connection.execute("SELECT * FROM harness_sessions").fetchone()
            assert row["status"] == "RUNNING"  # historical status retained, no false end timestamp
            assert row["lifecycle_state"] == "legacy_unlinked"
            assert row["endpoint_id"] is None
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


def test_p03_presence_uses_canonical_session_and_close_only_owns_its_binding(runtime):
    deps, client, _, _, key, _ = runtime
    opened = open_rest(runtime).json()["data"]
    assert opened["endpoint_id"] == "endpoint-pi"
    assert opened["lifecycle_state"] == "protocol_ready"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        presence = deps.repos.sessions.get(uow, opened["presence_session_id"])
        assert presence.status == "active"
        assert presence.agent_id == "worker"
        assert presence.workspace_id == opened["workspace_id"]
    assert tool(client, key, "harness_close", {"session_id": opened["session_id"]})["ok"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert deps.repos.sessions.get(uow, opened["presence_session_id"]).status == "closed"
        assert uow.connection.execute("SELECT lifecycle_state FROM harness_sessions WHERE session_id=?",
                                      (opened["session_id"],)).fetchone()[0] == "detached"


def test_p03_diagnostics_are_operator_only_and_do_not_infer_liveness(runtime):
    _, client, _, _, key, caller_key = runtime
    response = client.get("/api/v1/harness/diagnostics", headers={"x-api-key": key})
    assert response.status_code == 200
    assert response.json()["data"]["live"] is False
    assert response.json()["data"]["legacy_sessions"] == []
    assert client.get("/api/v1/harness/diagnostics", headers={"x-api-key": caller_key}).status_code == 403


@pytest.mark.parametrize("target", [{"strategy": "broadcast"}, {"strategy": "role", "role": "reviewer"},
    {"strategy": "capability", "capability": "review"},
    {"strategy": "tag", "selector": {"team": ["fixture"]}}])
def test_p03_presence_participates_in_canonical_routing_without_manual_session_insert(runtime, target):
    deps, client, root, peers, key, _ = runtime
    if target["strategy"] == "capability":
        assert client.post("/api/v1/capabilities", headers={"x-api-key": key},
                           json={"name": "review"}).status_code == 200
    if target["strategy"] == "tag":
        headers = {"x-api-key": key}
        assert client.post("/api/v1/tags", headers=headers, json={"key": "team"}).status_code == 200
        assert client.post("/api/v1/tags/team/values", headers=headers, json={"value": "fixture"}).status_code == 200
        assert client.patch("/api/v1/agents/worker", headers=headers,
                            json={"tags": {"team": ["fixture"]}}).status_code == 200
    assert open_rest(runtime).status_code == 200
    result = send_message(runtime, subject="presence fixture", body="one response", target=target)
    assert result["delivered_count"] == 1
    wait_sent(peers)


def test_p03_ambiguous_endpoint_selection_does_not_construct_connector(runtime):
    _, client, root, peers, key, _ = runtime
    created = client.post("/api/v1/harness/endpoints", headers={"x-api-key": key}, json={
        "endpoint_id": "second-pi", "agent_id": "worker", "adapter_id": "pi",
        "profile_id": "profile-pi", "project_root": root, "enabled": True})
    assert created.status_code == 200, created.text
    response = open_rest(runtime)
    assert response.status_code == 409, response.text
    assert "AMBIGUOUS_BINDING" in response.text
    assert peers == []
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": key}, json={
        "agent_id": "worker", "kind": "pi", "project_root": root, "endpoint_id": "second-pi"})
    assert opened.status_code == 200, opened.text


def test_p03_runtime_cannot_override_approved_environment(runtime):
    _, client, root, peers, key, _ = runtime
    result = tool(client, key, "harness_open", {"agent_id": "worker", "kind": "codex",
        "project_root": root, "backend": {"env": {"PATH": "unapproved"}}})
    assert result["error"]["code"] == "VALIDATION_ERROR"
    assert peers == []


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
