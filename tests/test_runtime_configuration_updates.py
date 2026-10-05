"""Operator changes invalidate prior execution authority without losing history."""
from concurrent.futures import ThreadPoolExecutor
import pytest

from test_pr34_remediation import runtime as runtime_fixture, open_rest, tool
from test_runtime_grants import issue
from test_runtime_commands import wait_close_result

runtime = runtime_fixture


def test_profile_disable_fences_send_preserves_session_and_allows_operator_close(runtime):
    deps, client, _, peers, operator, caller = runtime
    session = open_rest(runtime).json()["data"]["session_id"]
    grant = issue(runtime, ["send", "open"])
    headers = {"x-api-key": operator}
    before = client.get("/api/v1/agents/worker", headers=headers).json()
    updated = client.patch("/api/v1/harness/profiles/profile-pi", headers=headers,
        json={"expected_revision": 1, "enabled": False})
    assert updated.status_code == 200, updated.text
    for key in (caller, operator):
        denied = tool(client, key, "harness_send", {"session_id": session, "payload": {"text": "must not execute"}})
        assert not denied["ok"] and denied["error"]["code"] == "PERMISSION_DENIED", denied
    assert not peers[0].sent
    assert client.get("/api/v1/agents/worker", headers=headers).json() == before
    closed = tool(client, operator, "harness_close", {"session_id": session})
    assert closed["ok"], closed
    wait_close_result(client, operator, closed)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT revoked_at FROM runtime_execution_grants WHERE grant_id=?", (grant["grant_id"],)).fetchone()[0]
        assert uow.connection.execute("SELECT count(*) FROM harness_sessions WHERE session_id=?", (session,)).fetchone()[0] == 1


def test_endpoint_disable_and_reenable_require_cas_and_never_restore_old_grant(runtime):
    deps, client, root, peers, operator, caller = runtime
    issue(runtime, ["open"])
    for revision, enabled in ((1, False), (2, True)):
        response = tool(client, operator, "harness_list", {"view": "endpoints", "maintenance": {
            "action": "update", "endpoint_id": "endpoint-pi", "expected_revision": revision, "enabled": enabled}})
        assert response["ok"] and response["data"]["revision"] == revision + 1, response
    denied = tool(client, caller, "harness_open", {"agent_id": "worker", "kind": "pi", "project_root": root,
        "endpoint_id": "endpoint-pi"})
    assert not denied["ok"] and not peers, denied
    stale = client.patch("/api/v1/harness/endpoints/endpoint-pi", headers={"x-api-key": operator},
        json={"expected_revision": 1, "enabled": False})
    assert stale.status_code == 409, stale.text
    assert open_rest(runtime).status_code == 200
    with deps.connection_factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute("SELECT old_revision,new_revision FROM runtime_access_audit WHERE action='config.endpoint.update'").fetchall()
        assert [tuple(row) for row in rows] == [(1, 2), (2, 3)]


def test_profile_updates_are_atomic_and_do_not_erase_omitted_fields(runtime):
    deps, client, root, _, operator, _ = runtime
    headers = {"x-api-key": operator}
    assert client.post("/api/v1/harness/profiles", headers=headers, json={"profile_id": "isolated-profile",
        "adapter_id": "codex", "config": {"env": {"CODEX_HOME": root}},
        "secret_refs": {"FIXTURE_KEY": "env:FIXTURE_SOURCE"}}).status_code == 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(lambda _: client.patch("/api/v1/harness/profiles/isolated-profile", headers=headers,
            json={"expected_revision": 1, "enabled": True}), range(2)))
    assert sorted(r.status_code for r in replies) == [200, 409]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        from okto_nexus.adapters.outbound.sqlite.endpoints_repo import SqliteEndpointRepo
        profile = SqliteEndpointRepo().profile(uow, "isolated-profile")
        assert profile["revision"] == 2 and profile["config"]["env"]["CODEX_HOME"] == root
        assert profile["secret_refs"] == {"FIXTURE_KEY": "env:FIXTURE_SOURCE"}
        audit = [dict(r) for r in uow.connection.execute("SELECT * FROM runtime_access_audit WHERE resource_id='isolated-profile'")]
        assert len(audit) == 2
        assert all("FIXTURE_SOURCE" not in str(row) and root not in str(row) for row in audit)
    diagnostic = client.get("/api/v1/harness/diagnostics", headers=headers)
    assert diagnostic.status_code == 200, diagnostic.text
    edits = [r for r in diagnostic.json()["data"]["configuration_changes"] if r["resource_id"] == "isolated-profile"]
    assert len(edits) == 2 and edits[0]["changed_fields"] == ["enabled"]


