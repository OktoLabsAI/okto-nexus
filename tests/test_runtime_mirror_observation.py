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
