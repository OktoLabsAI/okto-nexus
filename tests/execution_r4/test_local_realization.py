"""Public embedded preparation joins the canonical binding flow without Connector."""
from dataclasses import asdict
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from nexus_connector_core import InstallationCandidate
from nexus_connector_core.discovery import fingerprint

from okto_nexus.bootstrap import embedded_inventory
from okto_nexus.application import execution_local_realizations as local
from test_embedded_inventory import app_for, wait_inventory
from test_binding_operator import prepare_operator


@pytest.fixture
def local_setup(tmp_path, monkeypatch, request):
    adapter = getattr(request, "param", "codex_app_server")
    adapter, trust = adapter if isinstance(adapter, tuple) else (adapter, 'selected')
    binary = tmp_path / ("pi.exe" if adapter == "pi_rpc" else "codex.exe")
    binary.write_bytes(b"Local realization technical candidate")
    candidate = InstallationCandidate(adapter, str(binary), fingerprint(binary), "explicit", trust)
    monkeypatch.setattr(embedded_inventory, "discover_local_candidates",
                        lambda **_: SimpleNamespace(candidates=tuple(c for c in (candidate,) if not _.get('adapter_ids') or c.adapter_id in _['adapter_ids'])))
    root = tmp_path / "workspace"
    root.mkdir()
    deps, app = app_for(tmp_path / "home")
    headers = {}
    with deps.connection_factory.unit_of_work() as uow:
        for actor in ("operator", "subject"):
            uow.connection.execute("INSERT OR IGNORE INTO agents(agent_id,created_at) VALUES (?,?)", (actor,deps.clock.now_iso()))
            existing = getattr(app.state, "test_existing_keys", {})
            headers[actor] = {"Authorization":"Bearer " + (existing.get(actor) or app.state.auth.issue_key(uow,agent_id=actor))}
    with TestClient(app, raise_server_exceptions=False, client=('127.0.0.1', 50000)) as client:
        wait_inventory(client)
        owner = app.state.embedded_inventory_owner
        inventory = client.get(f"/v1/runtime/executors/{owner.key.executor_id}/inventory",headers=headers["operator"]).json()["snapshot"]
        body = dict(client_intent_id="local-setup",agent_id="subject",workspace_root=str(root),
            workspace_id=None,workspace_label="Local project",adapter_id=candidate.adapter_id,
            candidate_ref=inventory["evidence"][0]["candidate_ref"],inventory_revision=inventory["inventory_revision"],
            local_consent_id="operator-consent",approved=True,provider_home=None,
            secret_bindings={"OPENAI_API_KEY":"vault:provider-key"})
        yield deps, app, client, headers, body, candidate, root


def publish(setup, *, actor="operator", changes=None):
    _, app, client, headers, body, _, _ = setup
    route=f"/v1/runtime/executors/{app.state.embedded_inventory_owner.key.executor_id}/realizations"
    return client.post(route,json=body | (changes or {}),headers=headers[actor])


