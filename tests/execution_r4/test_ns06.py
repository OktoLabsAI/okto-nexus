"""R4 resolve is a recoverable intent, not an operation admission."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.outbound.sqlite.execution_identity import (
    ensure_execution_installation,
)
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.application.execution_admission import submit_execution_operation
from okto_nexus.application.execution_dispatch import (
    begin_execution_send, release_unsent_dispatch,
    reserve_execution_dispatch,
)
from okto_nexus.application.execution_intents import (
    read_execution_intent, resolve_execution_intent,
)

# Fixtures are requested only by the domain-integration acceptance below.
from test_local_realization import local_setup
from test_canonical_delivery import connected_local
from test_combined_consumption import combined_onboarding


@pytest.mark.parametrize('scenario', ['local', 'remote', 'observer', 'handoff', 'claim_race'])
def test_ns06_05(request, tmp_path, monkeypatch, scenario):
    """TR4-06-05: one logical consumer; observer/terminal cannot execute work."""
    from okto_nexus.bootstrap import embedded_dispatch, execution_compat
    from okto_nexus.adapters.inbound.http import runtime_v1
    for module in (embedded_dispatch, execution_compat, runtime_v1):
        info = module.protocol_info()
        monkeypatch.setattr(module, 'protocol_info', lambda info=info: {**info, 'remote_execution_ready': True})
    if scenario == 'remote':
        from test_combined_consumption import test_remote_delivery_and_claim_survive_forbidden_local_preparation
        test_remote_delivery_and_claim_survive_forbidden_local_preparation(
            request.getfixturevalue('combined_onboarding'), tmp_path, monkeypatch)
    elif scenario == 'local':
        from test_canonical_consumption import test_canonical_push_reservation_excludes_mcp_pull
        test_canonical_push_reservation_excludes_mcp_pull(
            request.getfixturevalue('connected_local'), monkeypatch, 'accepted')
    else:
        connected = request.getfixturevalue('connected_local')
        if scenario == 'observer':
            from test_canonical_delivery import test_canonical_observer_does_not_receive_executable_prompt
            test_canonical_observer_does_not_receive_executable_prompt(connected, monkeypatch)
        elif scenario == 'handoff':
            from test_canonical_handoff import test_managed_claim_replays_and_native_terminal_does_not_complete
            test_managed_claim_replays_and_native_terminal_does_not_complete(connected, monkeypatch)
        else:
            from test_canonical_consumption import test_handoff_pull_and_runtime_compete_for_one_claim
            test_handoff_pull_and_runtime_compete_for_one_claim(connected, monkeypatch, 'concurrent')


def test_ns06_01(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    app = build_app(deps)
    installation = ensure_execution_installation(deps.connection_factory)
    candidate_ref = "nexus-install-v1:" + "a" * 64
    inventory_revision = "sha256:" + "b" * 64
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        now = "2026-09-29T00:00:00Z"
        for agent_id in ("agent-a", "agent-b"):
            conn.execute("INSERT INTO agents(agent_id,created_at) VALUES (?,?)",
                         (agent_id, now))
        conn.execute("INSERT INTO agent_execution_policies VALUES(?,?,?,?)",
                     ("agent-a", "remote", None, 1))
        conn.execute("INSERT INTO workspaces(workspace_id,created_at) "
                     "VALUES ('ws',?)", (now,))
        conn.execute(
            "INSERT INTO execution_executors(server_id,executor_id,connector_id,"
            "registered_by_agent_id,kind,control_state,generation) "
            "VALUES (?,?,'connector','agent-a','remote','DISCONNECTED',1)",
            (installation.server_id, "exe_remote"),
        )
        conn.execute(
            "INSERT INTO execution_workspace_bindings(server_id,workspace_binding_id,"
            "executor_id,workspace_id,realization_handle,revision,status) "
            "VALUES (?,'wxb','exe_remote','ws','root_1234567890123456',2,'READY')",
            (installation.server_id,),
        )
        conn.execute(
            "INSERT INTO execution_realizations(server_id,executor_id,"
            "realization_ref,local_realization_ref,subject_agent_id,"
            "workspace_binding_id,candidate_ref,inventory_revision,"
            "configuration_digest,local_root_proof_digest,revision,status) "
            "VALUES (?,'exe_remote','real','root_1234567890123456',"
            "'agent-a','wxb',?,?,?, ?,1,'READY')",
            (installation.server_id, candidate_ref, inventory_revision,
             "sha256:" + "c" * 64, "sha256:" + "d" * 64),
        )
        conn.execute(
            "INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,"
            "adapter_id,protocol,enabled,created_at,updated_at) "
            "VALUES ('ep','agent-a','ws','codex_app_server','nxl-r4',0,?,?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO execution_bindings(server_id,binding_id,executor_id,"
            "endpoint_id,workspace_binding_id,candidate_ref,inventory_revision,"
            "realization_ref,realization_revision,binding_revision) "
            "VALUES (?,'binding','exe_remote','ep','wxb',?,?, 'real',1,1)",
            (installation.server_id, candidate_ref, inventory_revision),
        )
    with deps.connection_factory.unit_of_work() as uow:
        key_a = app.state.auth.issue_key(uow, agent_id="agent-a")
        key_b = app.state.auth.issue_key(uow, agent_id="agent-b")
    body = {
        "client_intent_id": "start-one", "intent": "runtime.start",
        "binding_id": "binding", "workspace_binding_id": "wxb",
        "new_session": True,
    }
    with TestClient(app, raise_server_exceptions=False) as client:
        route = "/v1/runtime/intents:resolve"
        created = client.post(route, json=body, headers={
            "Authorization": f"Bearer {key_a}"})
        assert created.status_code == 200, created.text
        resolution = created.json()
        contract = json.loads((Path(__file__).resolve().parents[2] /
                               "plans/contratos/http-target.schema.json").read_text(
                                   encoding="utf-8"))
        Draft202012Validator({"$defs": contract["$defs"],
                              **contract["$defs"]["IntentResolution"]}).validate(
                                  resolution)
        assert resolution["scope"]["binding_id"] == "binding"
        assert resolution["semantic_intent"]["action"] == "runtime.open"
        assert resolution["can_submit"] is False
        assert "executor_not_ready" in resolution["blockers"]
        assert "remote_execution_unavailable" not in resolution["blockers"]
        refused = client.post("/v1/runtime/operations", json={
            "client_intent_id": body["client_intent_id"],
            "operation_id": resolution["operation_id"],
            "resolution_revision": resolution["resolution_revision"],
            "intent_hash": resolution["intent_hash"],
        }, headers={"Authorization": f"Bearer {key_a}"})
        assert refused.status_code == 409, refused.text
        assert client.post(route, json=body, headers={
            "Authorization": f"Bearer {key_a}"}).json() == resolution
        assert client.post(route, json={**body, "binding_id": "different"},
                           headers={"Authorization": f"Bearer {key_a}"}).status_code == 409
        queried = client.get("/v1/runtime/intents/start-one", headers={
            "Authorization": f"Bearer {key_a}"})
        assert queried.status_code == 200
        assert queried.json() == {"resolution": resolution, "operation": None}
        assert client.get("/v1/runtime/intents/start-one", headers={
            "Authorization": f"Bearer {key_b}"}).status_code == 404
    with deps.connection_factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        assert conn.execute("SELECT COUNT(*) FROM execution_client_intents "
                            "WHERE client_intent_id='start-one'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM execution_dispatch_outbox").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM execution_sessions").fetchone()[0] == 0


def test_ns06_02_atomic_admission_and_replay_with_synthetic_qualification(tmp_path):
    """The real protocol gate stays closed; this tests the isolated T2 writer."""
    deps = bootstrap({}, ["--home", str(tmp_path / "home"), "--feature-harness-integrations", "true"])
    factory = deps.connection_factory
    server_id = ensure_execution_installation(factory).server_id
    now = "2026-09-29T00:00:00Z"
    from nexus_connector_core import InstallationCandidate, build_executor_inventory_snapshot
    snapshot = build_executor_inventory_snapshot([
        InstallationCandidate("codex_app_server", str(tmp_path / "codex"),
                              "sha256:" + "a" * 64, "explicit", "selected")],
        server_id=server_id, executor_id="executor",
        producer_instance_id="fixture", publication_sequence=1)
    candidate = snapshot["evidence"][0]["candidate_ref"]
    inventory = snapshot["inventory_revision"]
    with factory.unit_of_work() as uow:
        conn = uow.connection
        conn.execute("INSERT INTO agents(agent_id,api_key_hash,created_at) VALUES ('agent-a','fixture-agent-key-hash',?)",
                     (now,))
        conn.execute("INSERT INTO agent_execution_policies VALUES(?,?,?,?)",
                     ("agent-a", "remote", None, 1))
        conn.execute("INSERT INTO workspaces(workspace_id,created_at) "
                     "VALUES ('ws',?)", (now,))
        conn.execute(
            "INSERT INTO runtime_profiles(profile_id,adapter_id,config,enabled,"
            "revision,created_at,updated_at) "
            "VALUES ('profile','codex_app_server','{}',1,3,?,?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO execution_executors(server_id,executor_id,connector_id,"
            "registered_by_agent_id,kind,control_state,generation) "
            "VALUES (?,'executor','connector','agent-a','remote','CONTROL_READY',1)",
            (server_id,),
        )
        conn.execute(
            "INSERT INTO execution_workspace_bindings(server_id,workspace_binding_id,"
            "executor_id,workspace_id,realization_handle,revision,status) "
            "VALUES (?,'wxb','executor','ws','local-root',1,'READY')",
            (server_id,),
        )
        conn.execute(
            "INSERT INTO execution_realizations(server_id,executor_id,"
            "realization_ref,local_realization_ref,subject_agent_id,"
            "workspace_binding_id,candidate_ref,inventory_revision,"
            "configuration_digest,local_root_proof_digest,revision,status) "
            "VALUES (?,'executor','real','local-root','agent-a','wxb',"
            "?,?,'sha256:1','sha256:2',1,'READY')",
            (server_id, candidate, inventory),
        )
        conn.execute(
            "INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,"
            "adapter_id,protocol,profile_id,enabled,activation_state,created_at,updated_at) "
            "VALUES ('ep','agent-a','ws','codex_app_server','nxl-r4',"
            "'profile',1,'approved',?,?)", (now, now),
        )
        conn.execute(
            "INSERT INTO execution_bindings(server_id,binding_id,executor_id,"
            "endpoint_id,workspace_binding_id,candidate_ref,inventory_revision,"
            "realization_ref,realization_revision,binding_revision) "
            "VALUES (?,'binding','executor','ep','wxb',?,?,'real',1,1)",
            (server_id, candidate, inventory),
        )
        conn.execute(
            "INSERT INTO execution_inventory_snapshots(server_id,executor_id,"
            "publication_sequence,inventory_revision,catalog_format,"
            "availability_format,snapshot_format,core_version,canonical_projection,"
            "received_at,observation_age_ms,producer_instance_id) "
            "VALUES (?,'executor',1,?,?,?,?,?,?,?,0,'fixture')",
            (server_id, inventory, snapshot["catalog"]["format_version"],
             snapshot["availability"]["format_version"], snapshot["snapshot_format_version"],
             snapshot["core_version"], json.dumps(snapshot), now),
        )
        conn.execute(
            "INSERT INTO execution_inventory_current(server_id,executor_id,"
            "publication_sequence,inventory_revision) "
            "VALUES (?,'executor',1,?)", (server_id, inventory),
        )
    from okto_nexus.bootstrap.execution_authority import build_execution_access
    from okto_nexus.domain.runtime_context import RuntimeRequestContext
    from okto_nexus.domain.base import iso_plus
    access = build_execution_access(deps)
    canonical_grant = access.issue(
        RuntimeRequestContext('operator', 'http_loopback', trusted_local_operator=True),
        actor_agent_id='agent-a', endpoint_id='ep', actions=['open'],
        expires_at=iso_plus(deps.clock.now_iso(), 3600))
    freshness = {(server_id, "executor"): (1, time.monotonic(), 0)}
    resolution = resolve_execution_intent(
        factory, actor_agent_id="agent-a", request={
            "client_intent_id": "start", "intent": "runtime.start",
            "binding_id": "binding", "workspace_binding_id": "wxb",
            "new_session": True,
        }, remote_ready=True, fresh_publications=freshness)
    assert resolution["blockers"] == []
    assert resolution["can_submit"] is True
    assert resolution["semantic_intent"]["payload"]["profile_revision"] == 3
    # Only this private fixture is qualified. The HTTP protocol still refuses
    # product admission until the Core bundle and remote host are ready.
    request = {key: resolution[key] for key in (
        "client_intent_id", "operation_id", "resolution_revision", "intent_hash")}
    # A retained projection cannot become executable after a Core upgrade,
    # even when publication freshness and the binding revision still match.
    from okto_nexus.errors import OktoNexusError
    historical = {**snapshot, "snapshot_format_version": 1}
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "UPDATE execution_inventory_snapshots SET canonical_projection=?",
            (json.dumps(historical),))
    outdated = resolve_execution_intent(
        factory, actor_agent_id="agent-a", request={
            "client_intent_id": "outdated-inventory", "intent": "runtime.start",
            "binding_id": "binding", "workspace_binding_id": "wxb",
            "new_session": True,
        }, remote_ready=True, fresh_publications=freshness)
    assert not outdated["can_submit"]
    assert "inventory_incompatible" in outdated["blockers"]
    with pytest.raises(OktoNexusError, match="Refresh the executor inventory"):
        submit_execution_operation(
            factory, actor_agent_id="agent-a", request=request,
            fresh_publications=freshness, remote_ready=True)
    with factory.unit_of_work() as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 0
        uow.connection.execute(
            "UPDATE execution_inventory_snapshots SET canonical_projection=?",
            (json.dumps(snapshot),))
    # Interrupt the same transaction at its final write.
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "CREATE TRIGGER fail_r4_outbox_persistent BEFORE INSERT ON "
            "execution_dispatch_outbox BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
        )
    try:
        with pytest.raises(Exception, match="synthetic failure"):
            submit_execution_operation(
                factory, actor_agent_id="agent-a", request=request,
                fresh_publications=freshness, remote_ready=True)
    finally:
        with factory.unit_of_work() as uow:
            uow.connection.execute("DROP TRIGGER fail_r4_outbox_persistent")
    with factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        assert conn.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM execution_sessions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM execution_dispatch_outbox").fetchone()[0] == 0
    first, reused = submit_execution_operation(
        factory, actor_agent_id="agent-a", request=request,
        fresh_publications=freshness, remote_ready=True)
    second, replay = submit_execution_operation(
        factory, actor_agent_id="agent-a", request=request,
        fresh_publications={}, remote_ready=False)
    assert not reused and replay and first == second
    assert first["admission_state"] == "ACCEPTED"
    assert first["receipt_revision"] == 0
    assert read_execution_intent(
        factory, actor_agent_id="agent-a", client_intent_id="start"
    )["operation"] == first
    next_resolution = resolve_execution_intent(
        factory, actor_agent_id="agent-a", request={
            "client_intent_id": "start-two", "intent": "runtime.start",
            "binding_id": "binding", "workspace_binding_id": "wxb",
            "new_session": True,
        }, remote_ready=True, fresh_publications=freshness)
    next_request = {key: next_resolution[key] for key in (
        "client_intent_id", "operation_id", "resolution_revision", "intent_hash")}
    from okto_nexus.errors import OktoNexusError
    with pytest.raises(OktoNexusError):
        submit_execution_operation(
            factory, actor_agent_id="agent-a", request=next_request,
            fresh_publications={}, remote_ready=True)
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "UPDATE agents SET metadata=? WHERE agent_id='agent-a'",
            ('{"display_name":"Changed after resolve"}',),
        )
    with pytest.raises(OktoNexusError):
        submit_execution_operation(
            factory, actor_agent_id="agent-a", request=next_request,
            fresh_publications=freshness, remote_ready=True)
    with factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        assert conn.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM execution_sessions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM execution_dispatch_outbox").fetchone()[0] == 1
    with factory.unit_of_work() as uow:
        conn = uow.connection
        for operation_id, action in (("regular-two", "turn.submit"),
                                     ("control-one", "turn.interrupt")):
            conn.execute(
                "INSERT INTO execution_operations(server_id,executor_id,"
                "operation_id,subject_agent_id,actor_agent_id,binding_id,"
                "workspace_id,workspace_binding_id,session_id,action,intent_hash,"
                "semantic_payload,expected_revisions_json,admission_state,created_at) "
                "SELECT server_id,executor_id,?,subject_agent_id,actor_agent_id,"
                "binding_id,workspace_id,workspace_binding_id,session_id,?,"
                "intent_hash,semantic_payload,expected_revisions_json,"
                "admission_state,created_at FROM execution_operations "
                "WHERE operation_id=?",
                (operation_id, action, request["operation_id"]),
            )
            conn.execute(
                "INSERT INTO execution_dispatch_outbox(server_id,executor_id,"
                "operation_id,dispatch_state) VALUES (?,'executor',?,'PENDING')",
                (server_id, operation_id),
            )
    assert reserve_execution_dispatch(
        factory, server_id=server_id, executor_id="executor",
        remote_ready=False) is None
    first_reservation = reserve_execution_dispatch(
        factory, server_id=server_id, executor_id="executor",
        remote_ready=True, regular_items=1)
    assert first_reservation.operation_id == "control-one"
    assert first_reservation.reservation_class == "control"
    second_reservation = reserve_execution_dispatch(
        factory, server_id=server_id, executor_id="executor",
        remote_ready=True, regular_items=1)
    assert second_reservation.reservation_class == "regular"
    assert second_reservation.operation_id == request["operation_id"]
    with pytest.raises(OktoNexusError):
        begin_execution_send(
            factory, reservation=second_reservation, remote_ready=True,
            fresh_publications=freshness, access=access)
    with factory.unit_of_work(write=False) as uow:
        state = uow.connection.execute(
            "SELECT dispatch_state FROM execution_dispatch_outbox "
            "WHERE operation_id=?", (second_reservation.operation_id,),
        ).fetchone()[0]
        assert state == "RESERVED"
    assert reserve_execution_dispatch(
        factory, server_id=server_id, executor_id="executor",
        remote_ready=True, regular_items=1) is None
    release_unsent_dispatch(factory, reservation=first_reservation)
    with pytest.raises(OktoNexusError):
        release_unsent_dispatch(factory, reservation=first_reservation)
    with factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute(
            "SELECT reserved_bytes,attempt_token FROM execution_dispatch_outbox "
            "WHERE operation_id='control-one'").fetchone()
        assert tuple(row) == (0, None)
    release_unsent_dispatch(factory, reservation=second_reservation)
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "UPDATE execution_dispatch_outbox SET dispatch_state='FIXTURE_DONE' "
            "WHERE operation_id IN (?,?,?)",
            (first_reservation.operation_id,
             second_reservation.operation_id, "regular-two"),
        )
    ready_resolution = resolve_execution_intent(
        factory, actor_agent_id="agent-a", request={
            "client_intent_id": "start-three", "intent": "runtime.start",
            "binding_id": "binding", "workspace_binding_id": "wxb",
            "new_session": True,
        }, remote_ready=True, fresh_publications=freshness)
    ready_request = {key: ready_resolution[key] for key in (
        "client_intent_id", "operation_id", "resolution_revision", "intent_hash")}
    submit_execution_operation(
        factory, actor_agent_id="agent-a", request=ready_request,
        fresh_publications=freshness, remote_ready=True)
    scope = ready_resolution["scope"]
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "UPDATE execution_executors SET owner_instance_id='fixture-channel' "
            "WHERE server_id=? AND executor_id='executor'", (server_id,))
        uow.connection.execute(
            "INSERT INTO execution_leases(server_id,executor_id,session_id,"
            "lease_serial,lease_id,grant_id,allowed_actions_json,"
            "authorization_revision,configuration_revision,owner_generation,"
            "connection_generation,credential_epoch,valid_until_server,"
            "request_id,status) VALUES (?,'executor',?,1,'lease',?,"
            "'[\"runtime.open\"]',?,?,?,?,?,?,'lease-request','ACTIVE')",
            (server_id, scope["session_id"], canonical_grant['grant_id'],
             scope["authorization_revision"], scope["configuration_revision"],
             scope["session_owner_generation"], 1, scope["credential_epoch"],
             (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()),
        )
    ready_reservation = reserve_execution_dispatch(
        factory, server_id=server_id, executor_id="executor",
        remote_ready=True, regular_items=1)
    assert ready_reservation.operation_id == ready_request["operation_id"]
    # A historical ACTIVE row has no proof that Core installed its grant.
    with pytest.raises(OktoNexusError, match="applied dispatch lease"):
        begin_execution_send(factory, reservation=ready_reservation,
                             remote_ready=True, fresh_publications=freshness, access=access)
    from okto_nexus.adapters.outbound.sqlite.execution_tickets import issue_execution_ticket
    fixture_ticket = issue_execution_ticket(factory, server_id=server_id, executor_id='executor',
        agent_id='agent-a', binding_id='binding', scopes=frozenset({'lane:attach', 'lease:request'}))
    with factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_link_tickets SET bound_connection_id='fixture-channel' WHERE ticket_id=?",
                               (fixture_ticket.ticket_id,))
        uow.connection.execute(
            "INSERT INTO execution_control_lanes(server_id,executor_id,binding_id,agent_id,ticket_id,"
            "attach_request_id,connection_id,connection_generation,credential_epoch,authorization_revision,"
            "configuration_revision,expires_at,state) VALUES (?,'executor','binding','agent-a',?,"
            "'fixture-attach','fixture-channel',1,?,?,?,?,'ADMITTED')",
            (server_id, fixture_ticket.ticket_id, scope['credential_epoch'], scope['authorization_revision'],
             scope['configuration_revision'], iso_plus(deps.clock.now_iso(), 300)))
        uow.connection.execute(
            "UPDATE execution_leases SET scope_json=?,applied_at=?,connection_id='fixture-channel' "
            "WHERE server_id=? AND executor_id='executor' AND session_id=?",
            (json.dumps(scope), datetime.now(timezone.utc).isoformat(), server_id, scope['session_id']))
    authorized = begin_execution_send(
        factory, reservation=ready_reservation, remote_ready=True,
        fresh_publications=freshness, access=access)
    assert authorized.lease_id == "lease"
    assert authorized.semantic_intent["action"] == "runtime.open"
    with pytest.raises(OktoNexusError):
        release_unsent_dispatch(factory, reservation=ready_reservation)
