"""Public native operator CAS, canonical audit and one durable application."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from nexus_connector_core import R4_PREVIEW_REVISION
import pytest

from okto_nexus.application.execution_admission import submit_execution_operation
from okto_nexus.application.execution_events import commit_execution_events
from okto_nexus.application.execution_intents import resolve_execution_intent
from okto_nexus.application.execution_native_decisions import NativeInputRetention
from okto_nexus.errors import OktoNexusError
from test_open_bootstrap import opening, begin
from test_session_capabilities import apply_lease


@pytest.fixture
def decision_state(opening, request):
    deps, app, _, _, _, channel, resolution, _ = opening
    deps.config.feature_hitl = True
    begin(opening)
    leases, _, _, ack = apply_lease(opening)
    leases.applied(ack, channel=channel)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET lifecycle_state='READY',stream_epoch='native-epoch'")
    native_case = getattr(request, "param", None)
    actor = "operator" if native_case in {"input", "nonblocking_input", "form", "mcp_permission"} else "subject"
    from okto_nexus.bootstrap.execution_authority import build_execution_access
    from okto_nexus.domain.runtime_context import RuntimeRequestContext
    authority = dict(access=build_execution_access(deps), context=RuntimeRequestContext(
        actor, "http_loopback", trusted_local_operator=actor == "operator"))
    turn = resolve_execution_intent(deps.connection_factory, actor_agent_id=actor,
        request=dict(client_intent_id="turn", intent="turn.submit", binding_id="binding", agent_id="subject",
                     workspace_binding_id="wxb", session_id=resolution["session_id"], text="Wait for permission"),
        remote_ready=True, fresh_publications=app.state.inventory_fresh_publications, **authority)
    assert turn["can_submit"], turn
    submit_execution_operation(deps.connection_factory, actor_agent_id=actor,
        request={key: turn[key] for key in ("client_intent_id", "operation_id", "resolution_revision", "intent_hash")},
        remote_ready=True, fresh_publications=app.state.inventory_fresh_publications, **authority)
    native_case = getattr(request, "param", None)
    is_input = native_case in {"input", "nonblocking_input", "agent_input", "form", "mcp_permission"}
    proposal = dict(schema_version=1, request_id=7, request_hash="a"*64,
        method="item/tool/requestUserInput" if is_input else "item/commandExecution/requestApproval",
        params={"turnId": "native-turn", "itemId": "item", "authorization": "Bearer private-marker"})
    if is_input:
        proposal['params']['isBlocking'] = native_case != 'nonblocking_input'
        proposal['params']['questions'] = [{'id': 'question', 'header': 'Choice', 'question': 'Choose the next step',
            'isOther': True, 'options': [{'label': 'Continue', 'description': 'Proceed with the reviewed work'},
                                      {'label': 'Stop', 'description': 'End this work'}]}]
    if native_case == 'form':
        proposal['method'] = 'mcpServer/elicitation/request'
        proposal['params'] = {'turnId': 'native-turn', 'mode': 'form', 'serverName': 'fixture', 'message': 'Review fixture values', 'requestedSchema': {
            'type': 'object', 'properties': {
                'count': {'type': 'integer', 'minimum': 1, 'maximum': 5, 'default': 2},
                'enabled': {'type': 'boolean', 'default': True},
                'note': {'type': 'string'}}, 'required': ['count', 'enabled']}}
    if native_case == 'mcp_permission':
        proposal['method'] = 'mcpServer/elicitation/request'
        proposal['params'] = {'turnId': 'native-turn', 'mode': 'form', 'serverName': 'nexus_test',
            'message': 'Allow Nexus agent_whoami?', '_meta': {'codex_approval_kind': 'mcp_tool_call'},
            'requestedSchema': {'type': 'object', 'properties': {}}}
    scope = resolution["scope"]
    frame = {key: scope[key] for key in ("server_id", "executor_id", "binding_id", "agent_id", "session_id")}
    frame.update(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, type="event.batch",
        connection_id=channel.connection_id, connection_generation=channel.connection_generation,
        stream_epoch="native-epoch", events=[dict(
            server_id=channel.server_id, executor_id=channel.executor_id, session_id=scope["session_id"],
            stream_epoch="native-epoch", sequence=1, category="input_request" if is_input else "approval_request",
            operation_id=turn["operation_id"], payload={"native_approval": proposal,
                "native_approval_display": {**proposal, "params": {**proposal['params'], "authorization": "[REDACTED]"}}})])
    commit_execution_events(deps.connection_factory, channel=channel, frame=frame, approvals=deps.approvals)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT * FROM approvals WHERE action='execution.native.respond'").fetchone()
        assert row is not None
        assert "private-marker" not in row["request_payload"]
        details = json.loads(row["request_payload"])["kwargs"]
    body = {key: details[key] for key in ("approval_key", "expected_revision", "request_hash", "cas_token")}
    body.update(client_intent_id="decision", decision="approve")
    if is_input: body["response"] = {"answers": {"question": {"answers": ["sensitive-input-marker"]}}}
    if native_case == 'form': body['response'] = {'content': {'count': 3, 'enabled': False, 'note': ''}}
    if native_case == 'mcp_permission': body['response'] = {'content': {}}
    return deps, app, body


@pytest.mark.parametrize("decision_state", ["input", "agent_input", "nonblocking_input"], indirect=True)
def test_question_listing_and_decision_belong_to_originating_interlocutor(decision_state):
    deps, app, body = decision_state
    with deps.connection_factory.unit_of_work(write=False) as uow:
        recipient = uow.connection.execute("SELECT actor_agent_id FROM execution_operations WHERE action='turn.submit'").fetchone()[0]
    client = TestClient(app)
    for actor in ("operator", "subject", "other"):
        response = client.get("/v1/runtime/input-requests", headers={"Authorization": "Bearer " + app.state.test_agent_keys[actor]})
        assert response.status_code == 200, response.text
        assert len(response.json()["items"]) == (1 if actor == recipient else 0)
        if actor != recipient:
            assert post(decision_state, actor=actor).status_code == 403
    invalid = copy.deepcopy(body)
    invalid["response"] = {"answers": {"wrong-question": {"answers": ["no"]}}}
    before = snapshot(decision_state)
    assert post(decision_state, invalid, actor=recipient).status_code == 422
    assert snapshot(decision_state) == before
    accepted = post(decision_state, actor=recipient)
    assert accepted.status_code == 202, accepted.text
    from okto_nexus.application.execution_dispatch import reserve_execution_dispatch, begin_execution_send
    from okto_nexus.bootstrap.execution_authority import build_execution_access
    key = body["approval_key"]
    reservation = reserve_execution_dispatch(deps.connection_factory,
        server_id=key["server_id"], executor_id=key["executor_id"], remote_ready=True)
    sent = begin_execution_send(deps.connection_factory, reservation=reservation,
        remote_ready=True, fresh_publications=app.state.inventory_fresh_publications,
        access=build_execution_access(deps), resolve_native_input=deps.native_decisions.inputs.resolve)
    assert sent.frame["payload"]["response"] == body["response"]


def post(state, body=None, actor="operator"):
    _, app, original = state
    return TestClient(app).post("/v1/runtime/approval-decisions", json=body or original,
        headers={"Authorization": "Bearer " + app.state.test_agent_keys[actor]})


def snapshot(state):
    with state[0].connection_factory.unit_of_work(write=False) as uow:
        return {table: [dict(row) for row in uow.connection.execute("SELECT * FROM " + table)]
                for table in ("execution_decisions", "execution_client_intents", "execution_operations",
                              "execution_dispatch_outbox", "execution_native_requests", "approvals")}


@pytest.mark.parametrize("choice,native,status", [("approve", "accept", "CONFIRMED"), ("deny", "decline", "DENIED")])
def test_public_cas_records_exactly_one_application_and_replay(decision_state, choice, native, status):
    deps, app, body = decision_state
    body["decision"] = choice
    response = post(decision_state)
    assert response.status_code == 202, response.text
    view = response.json()
    assert response.headers["cache-control"] == "no-store"
    assert (view["native_decision"], view["canonical_state"], view["native_stage"]) == (native, status, "DISPATCH_PENDING")
    assert view["possible_effect"] is False
    schema = json.loads((Path(__file__).parents[2]/"plans/contratos/http-target.schema.json").read_text())
    Draft202012Validator(dict(schema, **{"$ref": "#/$defs/DecisionView"}), format_checker=FormatChecker()).validate(view)
    stored = snapshot(decision_state)
    assert len(stored["execution_decisions"]) == 1
    assert sum(row["action"] == "approval.decide" for row in stored["execution_operations"]) == 1
    assert sum(row["operation_id"] == view["native_operation_id"] for row in stored["execution_dispatch_outbox"]) == 1
    assert stored["approvals"][0]["status"] == ("approved" if choice == "approve" else "rejected")
    repeat = post(decision_state)
    assert repeat.status_code == 200 and repeat.json() == view
    assert snapshot(decision_state) == stored
    for actor, expected in (("operator", 200), ("subject", 200), ("other", 404)):
        result = TestClient(app).get("/v1/runtime/approval-decisions/"+view["decision_id"],
            headers={"Authorization": "Bearer "+app.state.test_agent_keys[actor]})
        assert result.status_code == expected, result.text
        assert "private-marker" not in result.text
        operation = TestClient(app, raise_server_exceptions=False).get(
            "/v1/runtime/operations/"+view["native_operation_id"],
            headers={"Authorization": "Bearer "+app.state.test_agent_keys[actor]})
        assert operation.status_code == expected, operation.text
        assert "private-marker" not in operation.text


@pytest.mark.parametrize("fault", ["subject", "other", "hash", "revision", "cas", "scope", "generation", "expired", "terminal", "grant", "profile"])
def test_invalid_or_stale_decision_cannot_create_an_operation(decision_state, fault):
    deps, _, body = decision_state
    actor = fault if fault in {"subject", "other"} else "operator"
    if fault == "hash": body["request_hash"] = "sha256:"+"b"*64
    elif fault == "revision": body["expected_revision"] = 2
    elif fault == "cas": body["cas_token"] = "x"*32
    elif fault == "scope": body["approval_key"]["agent_id"] = "other"
    elif fault == "generation": body["approval_key"]["session_owner_generation"] = 2
    elif fault in {"expired", "terminal", "grant", "profile"}:
        sql = {"expired": "UPDATE execution_native_requests SET expires_at='2000-01-01T00:00:00Z'",
               "terminal": "UPDATE execution_native_requests SET state='STALE'",
               "grant": "UPDATE runtime_execution_grants SET revoked_at='now'",
               "profile": "UPDATE runtime_profiles SET enabled=0"}[fault]
        with deps.connection_factory.unit_of_work() as uow: uow.connection.execute(sql)
    before = snapshot(decision_state)
    response = post(decision_state, actor=actor)
    assert response.status_code in {403, 409}, response.text
    assert snapshot(decision_state) == before


def test_two_interfaces_race_for_one_canonical_decision(decision_state):
    deny = copy.deepcopy(decision_state[2])
    deny.update(client_intent_id="other-interface", decision="deny")
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(post, decision_state)
        second = pool.submit(post, decision_state, deny)
        assert sorted((first.result().status_code, second.result().status_code)) == [202, 409]
    stored = snapshot(decision_state)
    assert len(stored["execution_decisions"]) == 1
    assert sum(row["action"] == "approval.decide" for row in stored["execution_operations"]) == 1


def test_outbox_failure_rolls_back_canonical_approval_and_decision(decision_state):
    deps, _, _ = decision_state
    before = snapshot(decision_state)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER fail_decision_outbox BEFORE INSERT ON execution_dispatch_outbox "
                               "BEGIN SELECT RAISE(ABORT,'Injected outbox failure'); END")
    with pytest.raises(Exception, match="Injected outbox failure"):
        post(decision_state)
    assert snapshot(decision_state) == before


@pytest.mark.parametrize("decision_state", ["input"], indirect=True)
def test_sensitive_input_is_retained_in_memory_and_explicitly_resupplied_after_loss(decision_state):
    deps, _, body = decision_state
    response = post(decision_state)
    assert response.status_code == 202, response.text
    stored = snapshot(decision_state)
    assert "sensitive-input-marker" not in json.dumps(stored)
    operation = next(row for row in stored["execution_operations"] if row["action"] == "input.provide")
    frame = json.loads(operation["semantic_payload"])
    assert deps.native_decisions.inputs.resolve(frame) == body["response"]
    deps.native_decisions.inputs.close()
    with pytest.raises(OktoNexusError) as lost:
        deps.native_decisions.inputs.resolve(frame)
    assert lost.value.code == "AUTHORIZED_INPUT_UNAVAILABLE"
    repeated = post(decision_state)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == response.json()
    assert deps.native_decisions.inputs.resolve(frame) == body["response"]
    assert snapshot(decision_state) == stored


@pytest.mark.parametrize("fault", [None, "operator", "decision", "payload", "grant"])
def test_dispatch_revalidates_operator_decision_and_uses_control_lane(decision_state, fault):
    from okto_nexus.application.execution_dispatch import reserve_execution_dispatch, begin_execution_send
    from okto_nexus.bootstrap.execution_authority import build_execution_access
    deps, app, _ = decision_state
    response = post(decision_state)
    assert response.status_code == 202, response.text
    view = response.json()
    key = view["approval_key"]
    reservation = reserve_execution_dispatch(deps.connection_factory,
        server_id=key["server_id"], executor_id=key["executor_id"], remote_ready=True)
    assert reservation.operation_id == view["native_operation_id"]
    with deps.connection_factory.unit_of_work() as uow:
        if fault == "operator": uow.connection.execute("UPDATE agents SET is_active=0 WHERE agent_id='operator'")
        elif fault == "decision": uow.connection.execute("UPDATE approvals SET status='pending' WHERE action='execution.native.respond'")
        elif fault == "payload": uow.connection.execute("UPDATE execution_decisions SET decision='decline'")
        elif fault == "grant": uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at='now'")
        budget = uow.connection.execute("SELECT used_executions FROM runtime_execution_grants").fetchone()[0]
    def send():
        return begin_execution_send(deps.connection_factory, reservation=reservation,
            remote_ready=True, fresh_publications=app.state.inventory_fresh_publications,
            access=build_execution_access(deps))
    if fault is not None:
        with pytest.raises(OktoNexusError): send()
    else:
        sent = send()
        assert sent.frame["action"] == "approval.decide"
        assert sent.frame["payload"]["request"]["params"]["authorization"] == "Bearer private-marker"
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants").fetchone()[0] == budget


@pytest.mark.parametrize("decision_state", ["input"], indirect=True)
def test_input_dispatch_reconstructs_exact_wire_without_persisting_response(decision_state):
    from okto_nexus.application.execution_dispatch import reserve_execution_dispatch, begin_execution_send
    from okto_nexus.bootstrap.execution_authority import build_execution_access
    from nexus_connector_core import decode_r4_frame, encode_r4_frame, r4_native_decision_operation
    deps, app, body = decision_state
    view = post(decision_state).json()
    key = view["approval_key"]
    reservation = reserve_execution_dispatch(deps.connection_factory,
        server_id=key["server_id"], executor_id=key["executor_id"], remote_ready=True)
    def send():
        return begin_execution_send(deps.connection_factory, reservation=reservation,
            remote_ready=True, fresh_publications=app.state.inventory_fresh_publications,
            access=build_execution_access(deps), resolve_native_input=deps.native_decisions.inputs.resolve)
    deps.native_decisions.inputs.close()
    with pytest.raises(OktoNexusError) as missing: send()
    assert missing.value.code == "AUTHORIZED_INPUT_UNAVAILABLE"
    assert post(decision_state).status_code == 200  # Explicit matching resupply.
    sent = send()
    assert "sensitive-input-marker" not in repr(sent)
    wire = decode_r4_frame(encode_r4_frame(sent.frame))
    assert "response_ref" not in wire["payload"]
    assert r4_native_decision_operation(wire).operator_response == body["response"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for record in uow.connection.iterdump():
            assert "sensitive-input-marker" not in record
    # A possible send is fenced. Replaying it cannot resend the response.
    with pytest.raises(OktoNexusError): send()


@pytest.mark.parametrize("decision_state", ["input"], indirect=True)
def test_lost_input_is_reported_without_inventing_a_native_receipt(decision_state):
    from okto_nexus.application.execution_dispatch import reserve_execution_dispatch, begin_execution_send
    from okto_nexus.adapters.outbound.sqlite.execution_dispatch_ownership import reject_unsent_dispatch
    from okto_nexus.bootstrap.execution_authority import build_execution_access
    deps, app, _ = decision_state
    view = post(decision_state).json()
    key = view["approval_key"]
    reservation = reserve_execution_dispatch(deps.connection_factory, server_id=key["server_id"],
        executor_id=key["executor_id"], remote_ready=True)
    deps.native_decisions.inputs.close()
    with pytest.raises(OktoNexusError) as missing:
        begin_execution_send(deps.connection_factory, reservation=reservation, remote_ready=True,
            fresh_publications=app.state.inventory_fresh_publications, access=build_execution_access(deps),
            resolve_native_input=deps.native_decisions.inputs.resolve)
    reject_unsent_dispatch(deps.connection_factory, reservation=reservation, error=missing.value)
    client = TestClient(app)
    headers = {"Authorization": "Bearer "+app.state.test_agent_keys["operator"]}
    updated = client.get("/v1/runtime/approval-decisions/"+view["decision_id"], headers=headers).json()
    assert updated["canonical_state"] == "CONFIRMED"
    assert updated["native_stage"] == "REFUSED_BEFORE_EFFECT"
    assert updated["possible_effect"] is False
    operation = client.get("/v1/runtime/operations/"+view["native_operation_id"], headers=headers)
    assert operation.status_code == 200, operation.text
    assert operation.json()["error"]["code"] == "AUTHORIZED_INPUT_UNAVAILABLE"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_receipts WHERE operation_id=?",
                                      (view["native_operation_id"],)).fetchone()[0] == 0
