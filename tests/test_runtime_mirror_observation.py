"""A registered context-only observer must receive the same logical delivery."""
import threading
import time

import pytest

from okto_nexus.application.adapter_registry import AdapterDescriptor
from okto_nexus.domain.endpoints import EndpointCapabilities
from okto_nexus.adapters.inbound.mcp.tools.harness import build_connector_factories
from test_harness_tools import FakeConnector
from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, wait_sent, tool

runtime = runtime_fixture


def open_observer(runtime, *, verified=True, method=True):
    deps, client, root, peers, operator, _ = runtime
    observed = threading.Event()
    contexts = []

    class ContextObserver(FakeConnector):
        # Optional adapter contract: store context without starting inference.
        # It deliberately has no implementation that forwards to send().
        def observe_context(self, session, envelope):
            contexts.append(envelope)
            observed.set()

    observer = ContextObserver(kind="fixture.context.v1")
    def factory(**kwargs):
        nonlocal observer
        observer = ContextObserver(kind="fixture.context.v1")
        if not method:
            observer.observe_context = None
        return observer
    capabilities = EndpointCapabilities(context_without_execution=True, events=True)
    build_connector_factories(deps).register(AdapterDescriptor(
        "fixture.context.v1", "fixture.context.v1", None, "fixture-context-v1",
        factory, lambda _: None, capabilities, observer.capabilities,
        input_schema={"context_observation_contract": 1},
        compatibility_probe=(lambda _: capabilities) if verified else None))
    headers = {"x-api-key": operator}
    profile = client.post("/api/v1/harness/profiles", headers=headers, json={
        "profile_id": "context-profile", "adapter_id": "fixture.context.v1", "enabled": True})
    assert profile.status_code == 200, profile.text
    endpoint = client.post("/api/v1/harness/endpoints", headers=headers, json={
        "endpoint_id": "context-observer", "agent_id": "worker", "adapter_id": "fixture.context.v1",
        "profile_id": "context-profile", "project_root": root, "enabled": True,
        "consumption": "mirror_only", "response_policy": "none"})
    assert endpoint.status_code == 200, endpoint.text
    opened = client.post("/api/v1/harness/sessions", headers=headers, json={
        "agent_id": "worker", "kind": "fixture.context.v1", "endpoint_id": "context-observer",
        "project_root": root})
    assert opened.status_code == 200, opened.text
    assert open_rest(runtime).status_code == 200
    return observer, observed, contexts


def wait_observation(runtime, source, expected):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with runtime[0].connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT * FROM runtime_context_observations WHERE source_operation_id=?",
                (source,)).fetchone()
        if row and row["status"] == expected:
            return dict(row)
        time.sleep(.01)
    raise AssertionError(dict(row) if row else "Observation intent missing")


def test_context_observer_receives_delivery_without_another_executor(runtime, monkeypatch):
    deps, client, _, peers, operator, _ = runtime
    observer, observed, contexts = open_observer(runtime)
    created = send_message(runtime, body="nonexecuting observer context")
    wait_sent(peers)
    assert observed.wait(5), "Approved context-only endpoint received no observation"
    assert len(contexts) == 1
    assert contexts[0]["message_id"] == created["message_id"]
    assert contexts[0]["response_requested"] is False
    assert contexts[0]["intent"] == "information"
    assert observer.sent == []
    assert [command.verb for peer in peers for command in peer.sent] == ["send_turn"]
    operation = created["runtime_operations"][0]
    observation = wait_observation(runtime, operation, "SENT_UNCONFIRMED")
    original_uow = deps.connection_factory.unit_of_work

    def query_only(*, write=True):
        uow = original_uow(write=write)
        if not write:
            # Fail deterministically if a read projection upgrades its SQLite
            # snapshot to write an authorization audit under concurrent writes.
            uow.connection.execute("PRAGMA query_only=ON")
        return uow

    monkeypatch.setattr(deps.connection_factory, "unit_of_work", query_only)
    inspected = tool(client, operator, "harness_get", {"operation_id": operation})
    assert inspected["ok"], inspected
    entry = inspected["data"]["context_observations"][0]
    assert entry["operation_id"] == observation["operation_id"]
    assert entry["external_acceptance"] == "not_observed"
    assert entry["execution_authority"] is False and entry["result_durable"] is False
    denied = tool(client, operator, "harness_send", {"session_id": observer.session.session_id,
        "payload": {"text": "observer is not an executor"}})
    assert not denied["ok"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        deliveries = uow.connection.execute("SELECT * FROM message_deliveries WHERE message_id=?",
            (created["message_id"],)).fetchall()
        assert len(deliveries) == 1
        assert deliveries[0]["consumer_kind"] == "push"
        assert deliveries[0]["consumer_operation_id"] == created["runtime_operations"][0]
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox WHERE message_id=?",
            (created["message_id"],)).fetchone()[0] == 1