def test_local_preparation_and_binding_use_public_canonical_flow(local_setup):
    deps, app, client, headers, body, candidate, root = local_setup
    prepared = publish(local_setup)
    assert prepared.status_code == 201, prepared.text
    view = prepared.json()
    assert str(root) not in prepared.text and str(candidate.executable) not in prepared.text
    assert "provider-key" not in prepared.text
    schema=json.loads((Path(__file__).parents[2]/"plans/contratos/http-target.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator({"$defs":schema["$defs"],"$ref":"#/$defs/RealizationPublishRequest"}).validate(body)
    replay=publish(local_setup)
    assert replay.status_code == 200 and replay.json() == view
    assert publish(local_setup, changes={"local_consent_id":"different"}).status_code == 409
    with deps.connection_factory.unit_of_work(write=False) as uow:
        record=json.loads(uow.connection.execute("SELECT local_record_json FROM execution_local_realizations").fetchone()[0])
        assert record["candidate"] == asdict(candidate)
        assert record["root"]["path"] == str(root.resolve())
        assert record["configuration"]["secret_bindings"] == body["secret_bindings"]
        assert uow.connection.execute("SELECT status FROM execution_realizations").fetchone()[0] == "PENDING_APPROVAL"
        stored_root = uow.connection.execute("SELECT root_realpath FROM workspaces WHERE workspace_id=?",
                                             (view["workspace_id"],)).fetchone()[0]
        assert stored_root == str(root.resolve())
    request=dict(client_intent_id="prepare-local",agent_id_hint="subject",executor_id=view["executor_id"],
        adapter_id=body["adapter_id"],candidate_ref=body["candidate_ref"],inventory_revision=body["inventory_revision"],
        realization_ref=view["realization_ref"],workspace_id=view["workspace_id"],alias="local-assistant")
    proposal, apply=prepare_operator(client,headers,request)
    assert proposal["can_apply"]
    response=client.post("/v1/connections/bindings:apply",json=apply,headers=headers["operator"])
    assert response.status_code == 200, response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM execution_realizations").fetchone()[0] == "READY"
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_bindings").fetchone()[0] == 1
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_sessions").fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_link_tickets").fetchone()[0] == 0


def _migration_statements():
    from okto_nexus.adapters.outbound.sqlite.migrations import _default_migrations_dir, _split_statements
    script = next(_default_migrations_dir().glob("153_*.sql")).read_text(encoding="utf-8")
    return _split_statements(script)


def test_realization_repairs_workspace_without_root_and_keeps_existing_root(local_setup):
    deps, _, _, _, _, _, root = local_setup
    first = publish(local_setup)
    assert first.status_code == 201, first.text
    workspace_id = first.json()["workspace_id"]
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE workspaces SET root_realpath=NULL WHERE workspace_id=?", (workspace_id,))
    again = publish(local_setup, changes={"client_intent_id": "repair", "local_consent_id": "repair",
                                           "workspace_id": workspace_id})
    assert again.status_code == 201, again.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT root_realpath FROM workspaces WHERE workspace_id=?",
                                      (workspace_id,)).fetchone()[0] == str(root.resolve())
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE workspaces SET root_realpath='/kept/root' WHERE workspace_id=?", (workspace_id,))
    publish(local_setup, changes={"client_intent_id": "keep", "local_consent_id": "keep", "workspace_id": workspace_id})
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT root_realpath FROM workspaces WHERE workspace_id=?",
                                      (workspace_id,)).fetchone()[0] == "/kept/root"


def test_migration_backfills_root_from_realization_and_normalizes_empty_root(local_setup):
    deps, _, _, _, _, _, root = local_setup
    first = publish(local_setup)
    assert first.status_code == 201, first.text
    workspace_id = first.json()["workspace_id"]
    backfill, normalize, *triggers = _migration_statements()
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        conn.execute("DROP TRIGGER workspaces_root_not_empty_insert")
        conn.execute("DROP TRIGGER workspaces_root_not_empty_update")
        conn.execute("UPDATE workspaces SET root_realpath='  ' WHERE workspace_id=?", (workspace_id,))
        conn.execute("INSERT INTO workspaces(workspace_id,root_realpath,created_at) VALUES ('orphan','','2026-01-01T00:00:00Z')")
        conn.execute("INSERT INTO workspaces(workspace_id,created_at) VALUES ('no-source','2026-01-01T00:00:00Z')")
        conn.execute(backfill)
        conn.execute(normalize)
        for trigger in triggers:
            conn.execute(trigger)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        roots = dict(uow.connection.execute("SELECT workspace_id,root_realpath FROM workspaces").fetchall())
    assert roots[workspace_id] == str(root.resolve())
    assert roots["orphan"] is None and roots["no-source"] is None


def test_workspace_write_rejects_empty_root(local_setup):
    import sqlite3
    from okto_nexus.errors import ErrorCode, OktoNexusError
    deps = local_setup[0]
    with pytest.raises(OktoNexusError) as caught:
        with deps.connection_factory.unit_of_work() as uow:
            deps.repos.workspaces.upsert(uow, workspace_id="ws-empty", root_realpath=" ")
    assert caught.value.code == ErrorCode.VALIDATION_ERROR
    with pytest.raises(sqlite3.IntegrityError, match="workspace_root_empty"):
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("INSERT INTO workspaces(workspace_id,root_realpath,created_at) "
                                   "VALUES ('ws-sql','','2026-01-01T00:00:00Z')")
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO workspaces(workspace_id,root_realpath,created_at) "
                               "VALUES ('ws-ok','/ok','2026-01-01T00:00:00Z')")
    with pytest.raises(sqlite3.IntegrityError, match="workspace_root_empty"):
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE workspaces SET root_realpath='' WHERE workspace_id='ws-ok'")


def test_non_operator_cannot_probe_local_directories(local_setup,monkeypatch):
    def forbidden(_):
        raise AssertionError("Filesystem access preceded operator authentication")
    monkeypatch.setattr(local,"directory_identity",forbidden)
    assert publish(local_setup,actor="subject").status_code == 403


