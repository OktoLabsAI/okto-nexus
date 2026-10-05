"""Native requests are immutable, scoped facts in the event ACK transaction."""
import copy
import json
import sqlite3

import pytest
from nexus_connector_core import CoreError, r4_operational_request_hash
from nexus_connector_core.protocol import canonical_json

from test_event_ingress import ingress, recovery, onboarding, commit, snapshot


@pytest.fixture
def native(ingress):
    factory, channel, frame = ingress
    with factory.unit_of_work() as uow:
        conn = uow.connection
        operation = conn.execute("SELECT * FROM execution_operations WHERE operation_id='close'").fetchone()
        scope = {name: operation[name] for name in (
            "server_id", "executor_id", "binding_id", "workspace_id", "workspace_binding_id", "session_id")}
        scope.update(agent_id="subject", session_owner_generation=1,
                     authorization_revision=1, configuration_revision=1,
                     credential_epoch=1, binding_revision=1)
        conn.execute("UPDATE execution_operations SET action='turn.submit',expected_revisions_json=?",
                     (json.dumps(scope),))
    request = dict(schema_version=1, request_id="nxs_native_id", request_hash="a" * 64,
                   method="item/commandExecution/requestApproval",
                   params={"turnId": "turn", "itemId": "item",
                           "authorization": "Bearer protected-value"})
    frame["events"][0].update(category="approval_request", payload={
        "native_approval": request,
        "native_approval_display": {**request, "request_id": "[REDACTED]",
                                    "params": {"turnId": "turn", "authorization": "[REDACTED]"}}})
    return ingress


def requests(factory):
    with factory.unit_of_work(write=False) as uow:
        return [dict(row) for row in uow.connection.execute(
            "SELECT * FROM execution_native_requests ORDER BY canonical_request_id")]


def test_intact_proposal_redacted_display_and_replay_after_reopen(native):
    from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
    factory, channel, frame = native
    original = canonical_json(frame["events"][0]["payload"]["native_approval"])
    assert commit(native)["sequence"] == 1
    saved = requests(factory)
    assert len(saved) == 1 and saved[0]["state"] == "PENDING"
    operational = json.loads(saved[0]["operational_frame_json"])["operational_request"]
    assert canonical_json(operational) == original
    assert saved[0]["request_hash"] == r4_operational_request_hash(operational)
    assert saved[0]["native_request_id_json"] == '"nxs_native_id"'
    assert "protected-value" not in saved[0]["display_json"]
    assert json.loads(saved[0]["display_json"])["request_hash"] == "a" * 64
    reopened = ConnectionFactory(factory.config)
    assert commit((reopened, channel, frame))["sequence"] == 1
    duplicate = copy.deepcopy(frame)
    duplicate["events"][0]["sequence"] = 2
    assert commit((reopened, channel, duplicate))["sequence"] == 2
    assert requests(reopened) == saved


def test_gap_does_not_publish_request_or_refresh_its_expiry(native):
    factory, _, frame = native
    frame["events"][0]["sequence"] = 2
    assert commit(native) is None
    assert requests(factory) == []
    with factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_event_ingress SET received_at='2000-01-01T00:00:00Z'")
    first = {**frame, "events": [{**frame["events"][0], "sequence": 1,
                                "category": "text_delta", "payload": {"text": "Hello"}}]}
    assert commit(native, first)["sequence"] == 2
    row = requests(factory)[0]
    assert row["state"] == "EXPIRED"
    assert row["expires_at"] == "2000-01-01T00:02:00+00:00"


@pytest.mark.parametrize("fault", ["params", "hash", "turn", "category", "operation"])
def test_reused_native_id_with_different_content_rolls_back_entire_ack(native, fault):
    factory, _, frame = native
    commit(native)
    saved, events = requests(factory), snapshot(factory)
    second = copy.deepcopy(frame)
    event = second["events"][0]
    event["sequence"] = 2
    request = event["payload"]["native_approval"]
    if fault == "params": request["params"]["itemId"] = "changed"
    elif fault == "hash":
        request["request_hash"] = "b" * 64
        event["payload"]["native_approval_display"]["request_hash"] = "b" * 64
    elif fault == "turn": request["params"]["turnId"] = "another-turn"
    elif fault == "category": event["category"] = "input_request"
    else:
        with factory.unit_of_work() as uow:
            row = dict(uow.connection.execute("SELECT * FROM execution_operations WHERE operation_id='close'").fetchone())
            row["operation_id"] = "second-turn"
            uow.connection.execute("INSERT INTO execution_operations (" + ",".join(row) + ") VALUES (" +
                                   ",".join("?" for _ in row) + ")", tuple(row.values()))
        event["operation_id"] = "second-turn"
    with pytest.raises((ValueError, CoreError)):
        commit(native, second)
    assert requests(factory) == saved and snapshot(factory) == events


