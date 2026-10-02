"""Normative legacy migration acceptance on one preserved database."""
import io
import json
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pytest

from okto_nexus.adapters.inbound.cli.admin import run_admin
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migration_backup import create_migration_backup
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner, _default_migrations_dir
from okto_nexus.config import NexusConfig
from okto_nexus.domain.ids import resolve_workspace_id
from okto_nexus.domain.keys import generate_api_key, hash_api_key
import test_local_realization as local
from test_embedded_dispatch import local_setup, connected_local, qualified_contract
from test_binding_migration import proposal_request
from test_binding_operator import prepare_operator


def test_tn40(tmp_path, monkeypatch, request, qualified_contract):
    """Supported same-version recovery after backfill and a possible native effect."""
    from ns15_restore_cases import restore_case
    restore_case(tmp_path, monkeypatch, request, backfilled_policies=True)


def test_ns15_05():
    """Documentation commands/routes and shipped HTTP-only dashboard guidance."""
    import importlib.util
    import okto_nexus
    root = Path(__file__).resolve().parents[2]
    path = root / 'plans/r4_execution/audit_ns15_05_docs.py'
    spec = importlib.util.spec_from_file_location('ns15_docs_audit', path)
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    audit.main()
    package = Path(okto_nexus.__file__).resolve().parent
    resources = (package / 'adapters/inbound/mcp/resources_docs.py').read_text(encoding='utf-8')
    assert 'authenticated stdio proxy' not in resources
    assert 'open cooperative stdio' not in resources
    assets = package / 'adapters/inbound/http/static'
    html = (assets / 'index.html').read_text(encoding='utf-8')
    import re
    scripts = re.findall(r'src="/assets/([^"]+\.js)"', html)
    assert scripts
    shipped = '\n'.join((assets / 'assets' / name).read_text(encoding='utf-8') for name in scripts)
    assert 'stdio MCP server (V1 mode)' not in shipped
    assert 'command reference; MCP uses HTTP /mcp' in shipped
    guide = (root / 'docs/harness-integrations/r4-operations.md').read_text(encoding='utf-8')
    for required in ('G0–G3', 'remote_execution_ready', 'possible_effect=true',
                     'retry_safe=false', 'does not require the Connector',
                     'catalog entry is not proof'):
        assert required in guide


@pytest.mark.parametrize("scenario", ["configuration", "restore"])
def test_ns15_04(tmp_path, monkeypatch, request, qualified_contract, scenario):
    """TR4-15-04: failure-safe config apply and joint post-effect restore."""
    from ns15_restore_cases import configuration_case, restore_case
    {"configuration": configuration_case, "restore": restore_case}[scenario](tmp_path, monkeypatch, request)


@pytest.mark.parametrize("surface", ["rest", "mcp"])
def test_ns15_03(connected_local, qualified_contract, monkeypatch, surface):
    """TR4-15-03: physical adapters only in Core; public callers survive removal."""
    import ast
    import okto_nexus
    from okto_nexus.bootstrap import execution_compat
    import test_harness_canonical as callers
    from test_native_loader_cutover import test_clean_server_composition_does_not_import_legacy_native_loaders

    test_clean_server_composition_does_not_import_legacy_native_loaders()
    package = Path(okto_nexus.__file__).resolve().parent
    native = package / "adapters/outbound/harness"
    files = list(package.rglob("*.py"))
    assert files and native.is_dir()
    forbidden = {"subprocess", "socket", "ctypes"}
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imports = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                       else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            for name in imports:
                assert name.split(".")[0] not in {"legacy_native_fixture", "okto_nexus_connector"}, (path, name)
                if native in path.parents:
                    assert name.split(".")[0] not in forbidden, (path, name)
    # Existing scoped public-caller contracts exercise the same Core dispatch,
    # durable history and idempotency after the physical code has been removed.
    info = execution_compat.protocol_info()
    monkeypatch.setattr(execution_compat, "protocol_info", lambda: {**info, "remote_execution_ready": True})
    if surface == "rest":
        callers.test_existing_rest_commands_use_core_once(connected_local, monkeypatch)
    else:
        callers.test_mcp_uses_same_admission_and_history(connected_local, monkeypatch)


