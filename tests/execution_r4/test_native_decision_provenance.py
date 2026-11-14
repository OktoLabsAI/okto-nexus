"""Durable authentication modality survives native decision asynchronous dispatch."""
import json

from fastapi.testclient import TestClient
import pytest

from okto_nexus.application.execution_dispatch import begin_execution_send, reserve_execution_dispatch
from okto_nexus.bootstrap.execution_authority import build_execution_access
from okto_nexus.errors import OktoNexusError
import test_native_decisions as native_fixtures
from test_native_decisions import post, snapshot

decision_state = native_fixtures.decision_state
opening = native_fixtures.opening


def dispatch(state, view):
    deps, app, _ = state
    key = view["approval_key"]
    reservation = reserve_execution_dispatch(deps.connection_factory,
        server_id=key["server_id"], executor_id=key["executor_id"], remote_ready=True)
    assert reservation.operation_id == view["native_operation_id"]
    return begin_execution_send(deps.connection_factory, reservation=reservation,
        remote_ready=True, fresh_publications=app.state.inventory_fresh_publications,
        access=build_execution_access(deps))


def local_post(state, *, host="127.0.0.1", headers=None):
    _, app, body = state
    app.state.local_open = True
    return TestClient(app, base_url="http://127.0.0.1", client=(host, 45678)).post(
        "/api/v1/runtime-management/runtime/approval-decisions", json=body, headers=headers)


@pytest.mark.parametrize("change", [None, "actor", "grant", "scope", "legacy"])
def test_keyless_loopback_decision_revalidates_before_async_dispatch(decision_state, change):
    deps, _, _ = decision_state
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET api_key_hash=NULL WHERE agent_id='operator'")
    response = local_post(decision_state)
    assert response.status_code == 202, response.text
    assert "credential_binding" not in response.text and "native-actor-v1" not in response.text
    view = response.json()
    with deps.connection_factory.unit_of_work() as uow:
        guard = uow.connection.execute("SELECT actor_guard_digest FROM execution_decisions").fetchone()[0]
        proof = json.loads(guard.removeprefix("native-actor-v1:"))
        assert proof["authentication_source"] == "http_loopback"
        assert proof["trusted_local_operator"] is True and proof["credential_binding"] is None
        if change == "actor":
            uow.connection.execute("UPDATE agents SET is_active=0 WHERE agent_id='operator'")
        elif change == "grant":
            uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at='now'")
        elif change == "scope":
            uow.connection.execute("UPDATE execution_sessions SET owner_generation=owner_generation+1")
        elif change == "legacy":
            uow.connection.execute("UPDATE execution_decisions SET actor_guard_digest=?", (proof["agent_guard"],))
    if change:
        with pytest.raises(OktoNexusError):
            dispatch(decision_state, view)
    else:
        sent = dispatch(decision_state, view)
        assert sent.frame["action"] == "approval.decide"
        assert sent.frame["payload"]["decision"] == "accept"


@pytest.mark.parametrize("change", [None, "rotate", "revoke"])
def test_remote_key_uses_original_binding_and_never_local_authority(decision_state, change):
    response = post(decision_state)
    assert response.status_code == 202, response.text
    deps, _, _ = decision_state
    with deps.connection_factory.unit_of_work() as uow:
        guard = uow.connection.execute("SELECT actor_guard_digest FROM execution_decisions").fetchone()[0]
        proof = json.loads(guard.removeprefix("native-actor-v1:"))
        original = uow.connection.execute("SELECT api_key_hash FROM agents WHERE agent_id='operator'").fetchone()[0]
        assert proof["credential_binding"] == original
        assert proof["authentication_source"] == "agent_key" and proof["trusted_local_operator"] is False
        if change:
            uow.connection.execute("UPDATE agents SET api_key_hash=? WHERE agent_id='operator'",
                ("rotated-key-hash" if change == "rotate" else None,))
    if change:
        with pytest.raises(OktoNexusError):
            dispatch(decision_state, response.json())
    else:
        assert dispatch(decision_state, response.json()).frame["action"] == "approval.decide"


@pytest.mark.parametrize("host,headers", [
    ("203.0.113.8", {"x-nexus-trusted-local-operator": "true"}),
    ("127.0.0.1", {"x-forwarded-for": "127.0.0.1"}),
])
def test_nonlocal_or_forwarded_caller_cannot_claim_local_modality(decision_state, host, headers):
    before = snapshot(decision_state)
    response = local_post(decision_state, host=host, headers=headers)
    assert response.status_code in (401, 403), response.text
    assert snapshot(decision_state) == before


def test_decision_body_cannot_supply_authority_envelope(decision_state):
    before = snapshot(decision_state)
    decision_state[2]["actor_guard_digest"] = "native-actor-v1:{}"
    response = local_post(decision_state)
    assert response.status_code == 422, response.text
    assert snapshot(decision_state) == before


@pytest.mark.parametrize("local", [True, False])
def test_attention_uses_same_provenance_without_public_binding(decision_state, local):
    from test_attention_authority import read, project
    deps, _, _ = decision_state
    if local:
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agents SET api_key_hash=NULL WHERE agent_id='operator'")
    response = local_post(decision_state) if local else post(decision_state)
    assert response.status_code == 202, response.text
    with deps.connection_factory.unit_of_work() as uow:
        facts, policy, now = read(uow, deps)
        pending = next(row for row in facts if row['family'] == 'dispatch'
            and row['work']['action'] == 'approval.decide')
        assert project(pending, now, policy) == []
        uow.connection.execute("UPDATE agents SET is_active=0 WHERE agent_id='operator'")
        facts, policy, now = read(uow, deps)
        pending = next(row for row in facts if row['family'] == 'dispatch'
            and row['work']['action'] == 'approval.decide')
        projected = project(pending, now, policy)
        assert len(projected) == 1
        public = json.dumps(projected)
        assert 'credential_binding' not in public and 'native-actor-v1:' not in public


@pytest.mark.parametrize("delta", [
    {'trusted_local_operator': 1}, {'authentication_source': 'remote_claim'},
    {'credential_binding': 'invented'}, {'actor_agent_id': 'other'},
    {'extra': True},
])
def test_internal_provenance_parser_rejects_ambiguous_modality(delta):
    from okto_nexus.application.execution_native_decisions import _recorded_actor
    proof = dict(actor_agent_id='operator', agent_guard='sha256:'+'0'*64,
        authentication_source='http_loopback', trusted_local_operator=True, credential_binding=None)
    proof.update(delta)
    with pytest.raises(OktoNexusError):
        _recorded_actor('native-actor-v1:'+json.dumps(proof), 'operator')