@pytest.mark.parametrize("change", ["endpoint", "profile", "credential", "flag", "effective"])
def test_observation_revalidates_authority_before_transport(runtime, monkeypatch, change):
    deps, client, _, _, operator, _ = runtime
    observer, _, contexts = open_observer(runtime)
    runner = deps.runtime_dispatcher.context_dispatcher
    execute = runner._execute
    reached, release = threading.Event(), threading.Event()

    def hold(command, lane):
        reached.set()
        assert release.wait(10)
        execute(command, lane)

    monkeypatch.setattr(runner, "_execute", hold)
    try:
        created = send_message(runtime)
        assert reached.wait(5)
        headers = {"x-api-key": operator}
        if change == "endpoint":
            result = client.patch("/api/v1/harness/endpoints/context-observer", headers=headers,
                json={"expected_revision": 1, "enabled": False})
            assert result.status_code == 200, result.text
        elif change == "profile":
            result = client.patch("/api/v1/harness/profiles/context-profile", headers=headers,
                json={"expected_revision": 1, "enabled": False})
            assert result.status_code == 200, result.text
        elif change == "credential":
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute("UPDATE agents SET api_key_hash='revoked-fixture' WHERE agent_id='caller'")
        elif change == "flag":
            deps.config.feature_harness_integrations = False
        else:
            session = deps.harness_supervisor.get(observer.session.session_id)
            session.compatibility_report["effective_capabilities"]["context_without_execution"] = False
            # The observed compatibility record is also persisted; selection
            # and the final live guard both require current verified support.
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute("UPDATE harness_sessions SET compatibility_report=json_set(compatibility_report,"
                    "'$.effective_capabilities.context_without_execution',json('false')) WHERE session_id=?",
                    (observer.session.session_id,))
        release.set()
        wait_observation(runtime, created["runtime_operations"][0], "REJECTED")
        assert contexts == [] and observer.sent == []
    finally:
        release.set()
        deps.config.feature_harness_integrations = True


def test_observation_failure_after_acceptance_is_unknown_and_never_replayed(runtime, monkeypatch):
    deps, _, _, _, _, _ = runtime
    observer, observed, contexts = open_observer(runtime)
    accept = observer.observe_context

    def lost_reply(session, envelope):
        accept(session, envelope)
        raise OSError("fixture lost context transport response")

    monkeypatch.setattr(observer, "observe_context", lost_reply)
    created = send_message(runtime)
    assert observed.wait(5)
    row = wait_observation(runtime, created["runtime_operations"][0], "OUTCOME_UNKNOWN")
    for _ in range(3):
        deps.runtime_dispatcher.context_dispatcher.scan_once()
    assert len(contexts) == 1 and observer.sent == []
    with deps.connection_factory.unit_of_work() as uow:
        assert not deps.runtime_dispatcher.context_dispatcher.repo.observe(uow, operation_id=row["operation_id"],
            epoch=row["owner_epoch"] - 1, attempt_id=row["attempt_id"], expected="OUTCOME_UNKNOWN",
            status="SENT_UNCONFIRMED", now=deps.clock.now_iso())
        assert uow.connection.execute("SELECT count(*) FROM runtime_results").fetchone()[0] == 0


def test_observation_metadata_requires_its_own_endpoint_read_authority(runtime):
    from test_runtime_grants import issue
    _, client, _, _, operator, caller = runtime
    open_observer(runtime)
    created = send_message(runtime)
    operation = created["runtime_operations"][0]
    wait_observation(runtime, operation, "SENT_UNCONFIRMED")
    issue(runtime, ["read"])
    inspected = tool(client, caller, "harness_get", {"operation_id": operation})
    assert inspected["ok"] and inspected["data"]["context_observations"] == [], inspected
    grant = issue(runtime, ["read"], endpoint_id="context-observer")
    inspected = tool(client, caller, "harness_get", {"operation_id": operation})
    assert inspected["ok"] and len(inspected["data"]["context_observations"]) == 1, inspected
    assert client.delete("/api/v1/harness/grants/" + grant["grant_id"],
        headers={"x-api-key": operator}).status_code == 200
    inspected = tool(client, caller, "harness_get", {"operation_id": operation})
    assert inspected["ok"] and inspected["data"]["context_observations"] == [], inspected