@pytest.mark.parametrize("fault", ["no_operation", "not_turn", "scope", "future_generation",
                                  "bool_id", "bad_hash", "no_display", "administrative"])
def test_invalid_request_never_commits_event_or_request(native, fault):
    factory, _, frame = native
    event = frame["events"][0]
    request = event["payload"]["native_approval"]
    if fault == "no_operation": event.pop("operation_id")
    elif fault == "bool_id": request["request_id"] = True
    elif fault == "bad_hash": request["request_hash"] = "invalid"
    elif fault == "no_display": event["payload"].pop("native_approval_display")
    elif fault == "administrative":
        request["request_hash"] = "sha256:" + "a" * 64
        event["payload"]["native_approval_display"]["request_hash"] = request["request_hash"]
    else:
        with factory.unit_of_work() as uow:
            if fault == "not_turn":
                uow.connection.execute("UPDATE execution_operations SET action='runtime.close'")
            else:
                scope = json.loads(uow.connection.execute(
                    "SELECT expected_revisions_json FROM execution_operations").fetchone()[0])
                scope["agent_id" if fault == "scope" else "session_owner_generation"] = "operator" if fault == "scope" else 2
                uow.connection.execute("UPDATE execution_operations SET expected_revisions_json=?", (json.dumps(scope),))
    with pytest.raises((ValueError, CoreError)):
        commit(native)
    assert requests(factory) == [] and snapshot(factory) == ([], [])


def test_typed_ids_are_distinct(native):
    factory, _, frame = native
    for sequence, native_id in enumerate((7, "7"), 1):
        event = frame["events"][0]
        event["sequence"] = sequence
        event["payload"]["native_approval"]["request_id"] = native_id
        commit(native)
    assert {row["native_request_id_json"] for row in requests(factory)} == {"7", '"7"'}


@pytest.mark.parametrize("terminal_first", [False, True])
def test_terminal_turn_cannot_leave_or_reopen_a_pending_request(native, terminal_first):
    factory, _, frame = native
    request = copy.deepcopy(frame["events"][0])
    terminal = {**request, "category": "turn_state", "payload": {"delivery_phase": "terminal"}}
    ordered = [terminal, request] if terminal_first else [request, terminal]
    for sequence, event in enumerate(ordered, 1): event["sequence"] = sequence
    assert commit(native, {**frame, "events": ordered})["sequence"] == 2
    assert requests(factory)[0]["state"] == "STALE"
    assert commit(native, {**frame, "events": [{**request, "sequence": 3}]})["sequence"] == 3
    assert requests(factory)[0]["state"] == "STALE"


def test_storage_failure_cannot_acknowledge_a_missing_request(native):
    factory, _, _ = native
    with factory.unit_of_work() as uow:
        uow.connection.execute("CREATE TRIGGER reject_request BEFORE INSERT ON execution_native_requests "
                               "BEGIN SELECT RAISE(ABORT,'Injected request failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="Injected"):
        commit(native)
    assert requests(factory) == [] and snapshot(factory) == ([], [])


@pytest.mark.parametrize("method,params,generation,category,kind", [
    ("item/tool/requestUserInput", {"turnId": "turn", "questions": []}, None,
     "input_request", "native_input"),
    ("control_request:can_use_tool", {"tool_name": "mcp__nexus__handoff_get", "input": {}}, 3,
     "approval_request", "native_approval"),
    ("control_request:can_use_tool", {"tool_name": "AskUserQuestion", "input": {}}, 3,
     "input_request", "native_input"),
])
def test_core_classifies_native_approval_and_input(native, method, params, generation, category, kind):
    factory, _, frame = native
    event = frame["events"][0]
    request = event["payload"]["native_approval"]
    request.update(method=method, params=params)
    if generation is not None: request["local_generation"] = generation
    event["payload"]["native_approval_display"] = copy.deepcopy(request)
    event["category"] = category
    commit(native)
    assert requests(factory)[0]["kind"] == kind


def test_same_native_id_in_two_stream_namespaces_is_distinct(native):
    factory, _, frame = native
    commit(native)
    with factory.unit_of_work() as uow:
        # A new Core stream is a different namespace; native IDs are local.
        uow.connection.execute("UPDATE execution_sessions SET stream_epoch='next-epoch'")
    frame["stream_epoch"] = frame["events"][0]["stream_epoch"] = "next-epoch"
    commit(native)
    rows = requests(factory)
    assert len(rows) == 2 and rows[0]["canonical_request_id"] != rows[1]["canonical_request_id"]


def test_old_generation_is_retained_without_actionable_authority(native):
    factory, _, _ = native
    with factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET owner_generation=2")
    commit(native)
    assert requests(factory)[0]["state"] == "STALE"