def test_ns15_01(tmp_path, monkeypatch, request):
    original_app = local.app_for
    backup = tmp_path / "migration-backup"
    preserved = {}
    history_tables = ("tasks", "handoffs", "messages", "message_deliveries",
                      "harness_sessions", "harness_events")

    def migrate(db, size=1):
        output = io.StringIO()
        code = run_admin(["migrate-execution", "--db-path", str(db), "--backup", str(backup),
                          "--batch-size", str(size)], out=output)
        return code, json.loads(output.getvalue()) if output.getvalue() else None

    def seeded(home):
        old = tmp_path / "schema65"
        old.mkdir()
        for path in _default_migrations_dir().glob("*.sql"):
            if int(path.name.split("_", 1)[0]) <= 65:
                shutil.copy2(path, old / path.name)
        config = NexusConfig(home_dir=home)
        factory = ConnectionFactory(config)
        MigrationRunner(factory, old).apply()
        workspace = resolve_workspace_id(str(tmp_path / "workspace"))
        keys = {actor: generate_api_key() for actor in ("operator", "subject")}
        with factory.unit_of_work() as uow:
            c = uow.connection
            for actor, key in keys.items():
                c.execute("INSERT INTO agents(agent_id,role,api_key_hash,created_at) VALUES(?,?,?,'2026-10-01')",
                          (actor, "operator" if actor == "operator" else None, hash_api_key(key)))
            c.execute("INSERT INTO workspaces(workspace_id,root_realpath,created_at) VALUES(?,?,'2026-10-01')",
                      (workspace, str((tmp_path / "workspace").resolve())))
            for profile, endpoint, adapter in (("legacy-profile", "legacy-endpoint", "codex"),
                                               ("pi-profile", "pi-endpoint", "pi")):
                c.execute("INSERT INTO runtime_profiles(profile_id,adapter_id,config,created_at,updated_at) "
                          "VALUES(?,?,?,'2026-10-01','2026-10-01')",
                          (profile, adapter, '{"command":"historical command must never execute"}'))
                c.execute("INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,adapter_id,protocol,"
                          "profile_id,enabled,activation_state,created_at,updated_at) "
                          "VALUES(?,'subject',?,?,'legacy',?,0,'denied','2026-10-01','2026-10-01')",
                          (endpoint, workspace, adapter, profile))
            c.execute("INSERT INTO agent_connection_methods VALUES('subject','pi',0)")
            c.execute("INSERT INTO tasks(task_id,workspace_id,title,status,created_at) "
                      "VALUES('job',?,'Historical job','completed','2026-10-01')", (workspace,))
            c.execute("INSERT INTO handoffs(handoff_id,workspace_id,task_id,status,claimed_by,claim_epoch,created_at) "
                      "VALUES('handoff',?,'job','completed','subject',3,'2026-10-01')", (workspace,))
            c.execute("INSERT INTO messages(message_id,workspace_id,from_agent_id,body,created_at) "
                      "VALUES('result',?,'subject','Historical result','2026-10-01')", (workspace,))
            c.execute("INSERT INTO message_deliveries(delivery_id,message_id,recipient_agent_id,status,created_at) "
                      "VALUES('delivery','result','subject','read','2026-10-01')")
            c.execute("INSERT INTO harness_sessions(session_id,kind,owning_agent_id,status,capabilities,started_at,"
                      "ended_at,created_at,updated_at,endpoint_id) VALUES('old-session','codex','subject','ended',"
                      "'{}','2026-09-30','2026-10-01','2026-09-30','2026-10-01','legacy-endpoint')")
            c.execute("INSERT INTO harness_events(event_id,session_id,harness_kind,kind,native_event,occurred_at,"
                      "sequence,created_at) VALUES('old-result','old-session','codex','turn_completed',"
                      "'{\"legacy_hash\":\"unchanged\"}','2026-10-01',1,'2026-10-01')")
            for table in history_tables:
                preserved[table] = [dict(r) for r in c.execute("SELECT * FROM " + table)]
            preserved["keys"] = {r[0]: r[1] for r in c.execute("SELECT agent_id,api_key_hash FROM agents")}
        create_migration_backup(config.db_path, backup)
        assert json.loads((backup / "manifest.json").read_text())["inventory"]["tables"]["tasks"]["rows"] == 1
        # First CLI batch expands the old schema and commits one denial.
        assert migrate(config.db_path)[1]["processed"] == 1
        with factory.unit_of_work() as uow:
            uow.connection.execute("CREATE TRIGGER interrupt_catalog BEFORE INSERT ON execution_migration_map "
                "WHEN NEW.legacy_id='pi-profile' BEGIN SELECT RAISE(ABORT,'interrupted backfill'); END")
        assert migrate(config.db_path, 100)[0] == 1
        with factory.unit_of_work() as uow:
            assert uow.connection.execute("SELECT COUNT(*) FROM execution_migration_map").fetchone()[0] == 1
            uow.connection.execute("DROP TRIGGER interrupt_catalog")
        for _ in range(4):
            assert migrate(config.db_path)[0] == 0
        for _ in range(2):
            code, report = migrate(config.db_path)
            assert code == 0 and report["status"] == "CATALOG_BACKFILL_COMPLETE"
            assert report["processed"] == 0 and report["execution_activated"] is False
        deps, app = original_app(home)
        app.state.test_existing_keys = keys
        app.state.test_legacy_workspace = workspace
        return deps, app

    class ForbiddenProcess(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            raise AssertionError("Migration must not open a provider process.")

    monkeypatch.setattr("subprocess.Popen", ForbiddenProcess)
    monkeypatch.setattr(local, "app_for", seeded)
    fixture = local.local_setup.__wrapped__(tmp_path, monkeypatch, request)
    setup = next(fixture)
    deps, _, client, headers, *_ = setup
    try:
        _, apply = prepare_operator(client, headers, proposal_request(setup))
        response = client.post("/v1/connections/bindings:apply", json=apply, headers=headers["operator"])
        assert response.status_code == 200, response.text
    finally:
        with pytest.raises(StopIteration):
            next(fixture)
    for _ in range(2):
        code, report = migrate(deps.config.db_path)
        assert code == 0 and report["processed"] == 0
    with deps.connection_factory.unit_of_work(write=False) as uow:
        c = uow.connection
        for table in history_tables:
            rows = [dict(r) for r in c.execute("SELECT * FROM " + table)]
            assert rows == preserved[table], table
        assert {r[0]: r[1] for r in c.execute("SELECT agent_id,api_key_hash FROM agents")} == preserved["keys"]
        assert c.execute("SELECT COUNT(*) FROM agent_endpoints WHERE enabled=0 AND activation_state='denied'").fetchone()[0] == 2
        assert c.execute("SELECT COUNT(*) FROM agent_connection_methods WHERE method IN ('pi','pi_rpc') AND enabled=0").fetchone()[0] == 2
        assert c.execute("SELECT COUNT(*) FROM execution_bindings").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM execution_sessions").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM execution_migration_map").fetchone()[0] == 5
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []


def test_ns15_02(tmp_path, monkeypatch, request, capsys):
    # Reuse the actual TCP/lifespan legacy owner fixture, not a second owner.
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import runtime, open_rest
    from okto_nexus.application.execution_binding_migration import migration_target
    from okto_nexus.bootstrap.execution_migration import migrate_execution_catalog
    from okto_nexus.adapters.inbound.cli.main import main
    from okto_nexus.errors import OktoNexusError
    from okto_nexus.bootstrap.dependencies import bootstrap
    from okto_nexus.adapters.inbound.http.app import build_app
    from fastapi.testclient import TestClient
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "tools"))
    import offline_runtime_backup as recovery

    with contextmanager(runtime.__wrapped__)(tmp_path, request) as running:
        deps, client, root, peers, operator_key, caller_key = running
        headers = {"x-api-key": operator_key}
        active = open_rest(running)
        assert active.status_code == 200, active.text
        uncertain = client.post("/api/v1/harness/sessions", headers=headers,
            json={"agent_id": "worker", "kind": "codex", "project_root": root})
        assert uncertain.status_code == 200, uncertain.text
        assert len(peers) == 2
        stopped_peer, unknown_peer = peers
        monkeypatch.setattr(stopped_peer, "observe_lifecycle",
                            lambda session: {"stop_observed": True, "active_turn": False}, raising=False)
        monkeypatch.setattr(unknown_peer, "observe_lifecycle",
                            lambda session: {"stop_observed": True, "active_turn": True}, raising=False)
        response = client.post("/v1/runtime/shutdown", headers={"Authorization": "Bearer " + operator_key},
                               json={"timeout_seconds": 5})
        assert response.status_code in (200, 202), response.text
        assert response.json()["state"] == "DRAINED", response.text
        assert deps.runtime_admission_fence.closed
        assert deps.runtime_dispatcher._shutdown_finished.is_set()
        assert all(peer.close_called for peer in peers)
        assert all(sum(command.verb == "end" for command in peer.sent) == 1 for peer in peers)
        assert open_rest(running).status_code >= 400
        assert len(peers) == 2
        for peer in peers:
            queried = client.get("/api/v1/harness/sessions/" + peer.session.session_id, headers=headers)
            assert queried.status_code == 200, queried.text
        with deps.connection_factory.unit_of_work(write=False) as uow:
            rows = {r["session_id"]: dict(r) for r in uow.connection.execute("SELECT * FROM harness_sessions")}
        stopped = rows[stopped_peer.session.session_id]
        unknown = rows[unknown_peer.session.session_id]
        assert stopped["status"] == "ENDED" and stopped["lifecycle_state"] == "stopped"
        assert stopped["ended_at"] is not None
        assert unknown["lifecycle_state"] == "outcome_unknown" and unknown["ended_at"] is None
        backup = tmp_path / "cutover-backup"
        create_migration_backup(deps.config.db_path, backup)
        assert migrate_execution_catalog(deps.config.db_path, backup)["status"] == "CATALOG_BACKFILL_COMPLETE"
        with deps.connection_factory.unit_of_work(write=False) as uow:
            c = uow.connection
            installation = c.execute("SELECT * FROM execution_installation").fetchone()
            executor = c.execute("SELECT executor_id FROM execution_executors WHERE kind='embedded'").fetchone()[0]
            scope = dict(server_id=installation["server_id"], executor_id=executor,
                         subject_agent_id="worker", workspace_id=resolve_workspace_id(root))
            assert migration_target(c, **scope, adapter_id="pi_rpc", endpoint_id="endpoint-pi")["endpoint_id"] == "endpoint-pi"
            with pytest.raises(OktoNexusError, match="Drain or reconcile"):
                migration_target(c, **scope, adapter_id="codex_app_server", endpoint_id="endpoint-codex")
            assert {r["session_id"]: dict(r) for r in c.execute("SELECT * FROM harness_sessions")} == rows
            assert c.execute("SELECT COUNT(*) FROM execution_sessions").fetchone()[0] == 0
        # Physical stops are observed for both peers; the second turn result
        # remains uncertain. Restore must preserve that uncertainty, not replay it.
        snapshot = tmp_path / "combined-cutover-snapshot"
        recovery.backup(deps.config.home_dir, snapshot, stopped=True)
        with pytest.raises(ValueError, match="Confirm"):
            recovery.restore(snapshot, tmp_path / "unsafe-restore")
        assert not (tmp_path / "unsafe-restore").exists()
    restored_home = recovery.restore(snapshot, tmp_path / "restored-cutover", stopped=True)
    restored = bootstrap({}, ["--home", str(restored_home), "--feature-harness-integrations", "false"])
    launches = []

    def forbidden(**kwargs):
        launches.append(kwargs)
        raise AssertionError("Restoring cutover history must not launch a replacement")

    restored.harness_connector_factories = {kind: forbidden for kind in ("pi", "codex", "claude_code")}
    with TestClient(build_app(restored)) as client:
        for peer in peers:
            response = client.get("/api/v1/harness/sessions/" + peer.session.session_id, headers=headers)
            assert response.status_code == 200, response.text
            denied = client.get("/api/v1/harness/sessions/" + peer.session.session_id,
                                headers={"x-api-key": caller_key})
            assert denied.status_code == 403
        refused = client.post("/api/v1/harness/sessions", headers=headers,
                              json={"agent_id": "worker", "kind": "pi", "project_root": root})
        assert refused.status_code == 403, refused.text
        with restored.connection_factory.unit_of_work(write=False) as uow:
            assert {r["session_id"]: dict(r) for r in uow.connection.execute("SELECT * FROM harness_sessions")} == rows
            with pytest.raises(OktoNexusError, match="Drain or reconcile"):
                migration_target(uow.connection, **scope, adapter_id="codex_app_server", endpoint_id="endpoint-codex")
        assert not launches
        assert main([]) == 0
        assert main(["stdio"]) == 2
        assert "MCP stdio is no longer available" in capsys.readouterr().err