@pytest.mark.parametrize("missing", ["probe", "method"])
def test_unverified_observer_does_not_receive_context_or_execution(runtime, missing):
    deps, _, _, peers, _, _ = runtime
    observer, _, contexts = open_observer(runtime, verified=missing != "probe", method=missing != "method")
    created = send_message(runtime)
    wait_sent(peers)
    session = deps.harness_supervisor.get(observer.session.session_id)
    assert session.compatibility_report["effective_capabilities"]["context_without_execution"] is False
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_context_observations WHERE source_operation_id=?",
            (created["runtime_operations"][0],)).fetchone()[0] == 0
    assert contexts == [] and observer.sent == []


def test_observation_insert_failure_rolls_back_the_canonical_delivery(runtime, monkeypatch):
    from okto_nexus.adapters.outbound.sqlite.runtime_observations_repo import SqliteRuntimeObservationRepo
    from okto_nexus.errors import ErrorCode, OktoNexusError
    deps, client, root, peers, _, caller = runtime
    observer, _, contexts = open_observer(runtime)
    insert = SqliteRuntimeObservationRepo.enqueue

    def fail_after_insert(self, uow, **kwargs):
        insert(self, uow, **kwargs)
        raise OktoNexusError(ErrorCode.DB_ERROR, "fixture observation commit failure", {})

    with monkeypatch.context() as patch:
        patch.setattr(SqliteRuntimeObservationRepo, "enqueue", fail_after_insert)
        reply = tool(client, caller, "message_create", {"project_root": root, "from_agent_id": "caller",
            "target": {"strategy": "direct", "agent_id": "worker"}, "body": "atomic observation", "subject": "fixture"})
    assert not reply["ok"] and reply["error"]["code"] == "DB_ERROR", reply
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ("messages", "message_deliveries", "delivery_outbox", "runtime_context_observations"):
            assert uow.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    assert not contexts and not observer.sent and not peers[0].sent
    created = send_message(runtime)
    wait_observation(runtime, created["runtime_operations"][0], "SENT_UNCONFIRMED")
    assert len(contexts) == 1


def test_timed_out_observation_keeps_its_single_worker_until_return(runtime, monkeypatch):
    deps, _, _, _, _, _ = runtime
    observer, observed, contexts = open_observer(runtime)
    accept = observer.observe_context
    release = threading.Event()

    def stuck(session, envelope):
        accept(session, envelope)
        assert release.wait(15)

    monkeypatch.setattr(observer, "observe_context", stuck)
    owner = deps.runtime_dispatcher
    try:
        first = send_message(runtime)
        assert observed.wait(5)
        wait_observation(runtime, first["runtime_operations"][0], "SENDING")
        owner.send_timeout_seconds = 0
        owner.context_dispatcher.expire()
        wait_observation(runtime, first["runtime_operations"][0], "OUTCOME_UNKNOWN")
        second = send_message(runtime)
        wait_observation(runtime, second["runtime_operations"][0], "PENDING")
        owner.context_dispatcher.scan_once()
        assert len(owner.context_dispatcher._threads) == 1
        assert not owner.context_dispatcher.idle()
        assert len(contexts) == 1
    finally:
        owner.send_timeout_seconds = 45
        release.set()


def test_close_cancels_pending_context_without_replaying_unknown_into_new_session(runtime, monkeypatch):
    from test_runtime_commands import wait_operation
    _, client, root, _, operator, _ = runtime
    observer, _, contexts = open_observer(runtime)
    accept = observer.observe_context

    def uncertain(session, envelope):
        accept(session, envelope)
        raise OSError("fixture uncertain observation")

    monkeypatch.setattr(observer, "observe_context", uncertain)
    first = send_message(runtime)
    wait_observation(runtime, first["runtime_operations"][0], "OUTCOME_UNKNOWN")
    pending = send_message(runtime)
    wait_observation(runtime, pending["runtime_operations"][0], "PENDING")
    closed = tool(client, operator, "harness_close", {"session_id": observer.session.session_id})
    assert closed["ok"], closed
    wait_operation(runtime, closed["data"]["operation_id"], lambda row: row["state"] == "DONE")
    wait_observation(runtime, pending["runtime_operations"][0], "CANCELLED")
    reopened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "fixture.context.v1", "endpoint_id": "context-observer",
        "project_root": root})
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["data"]["session_id"] != observer.session.session_id
    fresh = send_message(runtime)
    wait_observation(runtime, fresh["runtime_operations"][0], "SENT_UNCONFIRMED")
    wait_observation(runtime, first["runtime_operations"][0], "OUTCOME_UNKNOWN")
    assert [entry["message_id"] for entry in contexts] == [first["message_id"], fresh["message_id"]]
