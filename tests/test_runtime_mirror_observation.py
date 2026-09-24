"""A registered context-only observer must receive the same logical delivery."""
import threading

from okto_nexus.application.adapter_registry import AdapterDescriptor
from okto_nexus.domain.endpoints import EndpointCapabilities
from okto_nexus.adapters.inbound.mcp.tools.harness import build_connector_factories
from test_harness_tools import FakeConnector
from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, wait_sent

runtime = runtime_fixture


def test_context_observer_receives_delivery_without_another_executor(runtime):
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
    capabilities = EndpointCapabilities(context_without_execution=True, events=True)
    build_connector_factories(deps).register(AdapterDescriptor(
        "fixture.context.v1", "fixture.context.v1", None, "fixture-context-v1",
        lambda **kwargs: observer, lambda _: None, capabilities, observer.capabilities,
        input_schema={"context_observation_contract": 1}, compatibility_probe=lambda _: capabilities))
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
    created = send_message(runtime, body="nonexecuting observer context")
    wait_sent(peers)
    assert observed.wait(5), "Approved context-only endpoint received no observation"
    assert len(contexts) == 1
    assert contexts[0]["message_id"] == created["message_id"]
    assert contexts[0]["response_requested"] is False
    assert contexts[0]["intent"] == "notification"
    assert observer.sent == []
    assert [command.verb for peer in peers for command in peer.sent] == ["send_turn"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        deliveries = uow.connection.execute("SELECT * FROM message_deliveries WHERE message_id=?",
            (created["message_id"],)).fetchall()
        assert len(deliveries) == 1
        assert deliveries[0]["consumer_kind"] == "push"
        assert deliveries[0]["consumer_operation_id"] == created["runtime_operations"][0]
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox WHERE message_id=?",
            (created["message_id"],)).fetchone()[0] == 1
