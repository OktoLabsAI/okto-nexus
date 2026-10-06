"""Public operator onboarding with synthetic inventory and no seeded binding."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from nexus_connector_core import InstallationCandidate
from nexus_connector_core.discovery import fingerprint
import pytest

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.outbound.execution.core_inventory import local_inventory_snapshot
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.domain.base import iso_plus
from okto_nexus.errors import OktoNexusError


@pytest.fixture
def onboarding(tmp_path, request):
    deps = bootstrap({}, ["--home", str(tmp_path / "home"),
                          "--feature-harness-integrations", "true"])
    app = build_app(deps)
    headers = {}
    with deps.connection_factory.unit_of_work() as uow:
        for agent in ("subject", "other", "operator"):
            uow.connection.execute(
                "INSERT OR IGNORE INTO agents(agent_id,created_at) VALUES (?,?)",
                (agent, deps.clock.now_iso()))
            key = app.state.auth.issue_key(uow, agent_id=agent)
            headers[agent] = {"Authorization": "Bearer " + key}
            uow.connection.execute('INSERT INTO agent_execution_policies VALUES(?,?,?,?)',
                                   (agent, 'remote', None, 1))
    with TestClient(app, raise_server_exceptions=False,
                    client=('127.0.0.1' if getattr(request, 'param', None) == 'human-operator' else 'testclient', 50000)) as client:
        response = client.post("/v1/connections/executors:register", json={
            "client_intent_id": "register", "connector_id": "connector",
            "label": "Remote host", "control_capabilities": [],
        }, headers=headers["subject"])
        assert response.status_code == 201, response.text
        registration = response.json()
        executor = registration["executor_id"]
        ticket = {"Authorization": "Bearer " + registration["bootstrap_ticket"]["ticket"]}
        binary = tmp_path / "remote-only" / "codex.exe"
        binary.parent.mkdir()
        binary.write_bytes(b"Synthetic selected native peer")
        candidate = InstallationCandidate(
            "codex_app_server", str(binary),
            fingerprint(binary), "explicit", "selected")
        candidates = [candidate]
        if getattr(request, 'param', None) == 'duplicate-installations':
            second = binary.parent / 'second-copy' / 'codex.exe'
            second.parent.mkdir()
            second.write_bytes(binary.read_bytes())
            candidates.append(InstallationCandidate('codex_app_server', str(second),
                fingerprint(second), 'explicit', 'selected'))
        snapshot = local_inventory_snapshot(
            candidates, server_id=registration["server_id"], executor_id=executor,
            producer_instance_id="peer", publication_sequence=1)
        response = client.put(f"/v1/runtime/executors/{executor}/inventory",
                              json=snapshot, headers=ticket)
        assert response.status_code == 200, response.text
        realization_body = {
            "client_intent_id": "realization", "agent_id": "subject",
            "local_realization_ref": "root_1234567890123456",
            "realization_revision": 1, "workspace_id": None,
            "workspace_label": "Project", "adapter_id": "codex_app_server",
            "candidate_ref": snapshot["evidence"][0]["candidate_ref"],
            "inventory_revision": snapshot["inventory_revision"],
            "local_root_proof_digest": "sha256:" + "b" * 64,
            "configuration_digest": "sha256:" + "c" * 64,
            "local_consent_id": "consent",
        }
        local = store = None
        if getattr(request, 'param', None) in ('connector-realization', 'connector-configured'):
            from okto_nexus_connector.services.realization_service import stage_local_realization, publication_body
            from okto_nexus_connector.storage.state_store import StateStore
            store = StateStore(tmp_path / 'connector-state.json')
            workspace = tmp_path / 'remote-workspace'
            workspace.mkdir()
            digest = 'sha256:' + 'c' * 64
            if getattr(request, 'param', None) == 'connector-configured':
                from okto_nexus_connector.services.launch_configuration import stage_launch_configuration
                configuration = stage_launch_configuration(store, server_id=registration['server_id'],
                    executor_id=executor, agent_id='subject', local_consent_id='consent',
                    adapter_id=candidate.adapter_id, profile_revision=1,
                    secret_bindings={'OPENAI_API_KEY': 'vault:provider-demo'})
                digest = configuration.configuration_digest
            local = stage_local_realization(store, server_id=registration['server_id'], executor_id=executor,
                agent_id='subject', client_intent_id='realization', candidates=[candidate],
                adapter_id=candidate.adapter_id, candidate_ref=snapshot['evidence'][0]['candidate_ref'],
                inventory_revision=snapshot['inventory_revision'], workspace_root=workspace,
                workspace_id=None, workspace_label='Project', configuration_digest=digest,
                local_consent_id='consent')
            realization_body = publication_body(local)
        response = client.post(f"/v1/runtime/executors/{executor}/realizations", json=realization_body, headers=ticket)
        assert response.status_code == 201, response.text
        realization = response.json()
        if local is not None:
            from dataclasses import fields
            from okto_nexus_connector.services.realization_service import acknowledge_local_realization
            from okto_nexus_connector.transport.https_client import R4Realization
            acknowledge_local_realization(store, record=local, published=R4Realization(**{
                field.name: realization[field.name] for field in fields(R4Realization)}))
        prepare = {
            "client_intent_id": "prepare", "agent_id_hint": "subject",
            "executor_id": executor, "adapter_id": "codex_app_server",
            "candidate_ref": snapshot["evidence"][0]["candidate_ref"],
            "inventory_revision": snapshot["inventory_revision"],
            "realization_ref": realization["realization_ref"],
            "workspace_id": realization["workspace_id"], "alias": "assistant",
        }
        yield deps, client, headers, prepare


def prepare_operator(client, headers, prepare):
    response = client.post("/v1/connections/bindings:prepare", json=prepare,
                           headers=headers["operator"])
    assert response.status_code == 200, response.text
    proposal = response.json()
    return proposal, {
        "client_intent_id": "apply", "proposal_id": proposal["proposal_id"],
        "proposal_revision": proposal["proposal_revision"],
        "approved_diff_hash": proposal["diff"]["approved_diff_hash"],
    }


def assert_no_binding(deps):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ("agent_endpoints", "runtime_profiles", "execution_bindings",
                      "execution_sessions", "execution_dispatch_outbox"):
            assert uow.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_operator_binding_creates_profile_endpoint_and_scoped_grant(onboarding):
    deps, client, headers, prepare = onboarding
    # A payload subject never makes an ordinary agent an operator.
    denied = client.post("/v1/connections/bindings:prepare", json=prepare,
                         headers=headers["other"])
    assert denied.status_code == 403
    proposal, apply = prepare_operator(client, headers, prepare)
    assert proposal["agent_id"] == "subject"
    assert proposal["profile_id"]
    assert proposal["diff"]["requires_operator"] is True
    assert proposal["required_approvals"] == ["operator_confirmation"]
    assert_no_binding(deps)
    contract = json.loads((Path(__file__).resolve().parents[2] /
                           "plans/contratos/http-target.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator({"$defs": contract["$defs"],
                          **contract["$defs"]["BindingProposal"]}).validate(proposal)
    route = "/v1/connections/bindings:apply"
    assert client.post(route, json=apply, headers=headers["subject"]).status_code == 404
    assert client.post(route, json={**apply, "operator_proof_ref": "forged"},
                       headers=headers["operator"]).status_code == 409
    response = client.post(route, json=apply, headers=headers["operator"])
    assert response.status_code == 200, response.text
    view = response.json()
    assert view["agent_id"] == "subject"
    assert client.post(route, json=apply, headers=headers["operator"]).json() == view
    assert client.post(route, json={**apply, "client_intent_id": "duplicate"},
                       headers=headers["operator"]).status_code == 409
    with deps.connection_factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        endpoint = conn.execute("SELECT * FROM agent_endpoints").fetchone()
        profile = conn.execute("SELECT * FROM runtime_profiles").fetchone()
        assert endpoint["agent_id"] == "subject"
        assert endpoint["profile_id"] == profile["profile_id"] == proposal["profile_id"]
        assert endpoint["enabled"] == profile["enabled"] == 1
        assert endpoint["activation_state"] == "approved"
        assert profile["config"] == profile["secret_refs"] == "{}"
        assert profile["inherit_ambient"] == 0
        assert conn.execute("SELECT COUNT(*) FROM execution_dispatch_outbox").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM runtime_execution_grants").fetchone()[0] == 0
        audit = conn.execute("SELECT actor_agent_id,resource_kind FROM runtime_access_audit "
                             "WHERE action LIKE 'config.%' ORDER BY audit_id").fetchall()
        assert [tuple(row) for row in audit] == [("operator", "profile"), ("operator", "endpoint")]
        stored = conn.execute("SELECT actor_agent_id,subject_agent_id FROM execution_proposals").fetchone()
        assert tuple(stored) == ("operator", "subject")
    me = client.get("/v1/connections/me", headers=headers["subject"]).json()
    assert me["revisions"]["authorization"] == view["authorization_revision"]
    assert me["revisions"]["configuration"] == view["configuration_revision"]
    # Delegation is an explicit authenticated command with an expiry and budget.
    grant = {
        "actor_agent_id": "subject", "endpoint_id": view["endpoint_id"],
        "actions": ["open", "send", "interrupt", "close"], "max_executions": 1,
        "expires_at": iso_plus(deps.clock.now_iso(), 600),
    }
    assert client.post("/api/v1/harness/grants", json=grant,
                       headers=headers["subject"]).status_code == 403
    issued = client.post("/api/v1/harness/grants", json=grant, headers=headers["operator"])
    assert issued.status_code == 200, issued.text
    assert issued.json()["data"]["profile_revision"] == 1


@pytest.mark.parametrize("change", ["subject_policy", "operator_key", "configuration", "expiry", "method"])
def test_operator_binding_revalidates_before_apply(onboarding, change):
    deps, client, headers, prepare = onboarding
    proposal, apply = prepare_operator(client, headers, prepare)
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        if change == "subject_policy":
            conn.execute("UPDATE agents SET permissions=? WHERE agent_id='subject'",
                         (json.dumps({"messages": {"send_direct": False}}),))
        elif change == "operator_key":
            # A newly authenticated operator key cannot approve an old diff.
            key = client.app.state.auth.issue_key(uow, agent_id="operator")
            headers["operator"] = {"Authorization": "Bearer " + key}
        elif change == "configuration":
            conn.execute("UPDATE execution_realizations SET configuration_digest=?",
                         ("sha256:" + "d" * 64,))
        elif change == "expiry":
            conn.execute("UPDATE execution_proposals SET expires_at='2000-01-01T00:00:00Z'")
        else:
            conn.execute("INSERT INTO agent_connection_methods(agent_id,method,enabled) "
                         "VALUES ('subject','codex_app_server',0)")
    response = client.post("/v1/connections/bindings:apply", json=apply,
                           headers=headers["operator"])
    assert response.status_code in (403, 409), response.text
    assert_no_binding(deps)


def test_operator_binding_rolls_back_profile_with_binding(onboarding):
    deps, client, headers, prepare = onboarding
    _, apply = prepare_operator(client, headers, prepare)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER reject_binding BEFORE INSERT ON execution_bindings "
                               "BEGIN SELECT RAISE(ABORT,'Injected binding write failure'); END")
    response = client.post("/v1/connections/bindings:apply", json=apply,
                           headers=headers["operator"])
    assert response.status_code == 500
    assert_no_binding(deps)
    with deps.connection_factory.unit_of_work() as uow:
        assert uow.connection.execute("SELECT status FROM execution_proposals").fetchone()[0] == "PREPARED"
        assert uow.connection.execute("SELECT COUNT(*) FROM runtime_access_audit "
                                      "WHERE action LIKE 'config.%'").fetchone()[0] == 0
        uow.connection.execute("DROP TRIGGER reject_binding")
    assert client.post("/v1/connections/bindings:apply", json=apply,
                       headers=headers["operator"]).status_code == 200


def test_binding_does_not_turn_self_confirmation_into_execution_authority(onboarding):
    deps, client, headers, prepare = onboarding
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO agent_connection_methods(agent_id,method,enabled) "
                               "VALUES ('subject','codex_app_server',0)")
    denied = client.post("/v1/connections/bindings:prepare", json=prepare,
                         headers=headers["operator"])
    assert denied.status_code == 403
    response = client.post("/v1/connections/bindings:prepare", json=prepare,
                           headers=headers["subject"])
    assert response.status_code == 403, response.text
    assert_no_binding(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT enabled FROM agent_connection_methods").fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM runtime_execution_grants").fetchone()[0] == 0


def prepare_delegated(client, headers, prepare):
    response = client.post("/v1/connections/bindings:prepare", json=prepare,
                           headers=headers["subject"])
    assert response.status_code == 200, response.text
    proposal = response.json()
    approval_id = next(item for item in proposal["required_approvals"] if item.startswith("apr_"))
    apply = {"client_intent_id": "apply", "proposal_id": proposal["proposal_id"],
             "proposal_revision": proposal["proposal_revision"],
             "approved_diff_hash": proposal["diff"]["approved_diff_hash"],
             "operator_proof_ref": approval_id}
    return proposal, apply, approval_id


def decide_binding(client, headers, approval_id, decision="approve"):
    return client.post(f"/api/v1/approvals/{approval_id}/decision",
                       json={"decision": decision}, headers=headers["operator"])


def connection_preferences(prepare):
    return dict(format='okto-nexus-connection', version=2,
        adapter_id=prepare['adapter_id'], alias=prepare['alias'], runtime_enabled=True,
        session_policy='per_sender', harness_settings={}, automatic_reply=True,
        tool_access='ask', authorization=dict(minutes=60, actions=20))


@pytest.mark.parametrize('onboarding', [None, 'human-operator'], indirect=True)
def test_single_approval_applies_configuration_and_scoped_grant_atomically(onboarding):
    deps, client, headers, prepare = onboarding
    prepare['connection_configuration'] = connection_preferences(prepare)
    proposal, apply, approval_id = prepare_delegated(client, headers, prepare)
    waiting = client.post('/v1/connections/bindings:apply', json=apply, headers=headers['subject'])
    assert waiting.status_code == 403
    assert waiting.json()['error']['code'] == 'APPROVAL_REQUIRED'
    assert_no_binding(deps)
    assert '60 minutes, 20 actions' in proposal['diff']['summary']
    decision_headers = {} if client._transport.client[0] == '127.0.0.1' else headers['operator']
    assert client.post(f'/api/v1/approvals/{approval_id}/decision',
        json={'decision':'approve'}, headers=decision_headers).status_code == 200
    applied = client.post('/v1/connections/bindings:apply', json=apply, headers=headers['subject'])
    assert applied.status_code == 200, applied.text
    replay = client.post('/v1/connections/bindings:apply', json=apply, headers=headers['subject'])
    assert replay.json() == applied.json()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        grant = uow.connection.execute('SELECT * FROM runtime_execution_grants').fetchall()
        assert len(grant) == 1
        assert grant[0]['max_executions'] == 20
        assert not grant[0]['no_expiry'] and not grant[0]['unlimited_actions']
        assert grant[0]['endpoint_id'] == applied.json()['endpoint_id']
        policy = uow.connection.execute("SELECT * FROM agent_runtime_overrides WHERE agent_id='subject'").fetchone()
        assert policy['runtime_enabled'] == 1 and policy['session_policy'] == 'per_sender'


def test_single_approval_rejection_is_terminal_and_creates_no_grant(onboarding):
    deps, client, headers, prepare = onboarding
    prepare['connection_configuration'] = connection_preferences(prepare)
    _, apply, approval_id = prepare_delegated(client, headers, prepare)
    assert decide_binding(client, headers, approval_id, 'reject').status_code == 200
    rejected = client.post('/v1/connections/bindings:apply', json=apply, headers=headers['subject'])
    assert rejected.status_code == 403
    assert rejected.json()['error']['code'] == 'PERMISSION_DENIED'
    assert_no_binding(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_execution_grants').fetchone()[0] == 0


def test_single_approval_configuration_failure_rolls_back_binding_and_grant(onboarding):
    deps, client, headers, prepare = onboarding
    prepare['connection_configuration'] = connection_preferences(prepare)
    _, apply, approval_id = prepare_delegated(client, headers, prepare)
    assert decide_binding(client, headers, approval_id).status_code == 200
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER fail_grant BEFORE INSERT ON runtime_execution_grants "
                               "BEGIN SELECT RAISE(ABORT,'Injected grant failure'); END")
    failed = client.post('/v1/connections/bindings:apply', json=apply, headers=headers['subject'])
    assert failed.status_code == 500
    assert_no_binding(deps)
    with deps.connection_factory.unit_of_work() as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM agent_runtime_overrides WHERE agent_id='subject'").fetchone()[0] == 0
        uow.connection.execute('DROP TRIGGER fail_grant')
    assert client.post('/v1/connections/bindings:apply', json=apply, headers=headers['subject']).status_code == 200


def test_single_approval_request_cannot_be_changed_after_review(onboarding):
    deps, client, headers, prepare = onboarding
    prepare['connection_configuration'] = connection_preferences(prepare)
    _, apply, approval_id = prepare_delegated(client, headers, prepare)
    prepare['connection_configuration']['authorization']['actions'] = 1000
    assert client.post('/v1/connections/bindings:prepare', json=prepare, headers=headers['subject']).status_code == 409
    assert_no_binding(deps)
    assert decide_binding(client, headers, approval_id).status_code == 200
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_proposals SET expires_at='2000-01-01T00:00:00Z'")
    assert client.post('/v1/connections/bindings:apply', json=apply, headers=headers['subject']).status_code == 409
    assert_no_binding(deps)


def test_binding_delegated_proof_uses_atomic_operator_decision(onboarding):
    deps, client, headers, prepare = onboarding
    proposal, apply, approval_id = prepare_delegated(client, headers, prepare)
    assert_no_binding(deps)
    replay = client.post("/v1/connections/bindings:prepare", json=prepare,
                         headers=headers["subject"])
    assert replay.json() == proposal
    assert client.post("/v1/connections/bindings:apply", json=apply,
                       headers=headers["subject"]).status_code == 403
    # Neither a caller-provided decider string nor an agent bearer is proof.
    with pytest.raises(OktoNexusError):
        deps.approvals.decide(approval_id=approval_id, decision="approve", decided_by="operator")
    assert client.post(f"/api/v1/approvals/{approval_id}/decision",
                       json={"decision": "approve"}, headers=headers["subject"]).status_code == 403
    detail = client.get(f"/api/v1/approvals/{approval_id}", headers=headers["operator"])
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["request_payload"]["kwargs"]["approved_diff_hash"] == apply["approved_diff_hash"]
    approved = decide_binding(client, headers, approval_id)
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["executed_result"]["operator_proof_ref"] == approval_id
    assert_no_binding(deps)
    # Both proof and decision survive reopening the database before apply.
    reopened = bootstrap({}, ["--home", str(deps.config.home_dir),
                               "--feature-harness-integrations", "true"])
    assert reopened.approvals.get_approval(approval_id=approval_id)["status"] == "approved"
    with reopened.connection_factory.unit_of_work(write=False) as uow:
        proof = uow.connection.execute("SELECT operator_proof_json FROM execution_proposals").fetchone()[0]
        assert json.loads(proof)["approval_id"] == approval_id
        assert uow.connection.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 1
    repeated = decide_binding(client, headers, approval_id)
    assert repeated.status_code == 200 and repeated.json()["data"]["reused"] is True
    assert decide_binding(client, headers, approval_id, "reject").status_code == 409
    committed = client.post("/v1/connections/bindings:apply", json=apply,
                            headers=headers["subject"])
    assert committed.status_code == 200, committed.text
    assert client.post("/v1/connections/bindings:apply", json=apply,
                       headers=headers["subject"]).json() == committed.json()
    assert decide_binding(client, headers, approval_id).status_code == 200
    with deps.connection_factory.unit_of_work(write=False) as uow:
        endpoint = uow.connection.execute("SELECT enabled,profile_id,agent_id FROM agent_endpoints").fetchone()
        assert tuple(endpoint) == (1, proposal["profile_id"], "subject")
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_dispatch_outbox").fetchone()[0] == 0


@pytest.mark.parametrize("change", ["operator_key", "subject_policy", "expiry", "wrong_proposal"])
def test_binding_delegated_proof_cannot_authorize_changed_scope(onboarding, change):
    deps, client, headers, prepare = onboarding
    _, apply, approval_id = prepare_delegated(client, headers, prepare)
    other_apply = None
    if change == "wrong_proposal":
        _, other_apply, _ = prepare_delegated(
            client, headers, {**prepare, "client_intent_id": "another", "alias": "different"})
    assert decide_binding(client, headers, approval_id).status_code == 200
    with deps.connection_factory.unit_of_work() as uow:
        if change == "operator_key":
            client.app.state.auth.issue_key(uow, agent_id="operator")
        elif change == "subject_policy":
            uow.connection.execute("UPDATE agents SET permissions=? WHERE agent_id='subject'",
                                   (json.dumps({"messages": {"send_direct": False}}),))
        elif change == "expiry":
            uow.connection.execute("UPDATE execution_proposals SET expires_at='2000-01-01T00:00:00Z'")
    if other_apply:
        apply = {**other_apply, "operator_proof_ref": approval_id}
    response = client.post("/v1/connections/bindings:apply", json=apply,
                           headers=headers["subject"])
    assert response.status_code in (403, 409), response.text
    assert_no_binding(deps)


def test_binding_rejected_proposal_cannot_be_applied(onboarding):
    deps, client, headers, prepare = onboarding
    _, apply, approval_id = prepare_delegated(client, headers, prepare)
    rejected = decide_binding(client, headers, approval_id, "reject")
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["data"]["executed_result"]["operator_proof_ref"] is None
    assert decide_binding(client, headers, approval_id).status_code == 409
    response = client.post("/v1/connections/bindings:apply", json=apply,
                           headers=headers["subject"])
    assert response.status_code == 403
    assert_no_binding(deps)


def test_binding_proof_and_decision_roll_back_together(onboarding):
    deps, client, headers, prepare = onboarding
    _, apply, approval_id = prepare_delegated(client, headers, prepare)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER reject_proof_result BEFORE UPDATE OF executed_result ON approvals "
                               "BEGIN SELECT RAISE(ABORT,'Injected decision result failure'); END")
    failed = decide_binding(client, headers, approval_id)
    assert failed.status_code == 503, failed.text
    assert failed.json()["error"]["code"] == "DB_ERROR"
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        assert conn.execute("SELECT status FROM approvals").fetchone()[0] == "pending"
        assert conn.execute("SELECT operator_proof_json FROM execution_proposals").fetchone()[0] is None
        conn.execute("DROP TRIGGER reject_proof_result")
    assert_no_binding(deps)
    assert decide_binding(client, headers, approval_id).status_code == 200
    assert client.post("/v1/connections/bindings:apply", json=apply,
                       headers=headers["subject"]).status_code == 200


def test_binding_stale_proposal_cannot_receive_operator_proof(onboarding):
    deps, client, headers, prepare = onboarding
    _, _, approval_id = prepare_delegated(client, headers, prepare)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET metadata='{}' WHERE agent_id='subject'")
        uow.connection.execute("UPDATE execution_proposals SET expires_at='2000-01-01T00:00:00Z'")
    assert decide_binding(client, headers, approval_id).status_code == 409
    assert decide_binding(client, headers, approval_id, "reject").status_code == 200
    assert_no_binding(deps)