@pytest.mark.parametrize("changes",[
    {"approved":False},{"approved":1},{"secret_bindings":{"OPENAI_API_KEY":"plaintext"}},
    {"secret_bindings":{"OPENAI_API_KEY":"vault:nxc4_secret"}},{"environment":{"OPENAI_API_KEY":"plaintext"}},
    {"workspace_root":"relative"},
])
def test_invalid_local_consent_or_configuration_never_persists(local_setup,changes):
    response=publish(local_setup,changes=changes)
    assert response.status_code in (400,409,422),response.text
    with local_setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_realizations").fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_local_realizations").fetchone()[0] == 0


@pytest.mark.parametrize("change",["root","binary","owner","policy"])
def test_preparation_refuses_changed_local_evidence(local_setup,monkeypatch,change):
    deps,app,_,_,_,candidate,root=local_setup
    if change in ("root","binary"):
        assert publish(local_setup).status_code == 201
    if change=="root":
        other=root.with_name("previous-workspace")
        assert root.resolve().parent == other.resolve().parent == root.parent.resolve()
        root.rename(other)
        root.mkdir()
    elif change=="binary":
        Path(candidate.executable).write_bytes(b"Different selected build")
    else:
        original=local.directory_identity
        changed=False
        def race(value):
            nonlocal changed
            result=original(value)
            if not changed:
                changed=True
                with deps.connection_factory.unit_of_work() as uow:
                    if change=="owner":
                        uow.connection.execute("UPDATE execution_executors SET generation=generation+1 WHERE kind='embedded'")
                    else:
                        uow.connection.execute("UPDATE agents SET is_active=0 WHERE agent_id='subject'")
            return result
        monkeypatch.setattr(local,"directory_identity",race)
    response=publish(local_setup)
    assert response.status_code == 409,response.text


def test_local_and_public_realization_roll_back_together(local_setup):
    deps=local_setup[0]
    with deps.connection_factory.unit_of_work() as uow:
        before=uow.connection.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0]
        uow.connection.execute("CREATE TRIGGER fail_local BEFORE INSERT ON execution_local_realizations BEGIN SELECT RAISE(ABORT,'local record failure'); END")
    assert publish(local_setup).status_code == 500
    with deps.connection_factory.unit_of_work() as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_realizations").fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_workspace_bindings").fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0] == before
        uow.connection.execute("DROP TRIGGER fail_local")
    assert publish(local_setup).status_code == 201


def test_prepared_local_mapping_survives_serve_restart(tmp_path, monkeypatch):
    binary = tmp_path / "codex.exe"
    binary.write_bytes(b"Persistent technical candidate")
    candidate = InstallationCandidate("codex_app_server", str(binary), fingerprint(binary), "explicit", "selected")
    monkeypatch.setattr(embedded_inventory, "discover_local_candidates",
                        lambda **_: SimpleNamespace(candidates=tuple(c for c in (candidate,) if not _.get('adapter_ids') or c.adapter_id in _['adapter_ids'])))
    root = tmp_path / "workspace"
    root.mkdir()
    deps, app = app_for(tmp_path / "home")
    with deps.connection_factory.unit_of_work() as uow:
        key = app.state.auth.issue_key(uow, agent_id="operator")
    headers = {"Authorization": "Bearer " + key}
    with TestClient(app) as client:
        wait_inventory(client)
        owner = app.state.embedded_inventory_owner
        route = f"/v1/runtime/executors/{owner.key.executor_id}/realizations"
        snapshot = client.get(f"/v1/runtime/executors/{owner.key.executor_id}/inventory", headers=headers).json()["snapshot"]
        body = dict(client_intent_id="restart-local", agent_id="operator", workspace_root=str(root),
                    workspace_id=None, workspace_label="Persistent project", adapter_id=candidate.adapter_id,
                    candidate_ref=snapshot["evidence"][0]["candidate_ref"], inventory_revision=snapshot["inventory_revision"],
                    local_consent_id="restart-consent", approved=True)
        first = client.post(route, json=body, headers=headers)
        assert first.status_code == 201, first.text
        generation = owner.generation
    deps, app = app_for(tmp_path / "home")
    with TestClient(app) as client:
        wait_inventory(client)
        assert app.state.embedded_inventory_owner.generation > generation
        replay = client.post(route, json=body, headers=headers)
        assert replay.status_code == 200, replay.text
        assert replay.json() == first.json()
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT COUNT(*) FROM execution_local_realizations").fetchone()[0] == 1
            assert uow.connection.execute("SELECT COUNT(*) FROM execution_realizations").fetchone()[0] == 1