def test_profile_rebinding_refuses_live_session_and_revokes_equal_revision_grant(runtime):
    _, client, root, _, operator, caller = runtime
    headers = {"x-api-key": operator}
    issue(runtime, ["open"])
    assert client.post("/api/v1/harness/profiles", headers=headers, json={
        "profile_id": "second-pi", "adapter_id": "pi", "enabled": True}).status_code == 200
    session = open_rest(runtime).json()["data"]["session_id"]
    body = {"expected_revision": 1, "profile_id": "second-pi"}
    blocked = client.patch("/api/v1/harness/endpoints/endpoint-pi", headers=headers, json=body)
    assert blocked.status_code == 409, blocked.text
    closed = tool(client, operator, "harness_close", {"session_id": session})
    wait_close_result(client, operator, closed)
    changed = client.patch("/api/v1/harness/endpoints/endpoint-pi", headers=headers, json=body)
    assert changed.status_code == 200, changed.text
    denied = tool(client, caller, "harness_open", {"agent_id": "worker", "kind": "pi", "project_root": root,
        "endpoint_id": "endpoint-pi"})
    assert not denied["ok"], denied


@pytest.mark.parametrize("kind", ["profile", "endpoint"])
def test_mutation_disables_boot_and_does_not_restore_grants_after_reenable(runtime, kind):
    deps, client, _, _, operator, caller = runtime
    headers = {"x-api-key": operator}
    grant = issue(runtime, ["open"])
    assert client.put("/api/v1/harness/endpoints/endpoint-pi/boot", headers=headers,
        json={"expected_revision": 1, "enabled": True}).status_code == 200
    view, key, identity = ("profiles", "profile_id", "profile-pi") if kind == "profile" else ("endpoints", "endpoint_id", "endpoint-pi")
    denied = tool(client, caller, "harness_list", {"view": view, "maintenance": {
        "action": "update", key: identity, "expected_revision": 1, "enabled": False}})
    assert not denied["ok"] and denied["error"]["code"] == "PERMISSION_DENIED", denied
    for revision, enabled in ((1, False), (2, True)):
        response = tool(client, operator, "harness_list", {"view": view, "maintenance": {
            "action": "update", key: identity, "expected_revision": revision, "enabled": enabled}})
        assert response["ok"], response
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT enabled FROM runtime_boot_bindings WHERE endpoint_id='endpoint-pi'").fetchone()[0] == 0
        assert uow.connection.execute("SELECT revoked_at FROM runtime_execution_grants WHERE grant_id=?", (grant["grant_id"],)).fetchone()[0]


@pytest.mark.parametrize("body", [{"config": {"sandbox": "danger-full-access"}}, {"enabled": None},
    {"config": None}, {"secret_refs": None}, {"adapter_id": "pi"}, {}])
def test_invalid_profile_update_cannot_alter_revision(runtime, body):
    deps, client, _, _, operator, _ = runtime
    response = client.patch("/api/v1/harness/profiles/profile-codex", headers={"x-api-key": operator},
        json={"expected_revision": 1, **body})
    assert response.status_code == 422, response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT revision FROM runtime_profiles WHERE profile_id='profile-codex'").fetchone()[0] == 1


def test_configuration_commit_failure_rolls_back_grant_boot_and_revision(runtime, monkeypatch):
    from okto_nexus.adapters.outbound.sqlite.endpoints_repo import SqliteEndpointRepo
    deps, client, _, _, operator, _ = runtime
    headers = {"x-api-key": operator}
    grant = issue(runtime, ["open"])
    assert client.put("/api/v1/harness/endpoints/endpoint-pi/boot", headers=headers,
        json={"expected_revision": 1, "enabled": True}).status_code == 200
    audit = SqliteEndpointRepo.audit_configuration
    def fail(self, uow, **kwargs):
        audit(self, uow, **kwargs)
        raise OSError("fixture configuration commit cut")
    with monkeypatch.context() as patch:
        patch.setattr(SqliteEndpointRepo, "audit_configuration", fail)
        response = client.patch("/api/v1/harness/profiles/profile-pi", headers=headers,
            json={"expected_revision": 1, "enabled": False})
        assert response.status_code == 500
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert tuple(uow.connection.execute("SELECT revision,enabled FROM runtime_profiles WHERE profile_id='profile-pi'").fetchone()) == (1, 1)
        assert uow.connection.execute("SELECT revoked_at FROM runtime_execution_grants WHERE grant_id=?", (grant["grant_id"],)).fetchone()[0] is None
        assert uow.connection.execute("SELECT enabled FROM runtime_boot_bindings WHERE endpoint_id='endpoint-pi'").fetchone()[0] == 1
        assert not uow.connection.execute("SELECT 1 FROM runtime_access_audit WHERE action='config.profile.update'").fetchone()


def test_configuration_audit_upgrade_preserves_old_access_rows(tmp_path):
    import shutil
    from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner, _default_migrations_dir
    from test_migrations import make_factory
    old = tmp_path / "schema52"
    old.mkdir()
    for migration in _default_migrations_dir().glob("*.sql"):
        if int(migration.name.split("_", 1)[0]) <= 52:
            shutil.copy(migration, old)
    factory = make_factory(tmp_path)
    MigrationRunner(factory, migrations_dir=old).apply()
    with factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO runtime_access_audit(request_id,action,decision,created_at) VALUES('legacy-audit','read','deny','2026-09-23T00:00:00Z')")
    assert MigrationRunner(factory).apply()[0] == 53
    assert MigrationRunner(factory).apply() == []
    with factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT * FROM runtime_access_audit WHERE request_id='legacy-audit'").fetchone()
        assert row["action"] == "read" and row["decision"] == "deny"
        assert row["resource_kind"] is None and row["old_revision"] is None
        assert not uow.connection.execute("SELECT 1 FROM delivery_outbox").fetchone()
        assert uow.connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_profile_disable_preserves_late_native_terminal_without_publishing(runtime):
    from test_pr34_remediation import send_message
    from test_runtime_commands import codex_session, wait_operation
    from test_runtime_result_publication import result
    deps, client, _, _, operator, _ = runtime
    session = codex_session(runtime)
    source = send_message(runtime, body="TRIGGER_HOLD")
    operation = source["runtime_operations"][0]
    wait_operation(runtime, operation, lambda row: row["external_acceptance"] == "observed")
    response = client.patch("/api/v1/harness/profiles/profile-codex", headers={"x-api-key": operator},
        json={"expected_revision": 1, "enabled": False})
    assert response.status_code == 200, response.text
    interrupted = tool(client, operator, "harness_interrupt", {"session_id": session, "expected_operation_id": operation})
    assert interrupted["ok"], interrupted
    wait_operation(runtime, operation, lambda row: row["result_durable"])
    captured = result(runtime, operation, "BLOCKED")
    assert captured["delivery_outcome"] == "interrupted" and not captured["publication_message_id"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
        assert uow.connection.execute("SELECT count(*) FROM harness_events WHERE operation_id=? AND delivery_phase='terminal'", (operation,)).fetchone()[0] == 1


def test_profile_change_after_send_intent_fences_native_write(runtime, monkeypatch):
    import threading
    from test_pr34_remediation import send_message
    from test_runtime_commands import wait_operation
    deps, client, _, peers, operator, _ = runtime
    assert open_rest(runtime).status_code == 200
    entered, release = threading.Event(), threading.Event()
    dispatch = deps.runtime_dispatcher.dispatch
    def before_dispatch(operation):
        entered.set()
        assert release.wait(10)
        dispatch(operation)
    monkeypatch.setattr(deps.runtime_dispatcher, "dispatch", before_dispatch)
    try:
        message = send_message(runtime)
        assert entered.wait(5)
        changed = client.patch("/api/v1/harness/profiles/profile-pi", headers={"x-api-key": operator},
            json={"expected_revision": 1, "enabled": False})
        assert changed.status_code == 200, changed.text
    finally:
        release.set()
    row = wait_operation(runtime, message["runtime_operations"][0], lambda row: row["state"] == "OUTCOME_UNKNOWN")
    assert row["external_acceptance"] == "not_observed"
    assert not peers[0].sent
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
